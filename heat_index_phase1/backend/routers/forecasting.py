from fastapi import APIRouter, Query

from backend.schemas.forecasting import ModelIdentifier, PredictRequest
from backend.services import datasets as ds

router = APIRouter(prefix="/api", tags=["Original model forecasting"])


@router.get("/models/status")
def status():
    try:
        from backend.services.forecasting import models_status
        return models_status()
    except ImportError:
        return {"phase": 3, "inference_ready": False, "status": "unavailable", "models": [], "message": "Install requirements-inference.txt to enable the original PyTorch models.", "requirements": ["PyTorch inference dependencies"]}


@router.get("/models/metadata")
def metadata():
    return status()


@router.post("/forecast/predict")
def forecast(request: PredictRequest):
    try:
        from backend.services.forecasting import predict
    except ImportError:
        ds.fail("dependencies_missing", "Install requirements-inference.txt to enable PyTorch inference.", 503)
    return predict(request.model, request.as_of)


@router.get("/forecast/history")
def forecast_history(model: ModelIdentifier = "sequence_time_constant", limit: int = Query(50, ge=1, le=200)):
    try:
        from backend.services.forecasting import ISSUED_FORECASTS, model_readiness
        from backend.services.model_audit import replay
    except ImportError:
        ds.fail("dependencies_missing", "Install requirements-inference.txt to inspect forecast history.", 503)
    ready = model_readiness(model)
    if not ready["inference_ready"]:
        ds.fail("model_unavailable", ready["message"], 503)
    audit = replay(model)
    return {"model": model, "status": "retrospective_replay", "evaluation": {key: value for key, value in audit.items() if key != "records"},
            "records": audit["records"][-limit:], "issued_forecasts": [item for item in reversed(ISSUED_FORECASTS) if item["model"] == model][:limit],
            "issued_history_storage": "Process memory only; cleared on backend restart"}
