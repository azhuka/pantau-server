from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ServiceReport(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    port: int = Field(..., ge=1, le=65535)
    process_name: str = Field(..., min_length=1, max_length=100)
    status: Literal["up", "down"]
    active_connections: int = Field(default=0, ge=0)


class ReportPayload(BaseModel):
    hostname: str = Field(..., min_length=1, max_length=255)
    ip_address: str = Field(..., min_length=1, max_length=45)
    services: list[ServiceReport] = Field(default_factory=list)


class ReportResponse(BaseModel):
    ok: bool
    message: str
    server_id: int


class HealthResponse(BaseModel):
    status: str = "ok"
    timestamp: datetime
