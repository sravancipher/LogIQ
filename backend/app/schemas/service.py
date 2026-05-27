from datetime import datetime

from pydantic import BaseModel


class ServiceSummary(BaseModel):
    service_name: str
    total_logs: int
    error_logs: int
    last_seen: datetime
    status: str  # "healthy" | "degraded" | "critical"


class ServicesListResponse(BaseModel):
    services: list[ServiceSummary]
