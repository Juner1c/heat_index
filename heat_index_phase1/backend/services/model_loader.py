"""Exact, inference-only reconstructions of the two original training architectures.

Do not import train_lnn*.py: those scripts train and write artifacts at import time.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path

import numpy as np
import torch
from torch import nn

from backend.services.datasets import data_root

FEATURES = ["temperature_C", "humidity_percent", "dew_point_C", "B08_mean_K", "B13_mean_K", "B14_mean_K", "B15_mean_K"]
MODEL_FILES = {
    "single_time_constant": "lnn_results/lnn_heat_index_model.pth",
    "sequence_time_constant": "lnn_sequence_results/lnn_sequence_model.pth",
}


class ModelUnavailable(ValueError):
    pass


class LiquidCell(nn.Module):
    def __init__(self, input_size: int, hidden_size: int):
        super().__init__()
        self.input_layer = nn.Linear(input_size, hidden_size)
        self.recurrent_layer = nn.Linear(hidden_size, hidden_size)
        self.tau = nn.Parameter(torch.ones(hidden_size))

    def forward(self, x, hidden):
        tau = torch.nn.functional.softplus(self.tau) + 0.1
        candidate = torch.tanh(self.input_layer(x) + self.recurrent_layer(hidden))
        alpha = 1.0 - torch.exp(-1.0 / tau)
        return hidden + alpha * (candidate - hidden)


class OriginalTimeConstantRNN(nn.Module):
    def __init__(self, sequence_length: int, hidden_size: int = 24):
        super().__init__()
        self.sequence_length = sequence_length
        self.hidden_size = hidden_size
        self.cell = LiquidCell(len(FEATURES), hidden_size)
        self.output_layer = nn.Sequential(nn.Linear(hidden_size, 16), nn.Tanh(), nn.Linear(16, 1))

    def forward(self, values):
        hidden = torch.zeros(values.shape[0], self.hidden_size, dtype=values.dtype, device=values.device)
        if self.sequence_length == 1:
            hidden = self.cell(values, hidden)
        else:
            for step in range(values.shape[1]):
                hidden = self.cell(values[:, step, :], hidden)
        return self.output_layer(hidden)


@dataclass
class LoadedModel:
    model: OriginalTimeConstantRNN
    metadata: dict
    x_mean: np.ndarray
    x_scale: np.ndarray
    y_mean: float
    y_scale: float

    def predict(self, values: np.ndarray) -> np.ndarray:
        values = np.asarray(values)
        expected = (7,) if self.metadata["sequence_length"] == 1 else (6, 7)
        if values.ndim != len(expected) + 1 or values.shape[1:] != expected or not len(values) or not np.isfinite(values).all():
            raise ModelUnavailable("Inference inputs must be finite and match the audited feature and sequence dimensions.")
        normalized = np.array(values, dtype=np.float32 if self.metadata["sequence_length"] == 6 else np.float64, copy=True)
        normalized -= self.x_mean
        normalized /= self.x_scale
        tensor = torch.tensor(normalized, dtype=torch.float32, device="cpu")
        with torch.inference_mode():
            output = self.model(tensor).cpu().numpy().ravel()
        physical = output.copy()
        physical *= self.y_scale
        physical += self.y_mean
        if not np.isfinite(physical).all():
            raise ModelUnavailable("The checkpoint produced non-finite output.")
        return physical


def load_model(identifier: str) -> LoadedModel:
    if identifier not in MODEL_FILES:
        raise ModelUnavailable("Unsupported model identifier.")
    path = data_root() / MODEL_FILES[identifier]
    if not path.is_file():
        raise ModelUnavailable("The selected original checkpoint is missing.")
    stat = path.stat()
    try:
        return _load(str(path.resolve()), stat.st_mtime_ns, stat.st_size, identifier)
    except ModelUnavailable:
        raise
    except Exception as exc:
        raise ModelUnavailable("The checkpoint could not be safely loaded with the original architecture.") from exc


@lru_cache(maxsize=4)
def _load(path: str, modified: int, size: int, identifier: str) -> LoadedModel:
    if size > 10_000_000:
        raise ModelUnavailable("The checkpoint exceeds the supported artifact size.")
    checkpoint = torch.load(path, map_location="cpu", weights_only=True)
    required = {"model_state_dict", "features", "hidden_size", "x_scaler_mean", "x_scaler_scale", "y_scaler_mean", "y_scaler_scale"}
    if not isinstance(checkpoint, dict) or not required.issubset(checkpoint):
        raise ModelUnavailable("Checkpoint preprocessing or architecture metadata is missing.")
    length = 6 if identifier == "sequence_time_constant" else 1
    if checkpoint["features"] != FEATURES or checkpoint["hidden_size"] != 24 or checkpoint.get("sequence_length", 1) != length:
        raise ModelUnavailable("Checkpoint feature order, hidden size, or sequence length does not match the audited training code.")
    arrays = [np.asarray(checkpoint[key], dtype=np.float64) for key in ("x_scaler_mean", "x_scaler_scale", "y_scaler_mean", "y_scaler_scale")]
    if any(array.shape != shape for array, shape in zip(arrays, [(7,), (7,), (1,), (1,)])):
        raise ModelUnavailable("Saved scaler shapes are incompatible.")
    if not all(np.isfinite(array).all() for array in arrays) or (arrays[1] <= 0).any() or arrays[3][0] <= 0:
        raise ModelUnavailable("Saved scaler values must be finite, with positive scales.")
    model = OriginalTimeConstantRNN(length)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    if not all(torch.isfinite(parameter).all() for parameter in model.parameters()):
        raise ModelUnavailable("The checkpoint contains non-finite weights.")
    model.eval()
    version = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    metadata = {
        "identifier": identifier, "version": version, "checkpoint": Path(path).name,
        "architecture": "custom time-constant RNN (continuous-time-inspired; not canonical LTC or CfC)",
        "hidden_size": 24, "head": "Linear(24,16) → Tanh → Linear(16,1)",
        "sequence_length": length, "forecast_horizon_hours": 1,
        "features": FEATURES, "target": "target_heat_index_1h_C", "output_units": "°C", "device": "cpu",
        "preprocessing": "Saved StandardScaler means/scales; no fitting at inference",
        "x_scaler_mean": arrays[0].tolist(), "x_scaler_scale": arrays[1].tolist(),
        "y_scaler_mean": arrays[2].tolist(), "y_scaler_scale": arrays[3].tolist(),
        "classification_note": "The single-observation model resets hidden state every row; only the six-hour model carries state across input observations.",
    }
    return LoadedModel(model, metadata, arrays[0], arrays[1], float(arrays[2][0]), float(arrays[3][0]))
