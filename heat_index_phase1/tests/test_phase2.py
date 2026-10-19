import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import datasets


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setenv("THERMOCAST_DATA_DIR", str(tmp_path))
    for variable in ("HIMAWARI_CSV", "GROUND_WEATHER_CSV", "HEAT_INDEX_CSV"):
        monkeypatch.delenv(variable, raising=False)
    (tmp_path / "mariveles_hourly").mkdir()
    satellite = tmp_path / "mariveles_hourly" / "himawari_mariveles_hourly.csv"
    pd.DataFrame({"timestamp": ["2024-08-01 00:00:00", "2024-08-01 02:00:00", "2024-08-01 02:00:00", "bad"],
                  "B08_mean_K": [230.5, float("inf"), 232.1, 233], "B13_mean_K": [280, 281, 281, 282]}).to_csv(satellite, index=False)
    weather = pd.DataFrame({"time": ["2024-08-01T00:00:00+00:00", "2024-08-01T01:00:00+00:00"],
                            "temperature_C": [27.4, 29.1], "humidity_percent": [86, 84]})
    weather.to_csv(tmp_path / "open_meteo_clean.csv", index=False)
    weather.rename(columns={"time": "timestamp"}).assign(heat_index_C=[31.446048, 35.943345]).to_csv(tmp_path / "heat_index_dataset.csv", index=False)
    return tmp_path, TestClient(app)


def test_satellite_integrity_json_safety_and_pagination(sources):
    root, client = sources
    summary = client.get("/api/himawari/summary").json()
    assert summary["total_records"] == 4
    assert summary["invalid_timestamps"] == 1
    assert summary["duplicate_timestamps"] == 1
    assert summary["missing_hours"] == 1
    assert summary["invalid_numeric_values"]["B08_mean_K"] == 1
    assert summary["source"] == "himawari_mariveles_hourly.csv"
    assert str(root) not in json.dumps(summary)
    response = client.get("/api/himawari/history?page_size=1&page=2")
    assert response.status_code == 200
    assert response.json()["records"][0]["B08_mean_K"] is None
    assert len(response.json()["records"]) == 1
    assert response.json()["total"] == 3
    assert client.get("/api/himawari/history?page_size=1001").status_code == 422
    assert client.get("/api/himawari/history?bands=B99").status_code == 422
    assert client.get("/api/himawari/history?start=2024-08-02&end=2024-08-01").status_code == 422
    assert client.get("/api/himawari/history?start=not-a-date").status_code == 422
    assert client.get("/api/himawari/history?start=2025-01-01").json()["total"] == 0
    assert "2024-08-01T01:00:00" in client.get("/api/himawari/missing-hours.csv").text


def test_ground_weather_and_heat_index_use_only_existing_columns(sources):
    _, client = sources
    weather = client.get("/api/weather/history").json()
    heat = client.get("/api/heat-index/history").json()
    assert weather["records"][0]["temperature_C"] == 27.4
    assert weather["metadata"]["provider"].startswith("Open-Meteo")
    assert heat["records"][0]["heat_index_C"] == 31.446048
    assert "Rothfusz" in heat["metadata"]["method"]
    assert "B13_mean_K" not in heat["columns"]
    assert client.get("/api/models/status").json()["inference_ready"] is False


def test_missing_file_schema_errors_and_refresh(sources):
    root, client = sources
    path = root / "open_meteo_clean.csv"
    path.unlink()
    response = client.get("/api/weather/history")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "source_missing"
    assert str(root) not in response.text
    pd.DataFrame({"time": ["2024-08-01"], "satellite_temperature_K": [280]}).to_csv(path, index=False)
    assert client.get("/api/weather/history").json()["detail"]["code"] == "schema_invalid"
    pd.DataFrame({"time": ["2024-08-01"], "temperature_C": [25], "humidity_percent": [70]}).to_csv(path, index=False)
    assert client.get("/api/weather/history").json()["total"] == 1
    pd.DataFrame({"time": ["2024-08-01", "2024-08-02"], "temperature_C": [25, 26], "humidity_percent": [70, 71]}).to_csv(path, index=False)
    assert client.get("/api/weather/history").json()["total"] == 2


def test_large_chart_aggregation_and_timezone_filtering(sources):
    root, client = sources
    count = 5000
    pd.DataFrame({"time": pd.date_range("2024-01-01", periods=count, freq="h", tz="UTC"), "temperature_C": [25.] * count,
                  "humidity_percent": [75.] * count}).to_csv(root / "open_meteo_clean.csv", index=False)
    result = client.get("/api/weather/history?max_points=100&page_size=10").json()
    assert len(result["chart"]) <= 100
    assert len(result["records"]) == 10
    assert result["chart"][0]["temperature_C"] == 25
    assert result["chart_aggregation"] != "observed"
    result = client.get("/api/weather/history?start=2024-01-01T08:00:00%2B08:00&end=2024-01-01T09:00:00%2B08:00").json()
    assert result["total"] == 2
    assert result["records"][0]["timestamp"] == "2024-01-01T00:00:00+00:00"


def test_cors_and_report_path_validation(sources):
    _, client = sources
    result = client.options("/api/health", headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "GET"})
    assert result.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert client.get("/api/himawari/reports/arbitrary.txt").status_code == 422


def test_heat_index_requires_valid_ground_weather_inputs(sources):
    root, client = sources
    pd.DataFrame({"timestamp": ["2024-08-01"], "temperature_C": ["invalid"], "humidity_percent": [150],
                  "heat_index_C": [35]}).to_csv(root / "heat_index_dataset.csv", index=False)
    result = client.get("/api/heat-index/history")
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "measurements_unavailable"
