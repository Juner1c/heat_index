"""Transport-independent IoT responses; never infer a date or timezone."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr

NumericInput = StrictStr | StrictFloat | StrictInt | None


class RenderLatest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    temperature: NumericInput = None
    humidity: NumericInput = None
    current_hi: NumericInput = None
    forecast_hi: NumericInput = None
    timestamp: StrictStr | None = None
    cur_category: StrictStr | None = None
    cur_action: StrictStr | None = None
    status: StrictStr | None = None


class RenderHistoryRow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: StrictInt | None = None
    timestamp: StrictStr | None = None
    temperature_c: NumericInput = None
    humidity_pct: NumericInput = None
    heat_index_c: NumericInput = None
    forecast_3hr_c: NumericInput = None
    pagasa_advisory: StrictStr | None = None


class RenderHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    readings: list[dict]
    count: int | None = Field(default=None, ge=0)


class SensorReading(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: int | None = None
    temperature_c: float | None = None
    humidity_percent: float | None = None
    heat_index_c: float | None = None
    timestamp_raw: str | None = None
    measurement_timestamp_utc: str | None = None
    timestamp_quality: Literal["offset_verified", "timezone_unverified", "time_only", "missing", "invalid"] = "missing"
    freshness: Literal["fresh", "stale", "future", "unknown"] = "unknown"
    age_seconds: float | None = None
    advisory: str | None = None
    action: str | None = None
    experimental_forecast_c: float | None = None
    forecast_label: str = "Experimental IoT forecast — unvalidated"
    forecast_horizon_verified: bool = False
    issues: list[str] = Field(default_factory=list)


class IoTResponse(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    source: str = "IoT Weather Sensor"
    provider: str = "render_flask"
    status: Literal["available", "partial", "no_data", "unavailable"]
    server_reachable: bool
    checked_at_utc: str
    cache_age_seconds: float = 0
    upstream_status: str | None = None
    message: str | None = None
    error_code: str | None = None
    measurement: SensorReading | None = None
    records: list[SensorReading] = Field(default_factory=list)
    requested_limit: int | None = None
    returned_count: int = 0
    invalid_readings: int = 0
    invalid_fields: int = 0
    unverified_timestamps: int = 0
    duplicate_timestamps: int = 0
    upstream_reported_count: int | None = None
    total_database_count_known: bool = False
    warnings: list[str] = Field(default_factory=list)
