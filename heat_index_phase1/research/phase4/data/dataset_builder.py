from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.phase4.common import FEATURES, sha256
from research.phase4.data.validation import read_hourly

WEATHER = FEATURES[:3]
SATELLITE = FEATURES[3:]


def heat_index_c(temperature, humidity) -> np.ndarray:
    """Existing NWS preliminary/Rothfusz method; invalid weather stays unavailable."""
    temperature, rh = np.asarray(temperature, float), np.asarray(humidity, float)
    valid = np.isfinite(temperature) & np.isfinite(rh) & (temperature >= -90) & (temperature <= 60) & (rh >= 0) & (rh <= 100)
    temperature, rh = np.where(valid, temperature, np.nan), np.where(valid, rh, np.nan)
    t = temperature * 9 / 5 + 32
    simple = (0.5 * (t + 61 + (t - 68) * 1.2 + rh * 0.094) + t) / 2
    roth = (-42.379 + 2.04901523*t + 10.14333127*rh - 0.22475541*t*rh
            - 0.00683783*t**2 - 0.05481717*rh**2 + 0.00122874*t**2*rh
            + 0.00085282*t*rh**2 - 0.00000199*t**2*rh**2)
    hi = np.where(simple >= 80, roth, simple)
    hi -= np.where((simple >= 80) & (rh < 13) & (t >= 80) & (t <= 112),
                   ((13-rh)/4) * np.sqrt(np.maximum((17-np.abs(t-95))/17, 0)), 0)
    hi += np.where((simple >= 80) & (rh > 85) & (t >= 80) & (t <= 87), ((rh-85)/10)*((87-t)/5), 0)
    return np.where(valid, (hi-32)*5/9, np.nan)


def build_dataset(satellite_paths: list[Path], weather_paths: list[Path], provenance: dict) -> tuple[pd.DataFrame, dict]:
    satellite = read_hourly(satellite_paths, "timestamp", SATELLITE)
    weather = read_hourly(weather_paths, "time", WEATHER)
    merged = satellite.merge(weather, on="timestamp", how="left", validate="one_to_one")
    # Screen invalid values, but keep their timestamps so windows cannot bridge them.
    merged.loc[~merged.temperature_C.between(-90, 60), "temperature_C"] = np.nan
    merged.loc[~merged.humidity_percent.between(0, 100), "humidity_percent"] = np.nan
    merged.loc[~merged.dew_point_C.between(-100, 60), "dew_point_C"] = np.nan
    for column in SATELLITE:
        merged.loc[merged[column] <= 0, column] = np.nan
    merged["heat_index_C"] = heat_index_c(merged.temperature_C, merged.humidity_percent)
    indexed = merged.set_index("timestamp")
    next_hour = merged.timestamp + pd.Timedelta(hours=1)
    merged["target_heat_index_1h_C"] = indexed.heat_index_C.reindex(next_hour).to_numpy()
    sources = [{"path": str(path.resolve()), "sha256": sha256(path)} for path in [*satellite_paths, *weather_paths]]
    fingerprint = hashlib.sha256(json.dumps({"source_hashes": [item["sha256"] for item in sources], "features": FEATURES,
                                            "builder_version": 1, "provenance": provenance}, sort_keys=True).encode()).hexdigest()
    manifest = {"dataset_fingerprint": fingerprint, "sources": sources, "provenance": provenance,
                "timezone": "UTC", "units": {**{k: "K" for k in SATELLITE}, "temperature_C": "°C",
                "dew_point_C": "°C", "humidity_percent": "%", "heat_index_C": "°C", "target_heat_index_1h_C": "°C"},
                "satellite_rows": len(satellite), "weather_rows": len(weather), "aligned_rows": len(merged),
                "satellite_without_weather_timestamp": int((~satellite.timestamp.isin(weather.timestamp)).sum()),
                "invalid_feature_rows": int((~np.isfinite(merged[FEATURES].to_numpy(float)).all(axis=1)).sum()),
                "valid_one_hour_targets": int(merged.target_heat_index_1h_C.notna().sum()),
                "interpolation": "none", "operational_availability_verified": False}
    return merged, manifest


@dataclass
class Samples:
    x: np.ndarray
    y: np.ndarray
    persistence: np.ndarray
    origins: pd.DatetimeIndex
    targets: pd.DatetimeIndex
    input_starts: pd.DatetimeIndex
    rejected: dict


def make_sequences(frame: pd.DataFrame, length: int = 6) -> Samples:
    if length < 1:
        raise ValueError("Sequence length must be positive.")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if frame.timestamp.isna().any() or frame.timestamp.duplicated().any():
        raise ValueError("Sequence timestamps must be unique and valid.")
    xs, ys, bases, origins, targets, starts = [], [], [], [], [], []
    rejected = {"insufficient_context": min(length-1, len(frame)), "gapped_window": 0, "invalid_features": 0, "missing_target": 0}
    for end in range(length-1, len(frame)):
        window = frame.iloc[end-length+1:end+1]
        if not window.timestamp.diff().dropna().eq(pd.Timedelta(hours=1)).all():
            rejected["gapped_window"] += 1
            continue
        values = window[FEATURES].to_numpy(float)
        if not np.isfinite(values).all() or not np.isfinite(window.heat_index_C.iloc[-1]):
            rejected["invalid_features"] += 1
            continue
        row = window.iloc[-1]
        target_time = row.timestamp + pd.Timedelta(hours=1)
        actual_target = frame.loc[frame.timestamp == target_time, "heat_index_C"]
        if not np.isfinite(row.target_heat_index_1h_C) or len(actual_target) != 1 or not np.isfinite(actual_target.iloc[0]):
            rejected["missing_target"] += 1
            continue
        if not np.isclose(row.target_heat_index_1h_C, actual_target.iloc[0], atol=1e-9, rtol=0):
            raise ValueError("Stored target is not aligned to the next actual hour.")
        xs.append(values); ys.append(row.target_heat_index_1h_C); bases.append(row.heat_index_C)
        origins.append(row.timestamp); targets.append(target_time); starts.append(window.timestamp.iloc[0])
    return Samples(np.asarray(xs, float).reshape(-1, length, len(FEATURES)), np.asarray(ys, float),
                   np.asarray(bases, float), pd.DatetimeIndex(origins), pd.DatetimeIndex(targets),
                   pd.DatetimeIndex(starts), rejected)
