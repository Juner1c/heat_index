from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import uuid

import numpy as np
import pandas as pd
import torch
from fastapi import HTTPException

from backend.services.datasets import data_root
from backend.services.model_audit import replay
from research.phase4.common import APP_ROOT, CONFIG_PATH, FEATURES, dependency_versions, load_config, source_paths, write_json
from research.phase4.data.dataset_builder import build_dataset, make_sequences
from research.phase4.data.temporal_split import chronological_split, split_metadata, sufficiency
from research.phase4.data.validation import audit_csv
from research.phase4.models.artifacts import predict_checkpoint, save_checkpoint
from research.phase4.models.persistence import predict as persistence
from research.phase4.reports.generate_report import make_figures, research_summary
from research.phase4.training.evaluate import grouped_errors, metrics, prediction_records
from research.phase4.training.train import train_model


def audit(config: dict) -> tuple:
    satellite, weather = source_paths(config)
    frame, manifest = build_dataset(satellite, weather, config["data"]["provenance"])
    samples = make_sequences(frame, config["sequence_length"])
    splits = chronological_split(samples.targets, **config["split"])
    report = {"datasets": [audit_csv(path, "timestamp") for path in satellite] + [audit_csv(path, "time") for path in weather],
              "manifest": manifest, "valid_single_observation_samples": len(make_sequences(frame, 1).y),
              "valid_sequence_samples": len(samples.y), "rejected_sequence_origins": samples.rejected,
              "splits": split_metadata(samples, splits), "sufficiency": sufficiency(samples, splits, config["minimum"])}
    # Read-only verification of archived preparation outputs; never write them.
    report["archived_sources"] = []
    report["archived_reconstruction_checks"] = {}
    for filename in ("merged_weather_dataset.csv", "heat_index_dataset.csv"):
        path = data_root()/filename
        if not path.is_file():
            continue
        report["archived_sources"].append(audit_csv(path, "timestamp"))
        existing = pd.read_csv(path)
        existing["timestamp"] = pd.to_datetime(existing.timestamp, utc=True, format="mixed")
        columns = [*FEATURES, *(["heat_index_C", "target_heat_index_1h_C"] if filename.startswith("heat") else [])]
        aligned = frame.merge(existing[["timestamp", *columns]], on="timestamp", validate="one_to_one", suffixes=("_rebuilt", "_archived"))
        checks = {}
        for column in columns:
            a, b = aligned[column+"_rebuilt"].to_numpy(float), aligned[column+"_archived"].to_numpy(float)
            finite = np.isfinite(a) & np.isfinite(b)
            checks[column] = {"compared": int(finite.sum()), "max_abs_difference": float(np.max(np.abs(a[finite]-b[finite]))) if finite.any() else None,
                              "missingness_matches": bool(np.array_equal(np.isnan(a), np.isnan(b)))}
        report["archived_reconstruction_checks"][filename] = {"overlap_rows": len(aligned), "columns": checks}
    return frame, manifest, samples, splits, report


def new_run_directory(label: str, root: Path | None = None) -> Path:
    root = root or APP_ROOT/"experiments"/"phase4"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + label + "_" + uuid.uuid4().hex[:8]
    output = root/run_id
    output.mkdir(parents=True, exist_ok=False)
    for directory in ("checkpoints", "metrics", "predictions", "figures", "reports"):
        (output/directory).mkdir()
    return output


def historical_reference_predictions(samples, test_ids) -> tuple[dict, dict]:
    predictions, details = {}, {}
    for identifier in ("single_time_constant", "sequence_time_constant"):
        try:
            result = replay(identifier)
            records = pd.DataFrame(result["records"])
            records["timestamp"] = pd.to_datetime(records.timestamp, utc=True)
            expected = samples.targets[test_ids]
            # Only use the checkpoint's original held-out targets, never its training targets.
            aligned = records.set_index("timestamp").reindex(expected)
            if not result["reproduced"] or aligned.isna().any().any() or not np.allclose(aligned.actual_heat_index_c, samples.y[test_ids], rtol=0, atol=5e-5):
                raise ValueError("Phase 4 targets are not entirely within verified original held-out records.")
            predictions[identifier] = aligned.predicted_heat_index_c.to_numpy(float)
            details[identifier] = {"status": "historical_reference_only", "checkpoint_version": result["version"],
                                   "note": "Original training/split differs; not a controlled architecture comparison."}
        except (ValueError, OSError, KeyError, HTTPException) as exc:
            details[identifier] = {"status": "excluded", "reason": str(exc)}
    return predictions, details


