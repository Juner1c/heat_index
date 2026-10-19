from pathlib import Path
import sys

import pandas as pd
from fastapi.testclient import TestClient

from backend.main import app, risk_level
from ml.model import HeatIndexLNN, save_artifact
from ml.train import main as train_main


def sample_csv(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "weather.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2026-05-01", periods=4, freq="h", tz="UTC"),
        "temperature_c": [31.0, 32.0, 33.0, 34.0],
        "relative_humidity": [70.0, 70.0, 65.0, 60.0],
    }).to_csv(path, index=False)
    monkeypatch.setenv("WEATHER_CSV", str(path))
    return path


def test_summary_and_derived_heat_index(tmp_path, monkeypatch):
    sample_csv(tmp_path, monkeypatch)
    client = TestClient(app)
    summary = client.get("/api/summary").json()
    assert summary["rows"] == 4
    assert summary["missing_hours"] == 0
    numeric = client.get("/api/numeric").json()
    assert "heat_index_c" in numeric["columns"]
    assert len(numeric["records"]) == 4
    quality = client.get("/api/quality").json()
    assert quality["status"] == "ready"
    assert quality["detected_columns"]["temperature"] == "temperature_c"
    assert quality["download_progress"]["observed_hours"] == 4
    report = client.get("/api/report").json()
    assert report["study_area"] == "Mariveles, Bataan, Philippines"
    assert report["dataset"]["rows"] == 4


def test_forecast_evaluation_and_alerts(tmp_path, monkeypatch):
    sample_csv(tmp_path, monkeypatch)
    client = TestClient(app)
    forecast = client.get("/api/forecast?horizon=6").json()
    assert forecast["model"] == "persistence_baseline"
    assert len(forecast["forecasts"]) == 6
    evaluation = client.get("/api/evaluation").json()
    assert evaluation["samples"] == 3
    assert evaluation["mae_c"] >= 0
    assert evaluation["split_policy"] == "chronological_70_15_15"
    assert [split["name"] for split in evaluation["splits"]] == ["train", "validation", "test"]
    assert sum(split["samples"] for split in evaluation["splits"]) == 3
    assert len(evaluation["recent_errors"]) == 3
    alerts = client.get("/api/alerts?horizon=2").json()["alerts"]
    assert len(alerts) == 2
    assert all(item["risk_level"] in {"normal", "caution", "extreme_caution", "danger", "extreme_danger"} for item in alerts)


def test_validation_and_categories(tmp_path, monkeypatch):
    sample_csv(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.get("/api/forecast?horizon=0").status_code == 422
    assert risk_level(26.9)[0] == "normal"
    assert risk_level(27)[0] == "caution"
    assert risk_level(33)[0] == "extreme_caution"
    assert risk_level(42)[0] == "danger"
    assert risk_level(52)[0] == "extreme_danger"


def test_configured_download_progress(tmp_path, monkeypatch):
    sample_csv(tmp_path, monkeypatch)
    monkeypatch.setenv("COLLECTION_START", "2026-05-01T00:00:00Z")
    monkeypatch.setenv("COLLECTION_END", "2026-05-01T07:00:00Z")
    progress = TestClient(app).get("/api/quality").json()["download_progress"]
    assert progress == {"observed_hours": 4, "expected_hours": 8, "completion_pct": 50.0, "configured": True}


def test_validated_lnn_artifact_is_used(tmp_path, monkeypatch):
    sample_csv(tmp_path, monkeypatch)
    artifact = tmp_path / "lnn"
    model = HeatIndexLNN(input_size=3, hidden_size=4)
    save_artifact(artifact, model, {
        "model_type": "liquid_time_constant",
        "feature_columns": ["temperature_c", "relative_humidity", "heat_index_c"],
        "sequence_length": 2,
        "hidden_size": 4,
        "feature_mean": [32.0, 66.0, 40.0],
        "feature_scale": [1.0, 5.0, 5.0],
        "target_mean": 40.0,
        "target_scale": 5.0,
        "split_policy": "chronological_70_15_15",
        "metrics": {},
    })
    monkeypatch.setenv("LNN_MODEL_PATH", str(artifact))
    client = TestClient(app)
    status = client.get("/api/model/status").json()
    assert status["lnn_ready"] is True
    response = client.get("/api/forecast?horizon=2&model=lnn")
    assert response.status_code == 200
    assert response.json()["model"] == "lnn"
    assert len(response.json()["forecasts"]) == 2


def test_training_pipeline_writes_loadable_artifact(tmp_path, monkeypatch):
    csv_path = tmp_path / "training.csv"
    artifact = tmp_path / "trained"
    rows = 36
    pd.DataFrame({
        "timestamp": pd.date_range("2026-04-01", periods=rows, freq="h", tz="UTC"),
        "temperature_c": [29 + (index % 8) * 0.5 for index in range(rows)],
        "relative_humidity": [75 - (index % 6) * 2 for index in range(rows)],
    }).to_csv(csv_path, index=False)
    monkeypatch.setattr(sys, "argv", ["train", "--csv", str(csv_path), "--output", str(artifact), "--sequence-length", "4", "--hidden-size", "4", "--epochs", "1", "--batch-size", "8"])
    train_main()
    assert (artifact / "metadata.json").is_file()
    assert (artifact / "model.pt").is_file()
    monkeypatch.setenv("WEATHER_CSV", str(csv_path))
    monkeypatch.setenv("LNN_MODEL_PATH", str(artifact))
    response = TestClient(app).get("/api/forecast?horizon=2&model=lnn")
    assert response.status_code == 200
    assert len(response.json()["forecasts"]) == 2


def test_station_filtering_and_satellite_bands(tmp_path, monkeypatch):
    path = tmp_path / "stations.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2026-05-01", periods=6, freq="h", tz="UTC"),
        "station_name": ["Mariveles"] * 3 + ["Orion"] * 3,
        "latitude": [14.433] * 3 + [14.621] * 3,
        "longitude": [120.485] * 3 + [120.581] * 3,
        "temperature_c": [31, 32, 33, 29, 30, 31],
        "relative_humidity": [70, 68, 66, 75, 73, 71],
        "B13_mean": [290, 291, 292, 288, 289, 290],
        "ahi_b08": [0.20, 0.21, 0.22, 0.18, 0.19, 0.20],
    }).to_csv(path, index=False)
    monkeypatch.setenv("WEATHER_CSV", str(path))
    client = TestClient(app)
    station_response = client.get("/api/stations").json()
    assert [item["name"] for item in station_response["stations"]] == ["Mariveles", "Orion"]
    assert station_response["stations"][0]["rows"] == 3
    numeric = client.get("/api/numeric?station=Mariveles").json()
    assert len(numeric["records"]) == 3
    satellite = client.get("/api/satellite?station=Orion").json()
    assert satellite["bands"] == ["B13_mean", "ahi_b08"]
    assert len(satellite["records"]) == 3
    assert client.get("/api/forecast?station=Unknown").status_code == 404


