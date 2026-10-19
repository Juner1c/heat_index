"""Reproduce stored held-out predictions with saved scalers; never train models."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.services import datasets as ds
from backend.services.model_loader import FEATURES, load_model
from backend.services.preprocessing import source_frame


def error_metrics(actual, predicted) -> dict:
    error = np.asarray(predicted, dtype=float) - np.asarray(actual, dtype=float)
    return {"samples": len(error), "mae_c": float(np.abs(error).mean()), "rmse_c": float(np.sqrt(np.mean(error**2))), "mean_bias_c": float(error.mean())}


def replay(identifier: str) -> dict:
    loaded = load_model(identifier)
    frame = source_frame()
    length = loaded.metadata["sequence_length"]
    directory = "lnn_sequence_results" if length == 6 else "lnn_results"
    saved = ds.read_csv(ds.data_root() / directory / "test_predictions.csv")
    timestamp_column = "target_timestamp" if length == 6 else "timestamp"
    required = [timestamp_column, "actual_heat_index_1h_C", "predicted_heat_index_1h_C", "baseline_heat_index_1h_C"]
    if not set(required).issubset(saved):
        raise ValueError("The saved test predictions have an incompatible schema.")
    targets = pd.to_datetime(saved[timestamp_column], utc=True, errors="coerce", format="mixed")
    if length == 1:
        targets += pd.Timedelta(hours=1)
    if targets.isna().any() or targets.duplicated().any():
        raise ValueError("Saved forecast timestamps are invalid or duplicated.")
    indexed = frame.set_index("timestamp", verify_integrity=True)
    inputs, baseline, actual = [], [], []
    for target in targets:
        times = pd.date_range(end=target - pd.Timedelta(hours=1), periods=length, freq="h")
        window = indexed.reindex(times)
        values = window[FEATURES].to_numpy(dtype=float)
        if not np.isfinite(values).all() or target not in indexed.index:
            raise ValueError("Current source data cannot reproduce the saved test input windows.")
        inputs.append(values[-1] if length == 1 else values)
        baseline.append(window.iloc[-1]["heat_index_C"])
        actual.append(indexed.loc[target, "heat_index_C"])
    predicted = loaded.predict(np.asarray(inputs, dtype=np.float32) if length == 6 else np.asarray(inputs, dtype=np.float64))
    # Sequence training uses float32 inputs BEFORE the scaler is applied.
    saved_values = saved[required[1:]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(saved_values).all():
        raise ValueError("Saved test measurements are not finite.")
    prediction_difference = float(np.max(np.abs(predicted - saved_values[:, 1])))
    actual_difference = float(np.max(np.abs(np.asarray(actual) - saved_values[:, 0])))
    baseline_difference = float(np.max(np.abs(np.asarray(baseline) - saved_values[:, 2])))
    reproduced = prediction_difference <= 5e-5 and actual_difference <= 5e-5 and baseline_difference <= 5e-5
    return {
        "reproduced": reproduced, "model": identifier, "version": loaded.metadata["version"],
        "prediction_max_abs_difference_c": prediction_difference, "actual_max_abs_difference_c": actual_difference,
        "baseline_max_abs_difference_c": baseline_difference,
        "test_target_start": targets.min().isoformat(), "test_target_end": targets.max().isoformat(),
        "metrics": error_metrics(actual, predicted), "persistence": error_metrics(actual, baseline),
        "records": [{"timestamp": time.isoformat(), "actual_heat_index_c": float(observed), "predicted_heat_index_c": float(estimate), "persistence_heat_index_c": float(base)} for time, observed, estimate, base in zip(targets, actual, predicted, baseline)],
        "limitations": ["Small historical sample", "Chronological 80/20 split without an independent validation set", "Model selection based on training loss", "Retrospective replay, not prospective forecast validation"],
    }


def comparison() -> dict:
    single = replay("single_time_constant")
    sequence = replay("sequence_time_constant")
    merged = pd.DataFrame(single["records"]).merge(pd.DataFrame(sequence["records"]), on="timestamp", suffixes=("_single", "_sequence"), validate="one_to_one")
    if merged.empty or not np.allclose(merged["actual_heat_index_c_single"], merged["actual_heat_index_c_sequence"], atol=5e-5, rtol=0):
        raise ValueError("The saved test results cannot be aligned on a common target period.")
    actual = merged["actual_heat_index_c_single"]
    return {"start": merged["timestamp"].min(), "end": merged["timestamp"].max(), "samples": len(merged),
            "metrics": {"single_time_constant": error_metrics(actual, merged["predicted_heat_index_c_single"]),
                        "sequence_time_constant": error_metrics(actual, merged["predicted_heat_index_c_sequence"]),
                        "persistence": error_metrics(actual, merged["persistence_heat_index_c_single"])},
            "prospective_validation": False}
