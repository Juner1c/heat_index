from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.phase4.common import sha256


def normalize_timestamps(values) -> pd.Series:
    """Offset-bearing timestamps convert to UTC; naive source values assume UTC."""
    return pd.to_datetime(values, utc=True, errors="coerce", format="mixed")


def audit_csv(path: Path, timestamp_column: str) -> dict:
    raw = pd.read_csv(path)
    times = normalize_timestamps(raw[timestamp_column])
    unique = pd.DatetimeIndex(times.dropna().unique()).sort_values()
    hourly = unique[unique == unique.floor("h")]
    expected = pd.date_range(hourly.min(), hourly.max(), freq="h") if len(hourly) else pd.DatetimeIndex([])
    missing = expected.difference(hourly)
    numeric = raw.drop(columns=[timestamp_column]).apply(pd.to_numeric, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    return {
        "source": path.name, "sha256": sha256(path), "rows": len(raw),
        "start_utc": unique.min().isoformat() if len(unique) else None,
        "end_utc": unique.max().isoformat() if len(unique) else None,
        "unique_timestamps": len(unique), "unique_hourly_timestamps": len(hourly),
        "invalid_timestamps": int(times.isna().sum()),
        "non_hourly_timestamps": int((times.notna() & (times != times.dt.floor("h"))).sum()),
        "duplicate_timestamps": int(times.dropna().duplicated().sum()),
        "expected_hours": len(expected), "missing_hours": len(missing),
        "missing_timestamps_utc": [x.isoformat() for x in missing],
        "coverage_percent": 100 * len(hourly) / len(expected) if len(expected) else 0,
        "missing_cells": {str(k): int(v) for k, v in raw.isna().sum().items()},
        "nonfinite_numeric_cells": {column: int((~np.isfinite(values[:, i])).sum()) for i, column in enumerate(numeric)},
        "numeric_ranges": {column: {"min": float(numeric[column].replace([np.inf, -np.inf], np.nan).min()),
                                     "max": float(numeric[column].replace([np.inf, -np.inf], np.nan).max())}
                           for column in numeric if np.isfinite(values[:, list(numeric).index(column)]).any()},
    }


def read_hourly(paths: list[Path], timestamp_column: str, required: list[str]) -> pd.DataFrame:
    if not paths:
        raise ValueError("At least one configured local source is required.")
    frames = []
    for path in paths:
        frame = pd.read_csv(path)
        if not {timestamp_column, *required}.issubset(frame):
            raise ValueError(f"Missing required columns in {path.name}.")
        frame = frame[[timestamp_column, *required]].rename(columns={timestamp_column: "timestamp"})
        frame["timestamp"] = normalize_timestamps(frame["timestamp"])
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    if combined["timestamp"].isna().any():
        raise ValueError("Invalid source timestamps; inspect the dataset audit.")
    if combined["timestamp"].duplicated().any():
        raise ValueError("Duplicate source timestamps, including overlapping files, require explicit resolution.")
    if (combined["timestamp"] != combined["timestamp"].dt.floor("h")).any():
        raise ValueError("Off-hour observations require an explicitly approved aggregation method.")
    for column in required:
        combined[column] = pd.to_numeric(combined[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return combined.sort_values("timestamp").reset_index(drop=True)
