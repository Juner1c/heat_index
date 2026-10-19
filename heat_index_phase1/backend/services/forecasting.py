from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backend.services import datasets as ds
from backend.services.model_loader import FEATURES, MODEL_FILES, ModelUnavailable, load_model
from backend.services.model_audit import replay
from backend.services.preprocessing import input_window, source_frame

ISSUED_FORECASTS: deque = deque(maxlen=100)


def model_readiness(identifier: str) -> dict:
    try:
        loaded = load_model(identifier)
        audit = replay(identifier)
        if not audit["reproduced"]:
            raise ModelUnavailable("The checkpoint does not reproduce the saved held-out predictions with the current data.")
        window = input_window(source_frame(), loaded.metadata["sequence_length"])
        return {"identifier": identifier, "inference_ready": True, "status": "prototype_ready", "metadata": loaded.metadata,
                "last_input_observation": window.iloc[-1]["timestamp"].isoformat(),
                "evaluation": {key: value for key, value in audit.items() if key != "records"},
                "message": "Original checkpoint and saved preprocessing reproduce retrospective test predictions. Prospective validation is pending."}
    except Exception as exc:
        # HTTP dataset errors are safe structured messages; avoid internal paths or pickle details.
        detail = getattr(exc, "detail", None)
        reason = detail.get("message") if isinstance(detail, dict) else str(exc) if isinstance(exc, (ModelUnavailable, ValueError)) else "Model prerequisites could not be verified."
        return {"identifier": identifier, "inference_ready": False, "status": "unavailable", "message": reason}


def models_status() -> dict:
    models = [model_readiness(identifier) for identifier in MODEL_FILES]
    ready = any(item["inference_ready"] for item in models)
    return {"phase": 3, "inference_ready": ready, "status": "prototype_ready" if ready else "unavailable", "models": models,
            "artifacts_present": [path for path in MODEL_FILES.values() if (ds.data_root() / path).is_file()],
            "message": "Original-model inference is available for one-hour historical-origin forecasts." if ready else "AI forecasting is unavailable: required checkpoint, preprocessing, or source-data verification failed.",
            "prospective_validation": False,
            "requirements": ["Evaluate on additional held-out dates", "Collect new temporally aligned weather and satellite observations", "Validate performance against persistence before deployment"]}


def predict(identifier: str, as_of=None) -> dict:
    ready = model_readiness(identifier)
    if not ready["inference_ready"]:
        ds.fail("model_unavailable", ready["message"], 503)
    loaded = load_model(identifier)
    frame = source_frame()
    window = input_window(frame, loaded.metadata["sequence_length"], as_of)
    values = window[FEATURES].to_numpy(dtype=float)
    batched = values[-1][None, :] if loaded.metadata["sequence_length"] == 1 else values[None, :, :]
    try:
        estimate = float(loaded.predict(batched)[0])
    except ModelUnavailable as exc:
        ds.fail("model_output_invalid", str(exc), 503)
    last = window.iloc[-1]["timestamp"]
    response = {
        "model": identifier, "model_version": loaded.metadata["version"], "status": "success",
        "issued_at": datetime.now(timezone.utc).isoformat(), "forecast_horizon_hours": 1,
        "last_input_observation": last.isoformat(), "input_start": window.iloc[0]["timestamp"].isoformat(),
        "source": ds.source_path("heat-index").name, "forecast_mode": "historical_origin", "scientifically_validated": False,
        "predictions": [{"timestamp": (last + pd.Timedelta(hours=1)).isoformat(), "predicted_heat_index_c": estimate}],
        "observations": [{"timestamp": row.timestamp.isoformat(), "actual_heat_index_c": float(row.heat_index_C) if pd.notna(row.heat_index_C) else None} for row in frame[frame["timestamp"] <= last].tail(12).itertuples()],
        "note": "Forecast is relative to the last source observation, not current weather. Retrospective reproducibility does not establish prospective accuracy.",
    }
    ISSUED_FORECASTS.append(response)
    return response
