"""ThermoCast API for historical observations, baseline forecasts, and risk alerts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
import os
from pathlib import Path
import re
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.routers.dashboard import router as dashboard_router
from backend.routers.forecasting import router as forecasting_router
from backend.routers.iot import router as iot_router
from backend.middleware import ForecastBodyLimit

app = FastAPI(title="ThermoCast API", version="0.3.0")
app.add_middleware(ForecastBodyLimit)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501,http://localhost:5173,http://127.0.0.1:5173").split(",")], allow_methods=["GET", "POST"], allow_headers=["*"])
app.include_router(dashboard_router)
app.include_router(forecasting_router)
app.include_router(iot_router)

DATE_CANDIDATES = ("timestamp", "datetime", "date_time", "time", "date", "observation_time")
TEMPERATURE_CANDIDATES = ("temperature_c", "temp_c", "air_temperature_c", "temperature", "temp", "t2m")
HUMIDITY_CANDIDATES = ("relative_humidity", "relative_humidity_pct", "humidity", "rh", "rh_pct")
HEAT_INDEX_CANDIDATES = ("heat_index_c", "heat_index", "heatindex_c", "hi_c", "heat_index_value")
STATION_CANDIDATES = ("station", "station_name", "station_id", "location", "site", "site_name")
LATITUDE_CANDIDATES = ("latitude", "lat", "station_latitude")
LONGITUDE_CANDIDATES = ("longitude", "lon", "lng", "station_longitude")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEATHER_CSV = PROJECT_ROOT.parent / "Himawari9_Development" / "mariveles_hourly" / "himawari_mariveles_hourly.csv"


def _find_column(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in df.columns}
    return next((lookup[name] for name in candidates if name in lookup), None)


def load_data() -> tuple[pd.DataFrame, Path]:
    path = Path(os.getenv("WEATHER_CSV") or DEFAULT_WEATHER_CSV).expanduser()
    if not path.is_file():
        raise HTTPException(404, f"CSV not found: {path.name}. Check the WEATHER_CSV configuration.")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise HTTPException(422, f"Unable to read CSV: {exc}") from exc
    if df.empty:
        raise HTTPException(422, "CSV is empty")
    return df, path


def filter_station(df: pd.DataFrame, station: str | None) -> pd.DataFrame:
    if station is None:
        return df
    column = _find_column(df, STATION_CANDIDATES)
    if column is None:
        raise HTTPException(400, "This dataset has no station or location column.")
    selected = df[df[column].astype(str).str.casefold() == station.casefold()]
    if selected.empty:
        raise HTTPException(404, f"Station not found: {station}")
    return selected


def satellite_columns(df: pd.DataFrame) -> list[str]:
    patterns = (
        re.compile(r"^(?:ahi_)?b(?:and)?[_-]?0?\d{1,2}(?:[_-].+)?$", re.IGNORECASE),
        re.compile(r"^(?:tbb|brightness_temperature)[_-]?0?\d{1,2}(?:[_-].+)?$", re.IGNORECASE),
    )
    return [str(column) for column in df.columns if any(pattern.match(str(column).strip()) for pattern in patterns)]


def timestamp_series(df: pd.DataFrame) -> tuple[str | None, pd.Series | None]:
    column = _find_column(df, DATE_CANDIDATES)
    if column is None:
        return None, None
    return column, pd.to_datetime(df[column], errors="coerce", utc=True)


def detected_roles(df: pd.DataFrame) -> dict[str, str | None]:
    return {
        "timestamp": _find_column(df, DATE_CANDIDATES),
        "temperature": _find_column(df, TEMPERATURE_CANDIDATES),
        "humidity": _find_column(df, HUMIDITY_CANDIDATES),
        "heat_index": _find_column(df, HEAT_INDEX_CANDIDATES),
        "station": _find_column(df, STATION_CANDIDATES),
        "latitude": _find_column(df, LATITUDE_CANDIDATES),
        "longitude": _find_column(df, LONGITUDE_CANDIDATES),
    }


def _heat_index_celsius(temperature_c: pd.Series, humidity: pd.Series) -> pd.Series:
    """NOAA/NWS regression with the standard simple-index adjustment."""
    t_f = temperature_c * 9 / 5 + 32
    rh = humidity
    simple = 0.5 * (t_f + 61 + (t_f - 68) * 1.2 + rh * 0.094)
    simple = (simple + t_f) / 2
    regression = (-42.379 + 2.04901523*t_f + 10.14333127*rh - 0.22475541*t_f*rh
                  - 0.00683783*t_f**2 - 0.05481717*rh**2 + 0.00122874*t_f**2*rh
                  + 0.00085282*t_f*rh**2 - 0.00000199*t_f**2*rh**2)
    return (regression.where(simple >= 80, simple) - 32) * 5 / 9


def observations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str | None]]:
    timestamp_column, timestamps = timestamp_series(df)
    temperature_column = _find_column(df, TEMPERATURE_CANDIDATES)
    humidity_column = _find_column(df, HUMIDITY_CANDIDATES)
    heat_index_column = _find_column(df, HEAT_INDEX_CANDIDATES)
    columns = {"timestamp": timestamp_column, "temperature": temperature_column, "humidity": humidity_column, "heat_index": heat_index_column}
    if timestamps is None:
        raise HTTPException(422, f"No timestamp column found. Supported names: {', '.join(DATE_CANDIDATES)}")
    result = pd.DataFrame({"timestamp": timestamps})
    if temperature_column:
        result["temperature_c"] = pd.to_numeric(df[temperature_column], errors="coerce")
    if humidity_column:
        result["relative_humidity"] = pd.to_numeric(df[humidity_column], errors="coerce")
    if heat_index_column:
        result["heat_index_c"] = pd.to_numeric(df[heat_index_column], errors="coerce")
    elif temperature_column and humidity_column:
        result["heat_index_c"] = _heat_index_celsius(result["temperature_c"], result["relative_humidity"])
    return result.dropna(subset=["timestamp"]).sort_values("timestamp"), columns


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    converted = frame.copy()
    for column in converted.columns:
        if pd.api.types.is_datetime64_any_dtype(converted[column]):
            converted[column] = converted[column].map(lambda value: value.isoformat() if pd.notna(value) else None)
    rows = converted.astype(object).where(pd.notna(converted), None).to_dict("records")
    return [{key: None if isinstance(value, float) and not math.isfinite(value) else value for key, value in row.items()} for row in rows]


def _split_ranges(sample_count: int) -> list[tuple[str, int, int]]:
    """Return non-overlapping chronological 70/15/15 ranges."""
    train_end = max(1, int(sample_count * 0.70))
    validation_end = max(train_end + 1, int(sample_count * 0.85)) if sample_count >= 3 else train_end
    validation_end = min(validation_end, sample_count)
    return [
        ("train", 0, train_end),
        ("validation", train_end, validation_end),
        ("test", validation_end, sample_count),
    ]


def _error_metrics(errors: pd.Series) -> dict[str, Any]:
    if errors.empty:
        return {"samples": 0, "mae_c": None, "rmse_c": None}
    return {
        "samples": len(errors),
        "mae_c": float(errors.abs().mean()),
        "rmse_c": float((errors.pow(2).mean()) ** 0.5),
    }


def risk_level(heat_index_c: float) -> tuple[str, str]:
    if heat_index_c >= 52:
        return "extreme_danger", "Heat stroke is imminent; suspend strenuous outdoor activity."
    if heat_index_c >= 42:
        return "danger", "Heat cramps and exhaustion are likely; heat stroke is possible."
    if heat_index_c >= 33:
        return "extreme_caution", "Heat cramps and exhaustion are possible with prolonged exposure."
    if heat_index_c >= 27:
        return "caution", "Fatigue is possible with prolonged exposure and activity."
    return "normal", "No elevated heat-index category; continue normal hydration precautions."


def _artifact_path() -> Path | None:
    configured = os.getenv("LNN_MODEL_PATH")
    return Path(configured).expanduser() if configured else None


def _load_lnn():
    from ml.model import load_artifact
    path = _artifact_path()
    if path is None:
        raise HTTPException(503, "LNN_MODEL_PATH is not configured.")
    try:
        return load_artifact(path)
    except Exception as exc:
        raise HTTPException(503, f"LNN artifact is not ready: {exc}") from exc


def _forecast_frame(horizon: int, requested_model: str = "auto", station: str | None = None) -> tuple[pd.DataFrame, str]:
    df, _ = load_data()
    df = filter_station(df, station)
    obs, _ = observations(df)
    if "heat_index_c" not in obs or obs["heat_index_c"].dropna().empty:
        raise HTTPException(422, "Forecasting requires a heat-index column or temperature and humidity columns.")
    valid = obs.dropna(subset=["heat_index_c"])
    last = valid.iloc[-1]
    times = [last["timestamp"] + timedelta(hours=step) for step in range(1, horizon + 1)]
    use_lnn = requested_model == "lnn" or (requested_model == "auto" and _artifact_path() is not None)
    if use_lnn:
        from ml.model import autoregressive_forecast
        model, metadata = _load_lnn()
        features = metadata["feature_columns"]
        missing = [column for column in features if column not in obs.columns]
        if missing:
            raise HTTPException(422, f"Dataset is missing LNN features: {', '.join(missing)}")
        history = obs[features].dropna().tail(int(metadata["sequence_length"]))
        if len(history) < int(metadata["sequence_length"]):
            raise HTTPException(422, f"LNN requires {metadata['sequence_length']} complete historical rows; found {len(history)}.")
        values = autoregressive_forecast(model, metadata, history.to_numpy(), horizon)
        return pd.DataFrame({"timestamp": times, "heat_index_c": values}), "lnn"
    return pd.DataFrame({"timestamp": times, "heat_index_c": [float(last["heat_index_c"])] * horizon}), "persistence_baseline"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/model/status")
def model_status() -> dict[str, Any]:
    path = _artifact_path()
    result = {"active_model": "persistence_baseline", "baseline_ready": True, "lnn_configured": path is not None, "lnn_artifact_present": bool(path and path.is_dir()), "lnn_ready": False, "message": "Set LNN_MODEL_PATH to a trained artifact directory."}
    if path is not None:
        try:
            from ml.model import load_artifact
            _, metadata = load_artifact(path)
            result.update(active_model="lnn", lnn_ready=True, message="Validated LNN artifact is ready.", metadata={key: metadata.get(key) for key in ("model_type", "feature_columns", "sequence_length", "split_policy", "metrics", "data_start", "data_end")})
        except Exception as exc:
            result["message"] = f"LNN artifact validation failed: {exc}"
    return result


@app.get("/api/summary")
def summary(station: str | None = None) -> dict[str, Any]:
    df, path = load_data()
    df = filter_station(df, station)
    timestamp_column, timestamps = timestamp_series(df)
    result: dict[str, Any] = {"file": path.name, "rows": len(df), "columns": list(df.columns), "null_cells": int(df.isna().sum().sum()), "duplicate_rows": int(df.duplicated().sum()), "timestamp_column": timestamp_column, "missing_hours": None, "duplicate_timestamps": None, "invalid_timestamps": None, "start": None, "end": None}
    if timestamps is not None:
        valid = timestamps.dropna()
        result["invalid_timestamps"] = int(timestamps.isna().sum())
        result["duplicate_timestamps"] = int(valid.duplicated().sum())
        if not valid.empty:
            hours = pd.DatetimeIndex(valid.dt.floor("h").unique()).sort_values()
            expected = pd.date_range(hours.min(), hours.max(), freq="h")
            result.update(start=valid.min().isoformat(), end=valid.max().isoformat(), missing_hours=int(len(expected.difference(hours))))
    return result


@app.get("/api/quality")
def quality(station: str | None = None) -> dict[str, Any]:
    df, path = load_data()
    df = filter_station(df, station)
    timestamp_column, timestamps = timestamp_series(df)
    roles = detected_roles(df)
    missing_by_column = {str(column): int(count) for column, count in df.isna().sum().items()}
    range_issues: list[dict[str, Any]] = []
    range_rules = {
        roles["temperature"]: (-40.0, 60.0, "temperature_c"),
        roles["humidity"]: (0.0, 100.0, "relative_humidity_pct"),
        roles["heat_index"]: (-40.0, 80.0, "heat_index_c"),
    }
    for column, (minimum, maximum, measure) in range_rules.items():
        if column is None:
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        invalid_count = int(((values < minimum) | (values > maximum)).sum())
        if invalid_count:
            range_issues.append({"column": column, "measure": measure, "minimum": minimum, "maximum": maximum, "invalid_values": invalid_count})
    column_profiles = []
    for column in df.columns:
        values = df[column]
        profile: dict[str, Any] = {
            "column": str(column),
            "dtype": str(values.dtype),
            "missing": int(values.isna().sum()),
            "complete_pct": round(float(values.notna().mean() * 100), 2),
            "unique": int(values.nunique(dropna=True)),
        }
        numeric_values = pd.to_numeric(values, errors="coerce")
        if numeric_values.notna().sum() == values.notna().sum() and numeric_values.notna().any():
            profile.update(min=float(numeric_values.min()), max=float(numeric_values.max()), mean=float(numeric_values.mean()))
        column_profiles.append(profile)
    duplicate_timestamps = None
    invalid_timestamps = None
    observed_hours = None
    missing_hours = None
    expected_hours = None
    completion_pct = None
    if timestamps is not None:
        valid = timestamps.dropna()
        duplicate_timestamps = int(valid.duplicated().sum())
        invalid_timestamps = int(timestamps.isna().sum())
        observed_hours = int(valid.dt.floor("h").nunique())
        if not valid.empty:
            observed = pd.DatetimeIndex(valid.dt.floor("h").unique()).sort_values()
            missing_hours = int((observed[-1] - observed[0]) / pd.Timedelta(hours=1)) + 1 - len(observed)
        start_value = os.getenv("COLLECTION_START")
        end_value = os.getenv("COLLECTION_END")
        if start_value and end_value:
            start = pd.to_datetime(start_value, errors="coerce", utc=True)
            end = pd.to_datetime(end_value, errors="coerce", utc=True)
            if pd.notna(start) and pd.notna(end) and end >= start:
                expected_hours = int(len(pd.date_range(start, end, freq="h")))
                in_window = valid[(valid >= start) & (valid <= end)].dt.floor("h").nunique()
                completion_pct = min(100.0, round(in_window / expected_hours * 100, 2))
    issues = []
    if timestamp_column is None:
        issues.append("missing_timestamp_column")
    if invalid_timestamps:
        issues.append("invalid_timestamps")
    if duplicate_timestamps:
        issues.append("duplicate_timestamps")
    if df.duplicated().any():
        issues.append("duplicate_rows")
    if missing_hours:
        issues.append("missing_hours")
    if any(missing_by_column.values()):
        issues.append("missing_values")
    if range_issues:
        issues.append("out_of_range_weather_values")
    return {
        "file": path.name,
        "status": "ready" if not issues else "attention_required",
        "issues": issues,
        "detected_columns": roles,
        "missing_by_column": missing_by_column,
        "column_profiles": column_profiles,
        "range_issues": range_issues,
        "missing_hours": missing_hours,
        "heat_index_available": roles["heat_index"] is not None or bool(roles["temperature"] and roles["humidity"]),
        "invalid_timestamps": invalid_timestamps,
        "duplicate_timestamps": duplicate_timestamps,
        "download_progress": {
            "observed_hours": observed_hours,
            "expected_hours": expected_hours,
            "completion_pct": completion_pct,
            "configured": expected_hours is not None,
        },
    }


@app.get("/api/gaps")
def gaps(station: str | None = None, limit: int = Query(500, ge=1, le=10000)) -> dict[str, Any]:
    df, _ = load_data()
    df = filter_station(df, station)
    timestamp_column, timestamps = timestamp_series(df)
    if timestamp_column is None or timestamps is None:
        raise HTTPException(422, "Gap detection requires a timestamp column.")
    valid = timestamps.dropna()
    if valid.empty:
        return {"missing_count": 0, "missing_timestamps": [], "gap_periods": [], "duplicate_timestamps": [], "invalid_rows": int(timestamps.isna().sum()), "truncated": False}
    hours = pd.DatetimeIndex(valid.dt.floor("h").unique()).sort_values()
    expected = pd.date_range(hours.min(), hours.max(), freq="h")
    missing = expected.difference(hours)
    periods = []
    if len(missing):
        period_start = previous = missing[0]
        for current in missing[1:]:
            if current - previous != pd.Timedelta(hours=1):
                periods.append({"start": period_start.isoformat(), "end": previous.isoformat(), "hours": int((previous - period_start) / pd.Timedelta(hours=1)) + 1})
                period_start = current
            previous = current
        periods.append({"start": period_start.isoformat(), "end": previous.isoformat(), "hours": int((previous - period_start) / pd.Timedelta(hours=1)) + 1})
    duplicate_values = valid[valid.duplicated(keep=False)].sort_values().drop_duplicates()
    return {
        "missing_count": len(missing),
        "missing_timestamps": [value.isoformat() for value in missing[:limit]],
        "gap_periods": periods[:limit],
        "duplicate_timestamps": [value.isoformat() for value in duplicate_values.iloc[:limit]],
        "invalid_rows": int(timestamps.isna().sum()),
        "truncated": len(missing) > limit or len(periods) > limit or len(duplicate_values) > limit,
    }


@app.get("/api/records")
def records(limit: int = Query(100, ge=1, le=1000), station: str | None = None) -> dict[str, Any]:
    df, _ = load_data()
    df = filter_station(df, station)
    return {"records": _records(df.tail(limit))}


@app.get("/api/numeric")
def numeric(limit: int = Query(1000, ge=1, le=10000), station: str | None = None) -> dict[str, Any]:
    df, _ = load_data()
    df = filter_station(df, station)
    _, timestamps = timestamp_series(df)
    if timestamps is None:
        raise HTTPException(422, "Numeric history requires a timestamp column.")
    result = pd.DataFrame({"timestamp": timestamps})
    for column in df.columns:
        if column == _find_column(df, DATE_CANDIDATES):
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        if values.notna().any():
            result[str(column)] = values
    obs, _ = observations(df)
    for column in ("temperature_c", "relative_humidity", "heat_index_c"):
        if column in obs and column not in result:
            result[column] = obs[column]
    result = result.dropna(subset=["timestamp"]).sort_values("timestamp")
    return {"columns": list(result.columns), "records": _records(result.tail(limit))}


@app.get("/api/stations")
def stations() -> dict[str, Any]:
    df, _ = load_data()
    station_column = _find_column(df, STATION_CANDIDATES)
    latitude_column = _find_column(df, LATITUDE_CANDIDATES)
    longitude_column = _find_column(df, LONGITUDE_CANDIDATES)
    if station_column is None:
        return {"station_column": None, "stations": [{"name": "Mariveles", "latitude": None, "longitude": None, "rows": len(df)}]}
    items = []
    for name, group in df.dropna(subset=[station_column]).groupby(station_column, sort=True):
        latitude = pd.to_numeric(group[latitude_column], errors="coerce").dropna().median() if latitude_column else None
        longitude = pd.to_numeric(group[longitude_column], errors="coerce").dropna().median() if longitude_column else None
        items.append({"name": str(name), "latitude": None if latitude is None or pd.isna(latitude) else float(latitude), "longitude": None if longitude is None or pd.isna(longitude) else float(longitude), "rows": len(group)})
    return {"station_column": station_column, "stations": items}


@app.get("/api/satellite")
def satellite(limit: int = Query(1000, ge=1, le=10000), station: str | None = None) -> dict[str, Any]:
    df, _ = load_data()
    df = filter_station(df, station)
    timestamp_column, timestamps = timestamp_series(df)
    bands = satellite_columns(df)
    if timestamp_column is None:
        raise HTTPException(422, "Satellite visualization requires a timestamp column.")
    frame = pd.DataFrame({"timestamp": timestamps})
    valid_bands = []
    for column in bands:
        values = pd.to_numeric(df[column], errors="coerce")
        if values.notna().any():
            frame[column] = values
            valid_bands.append(column)
    frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp")
    return {"bands": valid_bands, "records": _records(frame.tail(limit))}


@app.get("/api/forecast")
def forecast(horizon: int = Query(24, ge=1, le=168), model: str = Query("auto", pattern="^(auto|baseline|lnn)$"), station: str | None = None) -> dict[str, Any]:
    frame, active_model = _forecast_frame(horizon, model, station)
    generated_from = frame.iloc[0]["timestamp"] - timedelta(hours=1)
    return {"model": active_model, "generated_from": generated_from.isoformat(), "horizon_hours": horizon, "forecasts": _records(frame)}


@app.get("/api/evaluation")
def evaluation(station: str | None = None) -> dict[str, Any]:
    df, _ = load_data()
    df = filter_station(df, station)
    obs, _ = observations(df)
    if "heat_index_c" not in obs:
        raise HTTPException(422, "Evaluation requires heat-index data or temperature and humidity columns.")
    series = obs.set_index("timestamp")["heat_index_c"].dropna()
    if len(series) < 3:
        raise HTTPException(422, "At least three valid heat-index observations are required.")
    actual, predicted = series.iloc[1:], series.shift(1).iloc[1:]
    error = actual - predicted
    error_frame = pd.DataFrame({"timestamp": actual.index, "actual_c": actual.values, "predicted_c": predicted.values, "error_c": error.values})
    splits = []
    for name, start, end in _split_ranges(len(error_frame)):
        part = error_frame.iloc[start:end]
        metrics = _error_metrics(part["error_c"])
        splits.append({
            "name": name,
            **metrics,
            "start": None if part.empty else part.iloc[0]["timestamp"].isoformat(),
            "end": None if part.empty else part.iloc[-1]["timestamp"].isoformat(),
        })
    metrics = _error_metrics(error)
    result = {
        "model": "persistence_baseline", "strategy": "walk_forward_one_hour",
        **metrics, "start": actual.index.min().isoformat(), "end": actual.index.max().isoformat(),
        "split_policy": "chronological_70_15_15", "splits": splits,
        "recent_errors": _records(error_frame.tail(100)),
    }
    baseline_test = next(item for item in splits if item["name"] == "test")
    comparisons = [{"model": "persistence_baseline", "split": "test", **{key: baseline_test[key] for key in ("samples", "mae_c", "rmse_c")}}]
    status = model_status()
    if status["lnn_ready"]:
        lnn_test = status.get("metadata", {}).get("metrics", {}).get("test")
        if lnn_test:
            comparisons.append({"model": "lnn", "split": "test", **{key: lnn_test.get(key) for key in ("samples", "mae_c", "rmse_c")}})
    result["comparisons"] = comparisons
    return result


@app.get("/api/alerts")
def alerts(horizon: int = Query(24, ge=1, le=168), model: str = Query("auto", pattern="^(auto|baseline|lnn)$"), station: str | None = None) -> dict[str, Any]:
    items = []
    frame, active_model = _forecast_frame(horizon, model, station)
    for row in _records(frame):
        level, guidance = risk_level(float(row["heat_index_c"]))
        items.append({**row, "risk_level": level, "guidance": guidance})
    return {"model": active_model, "alerts": items}


@app.get("/api/report")
def report(station: str | None = None) -> dict[str, Any]:
    """Return a portable snapshot for validation and technical reporting."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "study_area": "Mariveles, Bataan, Philippines",
        "station": station or "all",
        "dataset": summary(station),
        "quality": quality(station),
        "gaps": gaps(station, 500),
        "model": model_status(),
        "evaluation": evaluation(station),
    }