def test_gap_details_duplicates_and_invalid_timestamps(tmp_path, monkeypatch):
    path = tmp_path / "gaps.csv"
    pd.DataFrame({
        "timestamp": ["2026-05-01T00:00:00Z", "2026-05-01T01:00:00Z", "2026-05-01T03:00:00Z", "2026-05-01T03:00:00Z", "not-a-date"],
        "temperature_c": [30, 31, 33, 33, 32],
        "relative_humidity": [70, 68, 65, 65, 67],
    }).to_csv(path, index=False)
    monkeypatch.setenv("WEATHER_CSV", str(path))
    client = TestClient(app)
    response = client.get("/api/gaps").json()
    assert response["missing_count"] == 1
    assert response["missing_timestamps"] == ["2026-05-01T02:00:00+00:00"]
    assert response["gap_periods"][0]["hours"] == 1
    assert response["duplicate_timestamps"] == ["2026-05-01T03:00:00+00:00"]
    assert response["invalid_rows"] == 1
    quality = client.get("/api/quality").json()
    assert quality["status"] == "attention_required"
    assert quality["column_profiles"][0]["complete_pct"] == 100.0


def test_quality_reports_out_of_range_weather_values(tmp_path, monkeypatch):
    path = tmp_path / "range.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2026-05-01", periods=3, freq="h", tz="UTC"),
        "temperature": [31.0, -80.0, 33.0],
        "humidity": [70.0, 150.0, 65.0],
        "heat_index": [35.0, -60.0, 38.0],
    }).to_csv(path, index=False)
    monkeypatch.setenv("WEATHER_CSV", str(path))
    quality = TestClient(app).get("/api/quality").json()
    assert "out_of_range_weather_values" in quality["issues"]
    assert {item["measure"] for item in quality["range_issues"]} == {"temperature_c", "relative_humidity_pct", "heat_index_c"}


def test_satellite_quality_flags_gaps_without_requiring_heat_index(tmp_path, monkeypatch):
    path = tmp_path / "satellite.csv"
    pd.DataFrame({
        "timestamp": ["2024-08-01 00:00:00", "2024-08-01 02:00:00"],
        "B08_mean_K": [230.5, 231.2],
        "B13_mean_K": [280.0, 281.0],
    }).to_csv(path, index=False)
    monkeypatch.setenv("WEATHER_CSV", str(path))
    client = TestClient(app)
    result = client.get("/api/quality").json()
    assert result["issues"] == ["missing_hours"]
    assert result["missing_hours"] == 1
    assert result["heat_index_available"] is False
    numeric = client.get("/api/numeric").json()
    assert numeric["columns"] == ["timestamp", "B08_mean_K", "B13_mean_K"]
    assert numeric["records"][0]["B08_mean_K"] == 230.5


def test_default_csv_is_anchored_to_project_and_refresh_reads_changes(tmp_path, monkeypatch):
    from backend import main

    path = tmp_path / "default.csv"
    monkeypatch.delenv("WEATHER_CSV", raising=False)
    monkeypatch.setattr(main, "DEFAULT_WEATHER_CSV", path)
    monkeypatch.chdir(tmp_path.parent)
    pd.DataFrame({"timestamp": ["2024-08-01 00:00:00"], "B13_mean_K": [280.0]}).to_csv(path, index=False)
    client = TestClient(app)
    assert client.get("/api/summary").json()["rows"] == 1
    assert client.get("/api/quality").json()["status"] == "ready"
    pd.DataFrame({"timestamp": ["2024-08-01 00:00:00", "2024-08-01 01:00:00"], "B13_mean_K": [280.0, 281.0]}).to_csv(path, index=False)
    assert client.get("/api/summary").json()["rows"] == 2
