from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

ModelIdentifier = Literal["single_time_constant", "sequence_time_constant"]


class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: ModelIdentifier = "sequence_time_constant"
    forecast_horizon_hours: Literal[1] = 1
    as_of: AwareDatetime | None = None
