from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import base64
import hashlib
import json
import math
import re
from typing import Protocol

MAX_HISTORY = 200


class StorageUnavailable(RuntimeError):
    """No acknowledgement is implied; an uncertain remote write may have committed."""


class ConflictError(ValueError):
    pass


def validate_lineage(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise ValueError("Use a stable, explicitly assigned source lineage (1–96 safe characters).")
    return value


def utc_datetime(value) -> datetime | None:
    if value is None:
        return None
    result = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("A complete offset-bearing timestamp is required; naive timestamps are never assumed UTC.")
    try:
        normalized=result.astimezone(timezone.utc)
        return datetime(normalized.year,normalized.month,normalized.day,normalized.hour,normalized.minute,
                        normalized.second,normalized.microsecond,tzinfo=timezone.utc)
    except (ValueError,OverflowError):
        raise ValueError("Timestamp cannot be represented in UTC.") from None


def finite_number(value, name, low=None, high=None, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{name} must be a finite number, not a boolean/object.")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite number.") from None
    if not math.isfinite(number) or (low is not None and number < low) or (high is not None and number > high):
        raise ValueError(f"{name} is non-finite or outside its supported range.")
    return number


@dataclass(frozen=True)
class Reading:
    source_lineage_id: str
    source_record_id: int | None
    device_id: str
    temperature_c: float
    humidity_percent: float
    heat_index_c: float
    experimental_forecast_c: float | None
    advisory: str
    legacy_timestamp_raw: str | None
    measured_at_utc: datetime | None
    received_at_utc: datetime | None
    imported_at_utc: datetime | None
    source: str
    schema_version: int = 1

    def __post_init__(self):
        validate_lineage(self.source_lineage_id)
        if self.source_record_id is not None and (type(self.source_record_id) is not int or not 1 <= self.source_record_id <= 9_007_199_254_740_991):
            raise ValueError("Record IDs must be positive JavaScript-safe integers.")
        if not isinstance(self.device_id, str) or not 1 <= len(self.device_id) <= 128:
            raise ValueError("A bounded device identifier is required.")
        for name, low, high, nullable in [("temperature_c",-90,60,False), ("humidity_percent",0,100,False),
                                           ("heat_index_c",None,None,False), ("experimental_forecast_c",None,None,True)]:
            object.__setattr__(self,name,finite_number(getattr(self,name),name,low,high,nullable))
        for name in ("measured_at_utc", "received_at_utc", "imported_at_utc"):
            object.__setattr__(self,name,utc_datetime(getattr(self,name)))
        if self.schema_version != 1 or self.source not in {"esp32", "sqlite_legacy"}:
            raise ValueError("Unsupported schema or source.")
        if not isinstance(self.advisory,str) or not 1 <= len(self.advisory) <= 500:
            raise ValueError("A bounded advisory string is required.")
        if self.legacy_timestamp_raw is not None and (not isinstance(self.legacy_timestamp_raw,str) or len(self.legacy_timestamp_raw)>256):
            raise ValueError("Invalid legacy timestamp string.")
        if self.source == "sqlite_legacy" and (self.measured_at_utc is not None or self.received_at_utc is not None):
            raise ValueError("Legacy import cannot invent measurement or receipt timestamps.")

    def document(self, *, json_safe=False):
        result = dict(self.__dict__)
        if json_safe:
            for name in ("measured_at_utc", "received_at_utc", "imported_at_utc"):
                result[name] = result[name].isoformat() if result[name] else None
        return result

    @classmethod
    def from_document(cls, value):
        return cls(**{name:value[name] for name in cls.__dataclass_fields__})

    def with_id(self, identifier):
        return replace(self,source_record_id=identifier)

    def fingerprint(self):
        # Import time is not original content and may differ on a resumed run.
        result = self.document(json_safe=True)
        result.pop("imported_at_utc")
        return hashlib.sha256(json.dumps(result,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()


def document_id(lineage, record_id):
    validate_lineage(lineage)
    if type(record_id) is not int or record_id < 1:
        raise ValueError("A positive record ID is required.")
    return "reading_"+hashlib.sha256(f"{lineage}:{record_id}".encode()).hexdigest()


def cursor_encode(reading):
    return base64.urlsafe_b64encode(json.dumps([1,reading.source_lineage_id,reading.source_record_id]).encode()).decode().rstrip("=")


def cursor_decode(value, lineage):
    if value is None:
        return None
    if not isinstance(value,str) or len(value)>512:
        raise ValueError("Invalid history cursor.")
    try:
        version,source,identifier=json.loads(base64.b64decode(value+"="*(-len(value)%4),altchars=b"-_",validate=True))
        if version!=1 or source!=lineage or type(identifier) is not int or identifier<1:
            raise ValueError()
        return identifier
    except Exception:
        raise ValueError("Invalid or cross-lineage history cursor.") from None


def check_limit(limit):
    if type(limit) is not int or not 1<=limit<=MAX_HISTORY:
        raise ValueError("History limit must be between 1 and 200.")


@dataclass
class Page:
    readings: list[Reading]
    next_cursor: str | None


class Storage(Protocol):
    def insert(self, reading: Reading) -> Reading: ...
    def latest(self) -> Reading | None: ...
    def history(self, limit: int = 20, cursor: str | None = None) -> Page: ...


def legacy_reading(row, lineage, imported_at=None):
    identifier,timestamp,temperature,humidity,heat_index,forecast,advisory=row
    return Reading(lineage,identifier,"legacy-esp32-unverified",temperature,humidity,heat_index,forecast,
                   advisory,timestamp,None,None,imported_at,"sqlite_legacy")