def execute(config: dict, *, smoke: bool, audit_only: bool = False, root: Path | None = None,
            prepared=None, splits_override=None, historical_references: bool = True) -> Path:
    frame, manifest, samples, splits, audit_report = prepared or audit(config)
    if splits_override is not None:
        splits = splits_override
    screening = sufficiency(samples, splits, config["minimum"])
    if not audit_only and not smoke and (not screening["screening_passed"] or config["evaluation"]["final_test_previously_inspected"]):
        raise ValueError("Dataset or holdout is insufficient for a validation experiment. Use --smoke for engineering checks, or collect new data and pre-register its protocol.")
    label = "audit" if audit_only else "smoke" if smoke else "retrospective"
    output = new_run_directory(label, root)
    status = {"run_id": output.name, "status": "running", "experiment_kind": "audit_only" if audit_only else "smoke_test" if smoke else "retrospective_experiment",
              "promotion_eligible": False}
    write_json(output/"run_status.json", status)
    try:
        write_json(output/"config.json", config)
        write_json(output/"reports"/"dataset_audit.json", audit_report)
        write_json(output/"reports"/"dataset_manifest.json", manifest)
        write_json(output/"reports"/"splits.json", split_metadata(samples, splits))
        frame.to_csv(output/"predictions"/"prepared_dataset.csv", index=False)
        pd.DataFrame({"timestamp_utc": pd.date_range(frame.timestamp.min(), frame.timestamp.max(), freq="h")}).assign(
            observed=lambda data: data.timestamp_utc.isin(frame.timestamp)).to_csv(output/"reports"/"hourly_coverage.csv", index=False)
        if audit_only:
            write_json(output/"run_status.json", {**status, "status": "completed"})
            return output
        # Smoke runs are bounded; the default fixed config executes at most eight epochs.
        if smoke and config["epochs"] > 10:
            raise ValueError("Smoke experiments are limited to ten epochs; use an explicitly registered larger-data experiment for substantial training.")
        versions = dependency_versions()
        metadata = {"features": FEATURES, "sequence_length": config["sequence_length"], "forecast_horizon_hours": 1,
                    "output_units": "°C", "input_time_unit": "hour", "dataset_fingerprint": manifest["dataset_fingerprint"],
                    "source_manifest": manifest, "training_config": config, "splits": split_metadata(samples, splits),
                    "dependency_versions": versions, "seed": config["seed"], "experiment_kind": status["experiment_kind"],
                    "created_at_utc": datetime.now(timezone.utc).isoformat(), "promotion_eligible": False,
                    "hidden_state_policy": "reset to zero per input window", "scaler_fit": "training-only flattened overlapping windows, population std"}
        histories, trained, training_details = {}, {}, {}
        # All epochs/checkpoints are selected before reading final test outputs.
        for identifier in config["models"]:
            print(f"Training separate Phase 4 {identifier} ({status['experiment_kind']})", flush=True)
            model, scaler, history, details = train_model(identifier, samples, splits, config)
            checkpoint = output/"checkpoints"/identifier
            saved = save_checkpoint(checkpoint, model, {**metadata, "model": identifier, "architecture": type(model).__name__,
                                                       "scaling": scaler.to_dict(), "training_result": details})
            with torch.inference_mode():
                expected = scaler.inverse_y(model(torch.from_numpy(scaler.transform_x(samples.x[splits["validation"]]))).numpy())
            reconstructed = predict_checkpoint(checkpoint, samples.x[splits["validation"]])
            if not np.allclose(expected, reconstructed, rtol=0, atol=1e-7):
                raise ValueError("Saved experimental checkpoint failed prediction round-trip.")
            histories[identifier], trained[identifier] = history, checkpoint
            training_details[identifier] = {**details, "model_version": saved["model_version"], "reload_verified": True}
            pd.DataFrame(history).to_csv(output/"metrics"/f"{identifier}_loss.csv", index=False)
        test_ids = splits["test"]
        predictions = {"persistence": persistence(samples.persistence[test_ids])}
        predictions.update({identifier: predict_checkpoint(path, samples.x[test_ids]) for identifier, path in trained.items()})
        references, reference_details = historical_reference_predictions(samples, test_ids) if historical_references else ({}, {})
        predictions.update(references)
        comparison = pd.DataFrame([{"model": model, "protocol": "original_historical_reference" if model in references else "phase4_smoke" if smoke else "phase4_retrospective",
                                    **metrics(samples.y[test_ids], values)} for model, values in predictions.items()])
        base_mae = float(comparison.loc[comparison.model == "persistence", "mae_c"].iloc[0])
        comparison["mae_skill_vs_persistence"] = 1-comparison.mae_c/base_mae if base_mae > 0 else np.nan
        comparison.to_csv(output/"metrics"/"model_comparison.csv", index=False)
        records = prediction_records(samples, test_ids, predictions)
        records.to_csv(output/"predictions"/"predicted_vs_actual.csv", index=False)
        for group in ("hour_utc", "heat_index_range_c"):
            grouped_errors(records, group).to_csv(output/"metrics"/f"error_by_{group}.csv", index=False)
        result = {**status, "status": "completed", "valid_samples": len(samples.y), "sequence_length": config["sequence_length"],
                  "dataset_fingerprint": manifest["dataset_fingerprint"], "splits": split_metadata(samples, splits), "sufficiency": screening,
                  "training": training_details, "historical_references": reference_details, "comparison": comparison.astype(object).where(pd.notna(comparison), None).to_dict("records"),
                  "test_previously_inspected": config["evaluation"]["final_test_previously_inspected"],
                  "prospectively_validated": False, "deployed_model_changed": False}
        make_figures(output, histories, records, status["experiment_kind"])
        research_summary(output, result, comparison)
        write_json(output/"reports"/"results.json", result)
        write_json(output/"run_status.json", {**status, "status": "completed"})
        return output
    except Exception as exc:
        write_json(output/"run_status.json", {**status, "status": "failed", "reason": str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description="Separate Phase 4 research. Never promotes a model or downloads data.")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    output = execute(load_config(args.config), smoke=args.smoke, audit_only=args.audit_only)
    print(f"Artifacts: {output}", flush=True)


if __name__ == "__main__":
    main()
