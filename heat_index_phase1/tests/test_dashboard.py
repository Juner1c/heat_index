from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from backend.main import app

APP_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "historical.py"


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    source = tmp_path / "satellite.csv"
    pd.DataFrame({
        "timestamp": pd.date_range("2024-08-01", periods=48, freq="h", tz="UTC"),
        "B08_mean_K": [230.0] * 48,
        "B13_mean_K": [280.0] * 48,
    }).to_csv(source, index=False)
    monkeypatch.setenv("WEATHER_CSV", str(source))
    monkeypatch.delenv("COLLECTION_START", raising=False)
    monkeypatch.delenv("COLLECTION_END", raising=False)
    monkeypatch.syspath_prepend(str(APP_PATH.parent))
    client = TestClient(app)
    monkeypatch.setattr("requests.get", lambda url, **kwargs: client.get(url.split(":8000", 1)[-1]))
    result = AppTest.from_file(str(APP_PATH), default_timeout=15).run()
    assert not result.exception
    return result


def test_empty_measurements_explain_missing_chart_and_restore_defaults(dashboard):
    dashboard.multiselect[0].set_value([]).run()
    assert not dashboard.exception
    assert any("Select at least one measurement" in item.value for item in dashboard.info)
    restore = next(button for button in dashboard.button if button.label == "Restore default measurements")
    restore.click().run()
    assert dashboard.multiselect[0].value == ["B08_mean_K", "B13_mean_K"]


def test_unfinished_date_range_does_not_silently_show_full_history(dashboard):
    dashboard.date_input[0].set_value((pd.Timestamp("2024-08-01").date(),)).run()
    assert not dashboard.exception
    assert any("Choose an end date" in item.value for item in dashboard.info)
    assert not any("Showing 48" in item.value for item in dashboard.caption)


def test_measurement_selection_survives_manual_refresh(dashboard):
    dashboard.multiselect[0].set_value(["B13_mean_K"]).run()
    next(button for button in dashboard.button if button.label == "Refresh dataset").click().run()
    assert not dashboard.exception
    assert dashboard.multiselect[0].value == ["B13_mean_K"]


def test_spectral_band_selection_can_be_restored(dashboard):
    dashboard.multiselect[1].set_value([]).run()
    assert any("Select at least one spectral band" in item.value for item in dashboard.info)
    next(button for button in dashboard.button if button.label == "Restore default bands").click().run()
    assert not dashboard.exception
    assert dashboard.multiselect[1].value == ["B08_mean_K", "B13_mean_K"]
