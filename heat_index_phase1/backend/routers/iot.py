from fastapi import APIRouter, Depends, Query

from backend.schemas.iot import IoTResponse
from backend.services.iot import MAX_HISTORY, SensorProvider, get_sensor_provider

router = APIRouter(prefix="/api/iot", tags=["Live IoT sensor"])


@router.get("/latest", response_model=IoTResponse)
def latest(provider: SensorProvider = Depends(get_sensor_provider)):
    return provider.latest()


@router.get("/history", response_model=IoTResponse)
def history(limit: int = Query(100, ge=1, le=MAX_HISTORY), provider: SensorProvider = Depends(get_sensor_provider)):
    return provider.history(limit)


@router.get("/status")
def status(provider: SensorProvider = Depends(get_sensor_provider)):
    latest = provider.latest()
    history = provider.history(100)
    reading = latest.get("measurement")
    return {"source": "IoT Weather Sensor", "provider": latest.get("provider", "unknown"), "status": latest["status"],
            "server_reachable": latest["server_reachable"] or history["server_reachable"],
            "sensor_freshness": reading["freshness"] if reading else "unknown",
            "measurement_timestamp_utc": reading["measurement_timestamp_utc"] if reading else None,
            "timestamp_quality": reading["timestamp_quality"] if reading else "missing",
            "latest": latest, "history": history,
            "history_note": "Counts describe the bounded returned window, not the entire upstream database."}
