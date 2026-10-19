"""Inspect original chronological samples and compare saved scaler statistics.

This module performs no model training and fits no scalers.
"""
import numpy as np
import pandas as pd

from backend.services.model_loader import FEATURES, load_model
from backend.services.preprocessing import source_frame


def training_audit(identifier: str) -> dict:
    loaded = load_model(identifier)
    frame = source_frame()
    length = loaded.metadata["sequence_length"]
    sample_inputs, targets, origins = [], [], []
    for end in range(length - 1, len(frame) - 1):
        window = frame.iloc[end-length+1:end+1]
        current, next_row = frame.iloc[end], frame.iloc[end+1]
        if next_row["timestamp"] - current["timestamp"] != pd.Timedelta(hours=1):
            continue
        if not (window["timestamp"].diff().dropna() == pd.Timedelta(hours=1)).all():
            continue
        values = window[FEATURES].to_numpy(dtype=float)
        if not np.isfinite(values).all() or not np.isfinite(current["target_heat_index_1h_C"]):
            continue
        if not np.isclose(current["target_heat_index_1h_C"], next_row["heat_index_C"], atol=1e-8, rtol=0):
            raise ValueError("The stored one-hour target is misaligned with the next heat-index observation.")
        sample_inputs.append(values[-1] if length == 1 else values)
        targets.append(current["target_heat_index_1h_C"])
        origins.append(current["timestamp"])
    inputs = np.asarray(sample_inputs, dtype=np.float32 if length == 6 else np.float64)
    target_values = np.asarray(targets, dtype=np.float32 if length == 6 else np.float64)
    split = int(len(inputs) * .8)
    training = inputs[:split].reshape(-1, len(FEATURES)).astype(np.float64)
    y_training = target_values[:split].astype(np.float64)
    x_mean, x_scale = training.mean(axis=0), training.std(axis=0)
    x_scale[x_scale == 0] = 1
    y_mean, y_scale = y_training.mean(), y_training.std() or 1.0
    differences = {
        "input_mean": float(np.max(np.abs(x_mean - loaded.x_mean))),
        "input_scale": float(np.max(np.abs(x_scale - loaded.x_scale))),
        "output_mean": abs(float(y_mean) - loaded.y_mean), "output_scale": abs(float(y_scale) - loaded.y_scale),
    }
    return {
        "samples": len(inputs), "train_samples": split, "test_samples": len(inputs)-split,
        "train_input_end_start": origins[0].isoformat(), "train_input_end_end": origins[split-1].isoformat(),
        "train_target_start": (origins[0] + pd.Timedelta(hours=1)).isoformat(),
        "train_target_end": (origins[split-1] + pd.Timedelta(hours=1)).isoformat(),
        "test_target_start": (origins[split] + pd.Timedelta(hours=1)).isoformat(),
        "test_target_end": (origins[-1] + pd.Timedelta(hours=1)).isoformat(),
        "saved_scaler_max_differences": differences,
        "saved_scalers_match_training_only_statistics": all(value < 1e-8 for value in differences.values()),
        "split": "chronological 80/20; no independent validation set", "one_hour_targets_verified": True,
    }
