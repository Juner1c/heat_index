from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import HTTPException

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "Himawari9_Development"
BANDS = ("B08", "B13", "B14", "B15")
SATELLITE_COLUMNS = [f"{band}_{stat}_K" for band in BANDS for stat in ("mean", "min", "max")]


def fail(code: str, message: str, status: int = 422):
    raise HTTPException(status, {"code": code, "message": message})


def data_root() -> Path:
    return Path(os.getenv("THERMOCAST_DATA_DIR") or DEFAULT_DATA_ROOT).expanduser()


def source_path(kind: str) -> Path:
    root = data_root()
    sources = {
        "himawari": ("HIMAWARI_CSV", root / "mariveles_hourly" / "himawari_mariveles_hourly.csv"),
        "weather": ("GROUND_WEATHER_CSV", root / "open_meteo_clean.csv"),
        "heat-index": ("HEAT_INDEX_CSV", root / "heat_index_dataset.csv"),
    }
    variable, default = sources[kind]
    return Path(os.getenv(variable) or default).expanduser()


@lru_cache(maxsize=12)
def _read_version(path: str, modified: int, size: int) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        fail("source_missing", f"The configured {path.name} dataset is unavailable.", 404)
    try:
        stat = path.stat()
        frame = _read_version(str(path.resolve()), stat.st_mtime_ns, stat.st_size).copy()
    except (OSError, ValueError, pd.errors.ParserError):
        fail("source_unreadable", f"The configured {path.name} dataset cannot be read.")
    if frame.empty:
        fail("source_empty", f"The configured {path.name} dataset has no records.")
    return frame


