from __future__ import annotations

import numpy as np
import pandas as pd


def metrics(actual, predicted) -> dict:
    actual, predicted = np.asarray(actual, float), np.asarray(predicted, float)
    if actual.ndim != 1 or predicted.shape != actual.shape or not len(actual) or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require equal nonempty finite vectors on identical target timestamps.")
    error = predicted-actual
    total_variation = float(np.sum((actual-actual.mean())**2))
    return {"samples": len(actual), "mae_c": float(np.abs(error).mean()), "rmse_c": float(np.sqrt(np.mean(error**2))),
            "mean_bias_c": float(error.mean()), "r2": float(1-np.sum(error**2)/total_variation) if len(actual) >= 2 and total_variation > 1e-12 else None,
            "residual_p05_c": float(np.quantile(error, .05)), "residual_median_c": float(np.median(error)),
            "residual_p95_c": float(np.quantile(error, .95)), "max_abs_error_c": float(np.abs(error).max())}


def prediction_records(samples, ids, predictions: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = []
    for model, values in predictions.items():
        metrics(samples.y[ids], values)  # validates alignment dimensions and finiteness
        rows.extend({"model": model, "origin_utc": origin.isoformat(), "target_utc": target.isoformat(),
                     "actual_heat_index_c": float(actual), "predicted_heat_index_c": float(predicted), "residual_c": float(predicted-actual)}
                    for origin, target, actual, predicted in zip(samples.origins[ids], samples.targets[ids], samples.y[ids], values))
    return pd.DataFrame(rows)


def grouped_errors(records: pd.DataFrame, group: str) -> pd.DataFrame:
    data = records.copy()
    if group == "hour_utc":
        data[group] = pd.to_datetime(data.target_utc, utc=True).dt.hour
    elif group == "heat_index_range_c":
        data[group] = pd.cut(data.actual_heat_index_c, [-np.inf,27,32,41,54,np.inf], right=False,
                             labels=["<27", "27 to <32", "32 to <41", "41 to <54", ">=54"])
    else:
        raise ValueError("Unknown error grouping.")
    rows = [{"model": model, group: str(label), **metrics(values.actual_heat_index_c, values.predicted_heat_index_c)}
            for (model, label), values in data.groupby(["model", group], observed=True)]
    return pd.DataFrame(rows)
