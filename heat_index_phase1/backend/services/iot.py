"""Read-only provider adapter. Future storage changes stay behind this boundary."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
import os
import re
import threading
import time
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import ValidationError
import requests

from backend.schemas.iot import IoTResponse, RenderHistory, RenderHistoryRow, RenderLatest, SensorReading

TIMESTAMP_WARNING = "Source timestamps without dates or timezone offsets cannot establish sensor freshness. Request time is not measurement time."
FORECAST_WARNING = "The upstream CfC/custom-adjustment forecast and its claimed three-hour horizon are unvalidated; they are not ThermoCast research-model inference."
MAX_RESPONSE_BYTES = 1_048_576
MAX_HISTORY = 200


@dataclass(frozen=True)
class Settings:
    base_url: str = "https://thermocast-ai-2.onrender.com"
    connect_timeout: float = 3
    read_timeout: float = 8
    cache_seconds: float = 5
    freshness_seconds: float = 120


def settings() -> Settings:
    def bounded(name, default, minimum, maximum):
        try:
            value = float(os.getenv(name, str(default)))
            return value if math.isfinite(value) and minimum <= value <= maximum else default
        except ValueError:
            return default
    return Settings(base_url=os.getenv("IOT_RENDER_BASE_URL", Settings.base_url).rstrip("/"),
                    connect_timeout=bounded("IOT_CONNECT_TIMEOUT_SECONDS", 3, .1, 10),
                    read_timeout=bounded("IOT_READ_TIMEOUT_SECONDS", 8, .1, 20),
                    cache_seconds=bounded("IOT_CACHE_SECONDS", 5, 1, 30),
                    freshness_seconds=bounded("IOT_FRESHNESS_SECONDS", 120, 10, 86400))


def numeric(value, field: str, issues: list[str], unit: str = "") -> float | None:
    if value is None or value == "":
        issues.append(f"{field}: missing")
        return None
    if isinstance(value, str):
        pattern = r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*" + (r"%?" if unit == "%" else r"(?:°?\s*C)?" if unit == "C" else "") + r"\s*"
        match = re.fullmatch(pattern, value, flags=re.IGNORECASE)
        if not match:
            issues.append(f"{field}: invalid numeric value")
            return None
        value = match.group(1)
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        result = float("nan")
    if isinstance(value, bool) or not math.isfinite(result):
        issues.append(f"{field}: non-finite or invalid value")
        return None
    if field == "humidity_percent" and not 0 <= result <= 100:
        issues.append(f"{field}: outside 0–100%")
        return None
    if field == "temperature_c" and not -90 <= result <= 60:
        issues.append(f"{field}: outside supported −90–60°C screening range")
        return None
    return result


def timestamp_info(raw: str | None, now: datetime, fresh_seconds: float) -> dict:
    result = {"timestamp_raw": raw[:100] if raw else None, "measurement_timestamp_utc": None,
              "timestamp_quality": "missing", "freshness": "unknown", "age_seconds": None}
    if not raw:
        return result
    value = raw.strip()
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?", value):
        for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p"):
            try:
                datetime.strptime(value.upper(), fmt)
                return {**result, "timestamp_quality": "time_only"}
            except ValueError:
                pass
        return {**result, "timestamp_quality": "invalid"}
    if not re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value):
        return {**result, "timestamp_quality": "invalid"}
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return {**result, "timestamp_quality": "invalid"}
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return {**result, "timestamp_quality": "timezone_unverified"}
    try:
        measured = parsed.astimezone(timezone.utc)
        age = (now-measured).total_seconds()
    except (ValueError, OverflowError):
        return {**result, "timestamp_quality": "invalid"}
    return {**result, "measurement_timestamp_utc": measured.isoformat(), "timestamp_quality": "offset_verified",
            "freshness": "future" if age < -30 else "stale" if age > fresh_seconds else "fresh", "age_seconds": round(age, 2)}


def normalize_reading(raw, now: datetime, fresh_seconds: float, latest: bool) -> SensorReading:
    issues = []
    temperature = numeric(raw.temperature if latest else raw.temperature_c, "temperature_c", issues, "C")
    humidity = numeric(raw.humidity if latest else raw.humidity_pct, "humidity_percent", issues, "%")
    heat_index = numeric(raw.current_hi if latest else raw.heat_index_c, "heat_index_c", issues, "C")
    if heat_index is not None and (temperature is None or humidity is None):
        heat_index = None
        issues.append("heat_index_c: requires valid temperature and humidity")
    forecast_raw = raw.forecast_hi if latest else raw.forecast_3hr_c
    forecast = numeric(forecast_raw, "experimental_forecast_c", issues, "C") if forecast_raw is not None else None
    info = timestamp_info(raw.timestamp, now, fresh_seconds)
    advisory = raw.cur_category if latest else raw.pagasa_advisory
    return SensorReading(id=None if latest else raw.id, temperature_c=temperature, humidity_percent=humidity,
                         heat_index_c=heat_index, **info, advisory=advisory[:200] if advisory else None,
                         action=raw.cur_action[:500] if latest and raw.cur_action else None,
                         experimental_forecast_c=forecast, issues=issues)


class SensorProvider(Protocol):
    """Normalized transport boundary; React does not depend on Flask/SQLite/Firestore."""
    def latest(self) -> dict: ...
    def history(self, limit: int) -> dict: ...


class UpstreamError(Exception):
    def __init__(self, code: str, message: str, reachable: bool = False):
        super().__init__(message)
        self.code, self.reachable = code, reachable


class RenderSensorProvider:
    def __init__(self, configuration: Settings, get=None, utc_now=None, monotonic=None):
        self.configuration = configuration
        self.get = get or requests.get
        self.utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic or time.monotonic
        self.cache = OrderedDict()
        self.lock = threading.RLock()

    def _json(self, path: str, params=None):
        parsed = urlsplit(self.configuration.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise UpstreamError("configuration_invalid", "Configure a valid server-side IoT base URL without embedded credentials.")
        try:
            with self.get(self.configuration.base_url+path, params=params,
                          timeout=(self.configuration.connect_timeout, self.configuration.read_timeout),
                          allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise UpstreamError("upstream_http_error", f"IoT server returned HTTP {response.status_code}.", True)
                body = bytearray()
                for part in response.iter_content(chunk_size=16384):
                    body.extend(part)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise UpstreamError("response_too_large", "IoT server response exceeded the supported size.", True)
                try:
                    return json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeError) as exc:
                    raise UpstreamError("invalid_json", "IoT server did not return valid JSON.", True) from exc
        except requests.Timeout as exc:
            raise UpstreamError("upstream_timeout", "IoT request timed out. Server connectivity and sensor freshness are not established.") from exc
        except requests.RequestException as exc:
            raise UpstreamError("upstream_unavailable", "IoT server could not be reached. No replacement readings were generated.") from exc

    def _fetch(self, kind: str, limit: int = 100) -> dict:
        key = (kind, limit if kind == "history" else 0)
        # Single-flight, bounded cache. It is isolated from other application services.
        with self.lock:
            cached = self.cache.get(key)
            if cached and self.monotonic()-cached[0] < self.configuration.cache_seconds:
                result = deepcopy(cached[1])
                result["cache_age_seconds"] = round(self.monotonic()-cached[0], 2)
                now = self.utc_now()
                for reading in ([result["measurement"]] if result.get("measurement") else result.get("records", [])):
                    reading.update(timestamp_info(reading["timestamp_raw"], now, self.configuration.freshness_seconds))
                return result
            now = self.utc_now()
            base = dict(status="unavailable", server_reachable=False, checked_at_utc=now.isoformat(),
                        requested_limit=limit if kind == "history" else None,
                        warnings=[TIMESTAMP_WARNING, FORECAST_WARNING])
            try:
                payload = self._json("/api/v1/latest" if kind == "latest" else "/api/v1/history", {"limit":limit} if kind == "history" else None)
                base["server_reachable"] = True
                if kind == "latest":
                    raw = RenderLatest.model_validate(payload)
                    reading = normalize_reading(raw, now, self.configuration.freshness_seconds, True)
                    present = any(value is not None for value in (reading.temperature_c, reading.humidity_percent, reading.heat_index_c))
                    base.update(status="no_data" if not present else "partial" if reading.issues else "available",
                                measurement=reading if present or raw.timestamp else None, upstream_status=raw.status[:500] if raw.status else None,
                                invalid_readings=int(bool(reading.issues)), invalid_fields=len(reading.issues),
                                unverified_timestamps=int(reading.timestamp_quality != "offset_verified"))
                else:
                    container = RenderHistory.model_validate(payload)
                    records, invalid, invalid_fields = [], 0, 0
                    for row in container.readings[:limit]:
                        try:
                            reading = normalize_reading(RenderHistoryRow.model_validate(row), now, self.configuration.freshness_seconds, False)
                            invalid += int(bool(reading.issues)); invalid_fields += len(reading.issues)
                            records.append(reading)
                        except ValidationError:
                            invalid += 1
                    timestamps = [record.timestamp_raw for record in records if record.timestamp_raw]
                    base.update(status="partial" if invalid else "available" if records else "no_data",
                                records=records, returned_count=len(records), invalid_readings=invalid, invalid_fields=invalid_fields,
                                unverified_timestamps=sum(record.timestamp_quality != "offset_verified" for record in records),
                                duplicate_timestamps=len(timestamps)-len(set(timestamps)), upstream_reported_count=container.count)
            except UpstreamError as exc:
                base.update(error_code=exc.code, message=str(exc), server_reachable=exc.reachable)
            except ValidationError:
                base.update(error_code="schema_invalid", message="IoT server response did not match the supported JSON schema.", server_reachable=True)
            result = IoTResponse(**base).model_dump()
            self.cache[key] = (self.monotonic(), deepcopy(result))
            self.cache.move_to_end(key)
            while len(self.cache) > 8:
                self.cache.popitem(last=False)
            return result

    def latest(self) -> dict:
        return self._fetch("latest")

    def history(self, limit: int = 100) -> dict:
        if not 1 <= limit <= MAX_HISTORY:
            raise ValueError("IoT history limit must be between 1 and 200.")
        return self._fetch("history", limit)


@lru_cache(maxsize=4)
def _provider(configuration: Settings) -> RenderSensorProvider:
    return RenderSensorProvider(configuration)


def get_sensor_provider() -> SensorProvider:
    return _provider(settings())