def dataset(kind: str) -> tuple[pd.DataFrame, dict]:
    path = source_path(kind)
    raw = read_csv(path)
    timestamp_column = "time" if kind == "weather" else "timestamp"
    needed = {timestamp_column}
    if kind == "himawari":
        present = [column for column in SATELLITE_COLUMNS if column in raw]
        if not present:
            fail("schema_invalid", "No supported Himawari brightness-temperature columns were found.")
        columns = present
    else:
        columns = ["temperature_C", "humidity_percent"]
        needed.update(columns)
        if kind == "heat-index":
            needed.add("heat_index_C")
            columns.append("heat_index_C")
    if not needed.issubset(raw.columns):
        fail("schema_invalid", "Required columns are missing: " + ", ".join(sorted(needed.difference(raw.columns))))
    times = pd.to_datetime(raw[timestamp_column], errors="coerce", utc=True, format="mixed")
    frame = pd.DataFrame({"timestamp": times})
    invalid_values = {}
    for column in columns:
        numeric = pd.to_numeric(raw[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
        if column == "humidity_percent":
            numeric = numeric.where(numeric.between(0, 100))
        elif column == "temperature_C":
            numeric = numeric.where(numeric.between(-90, 60))
        elif column == "heat_index_C":
            # Only display an existing value when its ground-weather inputs are valid.
            numeric = numeric.where(frame["temperature_C"].notna() & frame["humidity_percent"].notna())
        invalid_values[column] = int((raw[column].notna() & numeric.isna()).sum())
        frame[column] = numeric
    metadata = {
        "source": path.name,
        "source_status": "available",
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "timezone": "UTC",
        "timezone_note": "Naive source timestamps are interpreted as UTC. The source Open-Meteo export specifies GMT (UTC offset 0).",
        "raw_rows": len(raw),
        "invalid_timestamps": int(times.isna().sum()),
        "duplicate_rows": int(raw.duplicated().sum()),
        "missing_values": {str(c): int(n) for c, n in raw.isna().sum().items()},
        "invalid_numeric_values": invalid_values,
    }
    if kind != "himawari":
        metadata.update(provider="Open-Meteo historical weather export", observation_type="Gridded weather data; not local station sensor readings", units={"temperature_C": "°C", "humidity_percent": "%"})
    if kind == "heat-index":
        metadata.update(
            method="Stored heat_index_C from prepare_heat_index.py: preliminary NWS index averaged with air temperature; Rothfusz regression at 80 °F and above, with low/high humidity adjustments; output converted to °C.",
            input_columns=["temperature_C", "humidity_percent"],
            alignment="Existing merge_weather_data.py inner-joins satellite and Open-Meteo observations on matching hourly timestamps.",
        )
    if kind == "heat-index" and frame["heat_index_C"].notna().sum() == 0:
        fail("measurements_unavailable", "No valid stored heat-index values with valid ground-weather inputs are available.")
    if kind == "weather" and not frame[["temperature_C", "humidity_percent"]].notna().any().any():
        fail("measurements_unavailable", "No valid ground-weather measurements are available.")
    return frame.dropna(subset=["timestamp"]).sort_values("timestamp", kind="stable"), metadata


def json_records(frame: pd.DataFrame) -> list[dict]:
    converted = frame.copy()
    for column in converted:
        if pd.api.types.is_datetime64_any_dtype(converted[column]):
            converted[column] = converted[column].map(lambda x: x.isoformat() if pd.notna(x) else None)
    return converted.astype(object).where(pd.notna(converted), None).to_dict("records")


def summary(frame: pd.DataFrame, metadata: dict) -> dict:
    times = frame["timestamp"]
    hours = pd.DatetimeIndex(times.dt.floor("h").unique()).sort_values()
    expected = int((hours[-1] - hours[0]) / pd.Timedelta(hours=1)) + 1 if len(hours) else 0
    return {
        **metadata, "total_records": metadata["raw_rows"],
        "valid_records": len(frame), "columns": list(frame.columns),
        "bands": [band for band in BANDS if any(column.startswith(band + "_") for column in frame)],
        "start": times.min().isoformat() if len(times) else None,
        "end": times.max().isoformat() if len(times) else None,
        "latest_observation": times.max().isoformat() if len(times) else None,
        "expected_hours": expected, "observed_hours": len(hours), "missing_hours": expected - len(hours),
        "coverage_percent": round(len(hours) / expected * 100, 2) if expected else 0,
        "duplicate_timestamps": int(times.duplicated().sum()),
        "completeness_percent": round((1 - sum(metadata["missing_values"].values()) / max(1, metadata["raw_rows"] * len(metadata["missing_values"]))) * 100, 2),
    }


def filtered(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    def parse(value: str | None, end_of_day: bool = False):
        if value is None:
            return None
        try:
            result = pd.to_datetime(value, utc=True, errors="raise")
        except (ValueError, OverflowError):
            fail("date_invalid", "Dates must be ISO 8601 dates or timestamps.")
        if pd.isna(result):
            fail("date_invalid", "Dates must not be empty.")
        if end_of_day and len(value) == 10:
            result += pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        return result
    first, last = parse(start), parse(end, True)
    if first is not None and last is not None and first > last:
        fail("date_range_invalid", "The start date must be earlier than the end date.")
    if first is not None:
        frame = frame[frame["timestamp"] >= first]
    if last is not None:
        frame = frame[frame["timestamp"] <= last]
    return frame


def chart_data(frame: pd.DataFrame, max_points: int) -> tuple[list[dict], str]:
    values = frame.drop_duplicates("timestamp", keep="first").set_index("timestamp")
    if values.empty:
        return [], "observed"
    if len(values) > max_points:
        seconds = max(1, int(np.ceil(((values.index[-1] - values.index[0]).total_seconds() + 1) / max_points)))
        aggregations = {c: "min" if "_min_" in c else "max" if "_max_" in c else "mean" for c in values}
        values = values.resample(f"{seconds}s", origin="start").agg(aggregations)
        return json_records(values.reset_index()), f"Time bins of {seconds} seconds: minima/min, maxima/max, other measurements/mean."
    # Insert only one marker per real hourly gap; never invent observed values.
    gaps = values.index.to_series().diff() > pd.Timedelta(hours=1)
    markers = values.index[gaps] - pd.Timedelta(nanoseconds=1)
    if len(markers):
        values = values.reindex(values.index.union(markers)).sort_index()
    return json_records(values.reset_index()), "observed"


def missing_periods(frame: pd.DataFrame) -> list[dict]:
    hours = pd.DatetimeIndex(frame["timestamp"].dt.floor("h").unique()).sort_values()
    result = []
    for previous, current in zip(hours[:-1], hours[1:]):
        count = int((current - previous) / pd.Timedelta(hours=1)) - 1
        if count > 0:
            result.append({"start": (previous + pd.Timedelta(hours=1)).isoformat(), "end": (current - pd.Timedelta(hours=1)).isoformat(), "hours": count})
    return result
