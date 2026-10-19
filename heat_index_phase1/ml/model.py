from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import torch
from ncps.torch import LTC
from torch import nn

ARTIFACT_VERSION = 1


class HeatIndexLNN(nn.Module):
    def __init__(self, input_size: int, hidden_size: int = 32):
        super().__init__()
        self.ltc = LTC(input_size=input_size, units=hidden_size, return_sequences=False, batch_first=True)
        self.output = nn.Linear(hidden_size, 1)

    def forward(self, values: torch.Tensor) -> torch.Tensor:
        encoded, _ = self.ltc(values)
        return self.output(encoded).squeeze(-1)


def save_artifact(directory: Path, model: HeatIndexLNN, metadata: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), directory / "model.pt")
    (directory / "metadata.json").write_text(json.dumps({"artifact_version": ARTIFACT_VERSION, **metadata}, indent=2), encoding="utf-8")


def load_artifact(directory: Path) -> tuple[HeatIndexLNN, dict[str, Any]]:
    metadata_path, weights_path = directory / "metadata.json", directory / "model.pt"
    if not metadata_path.is_file() or not weights_path.is_file():
        raise ValueError("LNN artifact requires metadata.json and model.pt")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    required = {"artifact_version", "feature_columns", "sequence_length", "hidden_size", "feature_mean", "feature_scale", "target_mean", "target_scale"}
    missing = required.difference(metadata)
    if missing:
        raise ValueError(f"LNN metadata is missing: {', '.join(sorted(missing))}")
    if metadata["artifact_version"] != ARTIFACT_VERSION:
        raise ValueError(f"Unsupported artifact version: {metadata['artifact_version']}")
    model = HeatIndexLNN(len(metadata["feature_columns"]), int(metadata["hidden_size"]))
    model.load_state_dict(torch.load(weights_path, map_location="cpu", weights_only=True))
    model.eval()
    return model, metadata


def autoregressive_forecast(model: HeatIndexLNN, metadata: dict[str, Any], history: np.ndarray, horizon: int) -> list[float]:
    feature_columns = metadata["feature_columns"]
    target_index = feature_columns.index("heat_index_c")
    feature_mean = np.asarray(metadata["feature_mean"], dtype=np.float32)
    feature_scale = np.asarray(metadata["feature_scale"], dtype=np.float32)
    target_mean, target_scale = float(metadata["target_mean"]), float(metadata["target_scale"])
    window = history.astype(np.float32).copy()
    predictions = []
    with torch.no_grad():
        for _ in range(horizon):
            normalized = (window - feature_mean) / feature_scale
            prediction_scaled = model(torch.from_numpy(normalized).unsqueeze(0)).item()
            prediction = prediction_scaled * target_scale + target_mean
            predictions.append(float(prediction))
            next_row = window[-1].copy()
            next_row[target_index] = prediction
            window = np.concatenate([window[1:], next_row.reshape(1, -1)], axis=0)
    return predictions
