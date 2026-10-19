"""Read and validate inference inputs without fitting scalers or filling features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services import datasets as ds
from backend.services.model_loader import FEATURES


def source_frame() -> pd.DataFrame:
    raw = ds.read_csv(ds.source_path("heat-index"))
    required = ["timestamp", *FEATURES, "heat_index_C", "target_heat_index_1h_C"]
    if any(column not in raw for column in required):
        ds.fail("features_missing", "The model dataset is missing required ground-weather, satellite, or target columns.")
    frame = raw[required].copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce", format="mixed")
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return frame.sort_values("timestamp", kind="stable").reset_index(drop=True)


def input_window(frame: pd.DataFrame, length: int, as_of=None) -> pd.DataFrame:
    if frame["timestamp"].isna().any():
        ds.fail("invalid_timestamps", "The model source contains invalid timestamps; repair the source pipeline before forecasting.")
    if frame["timestamp"].duplicated().any():
        ds.fail("duplicate_timestamps", "The model source contains duplicate timestamps; resolve them before forecasting.")
    if as_of is not None:
        cutoff = pd.Timestamp(as_of)
        if cutoff.tzinfo is None:
            ds.fail("timezone_required", "The forecast origin must include a UTC offset.")
        frame = frame[frame["timestamp"] <= cutoff.tz_convert("UTC")]
    window = frame.tail(length)
    if len(window) != length:
        ds.fail("history_insufficient", f"The model requires {length} complete hourly observations.")
    if not np.isfinite(window[FEATURES].to_numpy(dtype=float)).all():
        ds.fail("features_invalid", "The most recent input window contains missing or invalid feature values. No values were filled or skipped.")
    if not window["humidity_percent"].between(0, 100).all() or not window["temperature_C"].between(-90, 60).all():
        ds.fail("features_out_of_range", "Ground-weather input values are outside the supported screening ranges.")
    if not (window[[column for column in FEATURES if column.endswith("_K")]] > 0).all().all():
        ds.fail("features_out_of_range", "Brightness temperatures in Kelvin must be positive.")
    if not (window["timestamp"].diff().dropna() == pd.Timedelta(hours=1)).all():
        ds.fail("history_gaps", "The selected model requires consecutive hourly input observations; the input window contains a gap.")
    return window
