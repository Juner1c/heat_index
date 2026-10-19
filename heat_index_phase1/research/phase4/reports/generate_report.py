from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
import pandas as pd


def markdown_table(frame: pd.DataFrame) -> str:
    def cell(value):
        return f"{value:.6f}" if isinstance(value, float) else str(value).replace("|", "/")
    lines = ["| " + " | ".join(frame.columns) + " |", "| " + " | ".join(["---"]*len(frame.columns)) + " |"]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join(lines)


def make_figures(output: Path, histories: dict, records: pd.DataFrame, label: str):
    directory = output / "figures"
    directory.mkdir(exist_ok=True)
    for column, title, filename in [("train_mse_scaled", "Training loss", "training_loss.png"),
                                    ("validation_mse_scaled", "Validation loss", "validation_loss.png")]:
        fig, axis = plt.subplots(figsize=(9,4))
        for model, history in histories.items():
            data = pd.DataFrame(history)
            axis.plot(data.epoch, data[column], marker=".", label=model)
        axis.set(xlabel="Epoch", ylabel="MSE (standardized target units²)", title=f"{title} — {label}")
        axis.legend(); fig.tight_layout(); fig.savefig(directory/filename, dpi=140); plt.close(fig)
    fig, axis = plt.subplots(figsize=(11,5))
    observed = records.drop_duplicates("target_utc")
    axis.plot(pd.to_datetime(observed.target_utc, utc=True), observed.actual_heat_index_c, label="Actual", color="black", linewidth=2)
    for model, data in records.groupby("model", sort=False):
        axis.plot(pd.to_datetime(data.target_utc, utc=True), data.predicted_heat_index_c, label=model, alpha=.8)
    axis.set(xlabel="Target timestamp (UTC)", ylabel="Heat index (°C)", title=f"One-hour forecast comparison — {label}")
    axis.legend(fontsize=7, ncol=2); fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(directory/"forecast_comparison.png", dpi=140); plt.close(fig)
    fig, axis = plt.subplots(figsize=(9,5))
    for model, data in records.groupby("model", sort=False):
        axis.hist(data.residual_c, bins=12, histtype="step", label=model)
    axis.axvline(0, color="black", linewidth=.8)
    axis.set(xlabel="Prediction − actual heat index (°C)", ylabel="Count", title=f"Residual distribution — {label}")
    axis.legend(fontsize=8); fig.tight_layout(); fig.savefig(directory/"residual_distribution.png", dpi=140); plt.close(fig)


def research_summary(output: Path, result: dict, comparison: pd.DataFrame):
    splits = pd.DataFrame([{"partition": name, **value} for name, value in result["splits"].items()])
    holdout_note = ("These target dates were previously examined. This is not a newly untouched test set."
                    if result["test_previously_inspected"] else
                    "The configuration declares previously uninspected test dates; independent provenance and operational availability still require review.")
    text = f"""# Phase 4 model comparison — {result['run_id']}

Status: **{result['experiment_kind']}**. Promotion eligible: **false**.

This run is an engineering smoke test if labeled smoke_test, not scientific validation.
It did not change the ThermoCast forecasting service or original artifacts.

## Dataset and chronological partitions

Valid supervised sequence samples: {result['valid_samples']}; input length: {result['sequence_length']} hours; forecast horizon: 1 hour.
Dataset fingerprint: `{result['dataset_fingerprint']}`.

{markdown_table(splits)}

## Identical-target comparison

All rows use the same final target timestamps. Bias is prediction minus actual.
Historical references retain their original 80/20 training protocol; they are not controlled Phase 4 retraining comparisons.

{markdown_table(comparison[['model','protocol','samples','mae_c','rmse_c','mean_bias_c','r2']])}

## Limitations and next action

- Screening: {'; '.join(result['sufficiency']['reasons']) or 'Minimum numerical screening thresholds met; this alone does not prove validity.'}
- {holdout_note}
- Open-Meteo weather is retrospective gridded data, not verified local sensor observations. The raw export does not identify the exact originating model or publication times.
- Features are restricted by valid timestamp, but operational availability at issue time is unverified.
- Scalers use training windows/targets only; early stopping uses validation MSE only. Test scores never select epochs.
- Windows overlap historical context across splits; targets are disjoint. Earlier observations available at each origin may be reused as context.
- No confidence intervals, calibrated uncertainty, statistical superiority, or operational alert readiness is claimed.
- Collect additional aligned satellite/weather dates and reserve a new untouched holdout before model improvement decisions or Phase 5 deployment.

Full configuration, dependency versions, scaler values, periods, and dataset fingerprint are saved alongside each checkpoint.
See `dataset_audit.json`, `splits.json`, `metrics/`, `predictions/`, and `figures/` in this run.
"""
    (output/"reports"/"model_comparison.md").write_text(text, encoding="utf-8")
