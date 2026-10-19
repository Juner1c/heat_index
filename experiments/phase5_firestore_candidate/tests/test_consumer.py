"""Validate response compatibility with the existing, unchanged FastAPI adapter."""
from pathlib import Path
import sys
from datetime import datetime,timezone

from application import create_app
from storage.factory import Settings


def test_existing_fastapi_iot_normalizer_accepts_candidate_responses(tmp_path):
    root=Path(__file__).resolve().parents[3]
    sys.path.insert(0,str(root/"heat_index_phase1"))
    try:
        from backend.schemas.iot import RenderLatest,RenderHistory,RenderHistoryRow
        from backend.services.iot import normalize_reading
        client=create_app(Settings(sqlite_path=tmp_path/"candidate.sqlite",model_path=tmp_path/"absent.pth")).test_client()
        assert client.post("/api/telemetry",json={"temperature":30,"humidity":70}).status_code==200
        raw=RenderLatest.model_validate(client.get("/api/v1/latest").json)
        normalized=normalize_reading(raw,datetime.now(timezone.utc),120,True)
        assert normalized.temperature_c==30 and normalized.humidity_percent==70
        assert normalized.experimental_forecast_c is None and normalized.freshness=="unknown"
        assert normalized.measurement_timestamp_utc is None and not normalized.issues
        history=RenderHistory.model_validate(client.get("/api/v1/history").json)
        RenderHistoryRow.model_validate(history.readings[0])
    finally:
        sys.path.pop(0)
