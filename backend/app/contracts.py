"""REST and WebSocket contracts."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """The health contract the Capture Agent wizard validates (agent-configuration-wizard.md)."""

    service: Literal["advera-api"] = "advera-api"
    status: Literal["ok"]
