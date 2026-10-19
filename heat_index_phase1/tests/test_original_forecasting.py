import ast
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from fastapi.testclient import TestClient
from torch import nn

from backend.main import app
from backend.services import datasets as ds
from backend.services.model_loader import FEATURES, ModelUnavailable, _load, load_model
from backend.services.model_audit import comparison, replay
from backend.services.model_training_audit import training_audit
from backend.services.preprocessing import source_frame
from backend.services.preprocessing import input_window
from fastapi import HTTPException


@pytest.fixture
def original_data(monkeypatch):
    monkeypatch.setenv("THERMOCAST_DATA_DIR", str(ds.DEFAULT_DATA_ROOT))
    for variable in ("HIMAWARI_CSV", "GROUND_WEATHER_CSV", "HEAT_INDEX_CSV"):
        monkeypatch.delenv(variable, raising=False)
    return TestClient(app)


@pytest.mark.parametrize("identifier,script,class_name", [
    ("single_time_constant", "train_lnn.py", "LiquidNeuralNetwork"),
    ("sequence_time_constant", "train_lnn_sequence.py", "SequenceLNN"),
])
def test_exact_original_architecture_and_saved_preprocessing(original_data, identifier, script, class_name):
    loaded = load_model(identifier)
    # Execute only the inspected class definitions, never top-level training code.
    tree = ast.parse((ds.DEFAULT_DATA_ROOT / script).read_text(encoding="utf-8-sig"))
    classes = ast.Module(body=[node for node in tree.body if isinstance(node, ast.ClassDef)], type_ignores=[])
    scope = {"torch": torch, "nn": nn}
    exec(compile(classes, script, "exec"), scope)
    reference = scope[class_name](input_size=7, hidden_size=24)
    reference.load_state_dict(loaded.model.state_dict(), strict=True)
    reference.eval()
    length = loaded.metadata["sequence_length"]
    raw = source_frame().tail(length)[FEATURES].to_numpy(dtype=float)
    inputs = raw[None, -1, :] if length == 1 else raw[None, :, :]
    normalized = torch.tensor((inputs - loaded.x_mean) / loaded.x_scale, dtype=torch.float32)
    with torch.inference_mode():
        assert torch.equal(reference(normalized), loaded.model(normalized))
    assert replay(identifier)["reproduced"]
    assert training_audit(identifier)["saved_scalers_match_training_only_statistics"]
    assert loaded.model.training is False


def test_real_forecast_horizon_timestamp_units_and_reproducibility(original_data):
    body = {"model": "sequence_time_constant", "forecast_horizon_hours": 1}
    first = original_data.post("/api/forecast/predict", json=body)
    second = original_data.post("/api/forecast/predict", json=body)
    assert first.status_code == 200
    result = first.json()
    assert result["predictions"] == second.json()["predictions"]
    assert result["forecast_horizon_hours"] == 1
    assert len(result["model_version"]) == 64
    assert result["forecast_mode"] == "historical_origin"
    assert result["scientifically_validated"] is False
    origin = pd.Timestamp(result["last_input_observation"])
    target = pd.Timestamp(result["predictions"][0]["timestamp"])
    assert target - origin == pd.Timedelta(hours=1)
    assert np.isfinite(result["predictions"][0]["predicted_heat_index_c"])
    history = original_data.get("/api/forecast/history?limit=10").json()
    assert len(history["records"]) == 10
    assert history["status"] == "retrospective_replay"
    assert history["issued_forecasts"]


def test_reject_invalid_horizons_ids_dates_gaps_and_request_sizes(original_data):
    for body in ({"model": "unknown"}, {"forecast_horizon_hours": 24}, {"as_of": "2024-08-01T12:00:00"}, {"checkpoint_path": "arbitrary.pth"}):
        assert original_data.post("/api/forecast/predict", json=body).status_code == 422
    response = original_data.post("/api/forecast/predict", json={"as_of": "2024-08-01T13:00:00Z"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "history_gaps"
    response = original_data.post("/api/forecast/predict", content=b" " * 4097, headers={"Content-Type": "application/json"})
    assert response.status_code == 413
    assert original_data.get("/api/forecast/history?limit=201").status_code == 422


def test_missing_checkpoint_is_unavailable_not_substituted(original_data, tmp_path, monkeypatch):
    monkeypatch.setenv("THERMOCAST_DATA_DIR", str(tmp_path))
    result = original_data.get("/api/models/status").json()
    assert result["inference_ready"] is False
    response = original_data.post("/api/forecast/predict", json={})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_unavailable"


def test_missing_scalers_are_rejected_without_refitting(original_data, tmp_path):
    checkpoint = torch.load(ds.DEFAULT_DATA_ROOT / "lnn_results/lnn_heat_index_model.pth", map_location="cpu", weights_only=True)
    checkpoint.pop("x_scaler_mean")
    destination = tmp_path / "incomplete.pth"
    torch.save(checkpoint, destination)
    stat = destination.stat()
    with pytest.raises(ModelUnavailable, match="metadata is missing"):
        _load(str(destination), stat.st_mtime_ns, stat.st_size, "single_time_constant")


def test_common_period_metrics_use_identical_targets(original_data):
    result = comparison()
    assert result["samples"] > 0
    assert result["prospective_validation"] is False
    baseline = result["metrics"]["persistence"]
    assert baseline["mae_c"] < result["metrics"]["single_time_constant"]["mae_c"]
    assert baseline["mae_c"] < result["metrics"]["sequence_time_constant"]["mae_c"]


def test_invalid_windows_and_wrong_tensor_shapes_are_rejected(original_data):
    model = load_model("sequence_time_constant")
    with pytest.raises(ModelUnavailable, match="dimensions"):
        model.predict(np.zeros((1, 5, 7)))
    frame = source_frame().tail(6).copy()
    frame.loc[frame.index[-1], "B13_mean_K"] = np.nan
    with pytest.raises(HTTPException) as result:
        input_window(frame, 6)
    assert result.value.detail["code"] == "features_invalid"
    frame = source_frame().tail(6).copy()
    frame.loc[frame.index[-1], "timestamp"] = frame.iloc[0]["timestamp"]
    with pytest.raises(HTTPException) as result:
        input_window(frame, 6)
    assert result.value.detail["code"] == "duplicate_timestamps"
