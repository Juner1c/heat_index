from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from research.phase4.common import FEATURES, sha256, write_json
from research.phase4.models.baseline_mlp import WindowMLP
from research.phase4.models.canonical_ltc import CanonicalLTC
from research.phase4.models.canonical_cfc import CanonicalCfC


def create_model(identifier: str, config: dict):
    if identifier == "mlp":
        return WindowMLP(len(FEATURES), config["hidden_size"], config["sequence_length"])
    if identifier == "ltc":
        return CanonicalLTC(len(FEATURES), config["hidden_size"], config["ode_unfolds"])
    if identifier == "cfc":
        return CanonicalCfC(len(FEATURES), config["hidden_size"])
    raise ValueError("Unknown Phase 4 experimental model.")


def save_checkpoint(directory: Path, model, metadata: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    weights = directory / "weights.pt"
    torch.save({key: value.detach().cpu().clone() for key, value in model.state_dict().items()}, weights)
    result = {**metadata, "artifact_format": "thermocast-phase4-v1", "model_version": sha256(weights)}
    write_json(directory / "metadata.json", result)
    return result


def load_checkpoint(directory: Path):
    metadata = json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
    if metadata["artifact_format"] != "thermocast-phase4-v1" or metadata["features"] != FEATURES or metadata["forecast_horizon_hours"] != 1:
        raise ValueError("Incompatible Phase 4 inference metadata.")
    config = metadata["training_config"]
    if metadata["sequence_length"] != config["sequence_length"] or not 1 <= config["sequence_length"] <= 168 or not 1 <= config["hidden_size"] <= 256:
        raise ValueError("Invalid experimental architecture dimensions.")
    weights = directory / "weights.pt"
    if weights.stat().st_size > 20_000_000 or sha256(weights) != metadata["model_version"]:
        raise ValueError("Experimental checkpoint integrity check failed.")
    model = create_model(metadata["model"], config)
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True), strict=True)
    if not all(torch.isfinite(value).all() for value in model.state_dict().values()):
        raise ValueError("Nonfinite experimental weights.")
    model.eval()
    from research.phase4.training.scaling import Scaling
    scaler = Scaling.from_dict(metadata["scaling"])
    return model, scaler, metadata


def predict_checkpoint(directory: Path, windows: np.ndarray) -> np.ndarray:
    model, scaler, metadata = load_checkpoint(directory)
    values = np.asarray(windows, dtype=float)
    if values.ndim != 3 or values.shape[1:] != (metadata["sequence_length"], len(FEATURES)) or not len(values) or not np.isfinite(values).all():
        raise ValueError("Prediction requires complete finite windows in the saved feature order.")
    with torch.inference_mode():
        output = model(torch.from_numpy(scaler.transform_x(values))).numpy()
    result = scaler.inverse_y(output)
    if not np.isfinite(result).all():
        raise ValueError("Nonfinite experimental predictions.")
    return result
