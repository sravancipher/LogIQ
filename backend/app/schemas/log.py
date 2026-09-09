from datetime import datetime

from pydantic import BaseModel, Field


class LogItemIn(BaseModel):
    service_name: str | None = Field(default=None, max_length=255)
    operation: str | None = Field(default=None, max_length=255)
    level: str = Field(min_length=3, max_length=20)
    status: str | None = Field(default=None, max_length=50)
    message: str = Field(min_length=1)
    error_type: str | None = Field(default=None, max_length=255)
    correlation_id: str | None = Field(default=None, max_length=255)
    metadata: dict | None = None
    source: str = Field(default="agent", max_length=50)
    source_file: str | None = Field(default=None, max_length=500)
    source_line: int | None = None


class LogIngestRequest(BaseModel):
    logs: list[LogItemIn] = Field(min_length=1, max_length=1000)


class LogIngestResponse(BaseModel):
    accepted: int


class LogOut(BaseModel):
    id: int
    service_name: str | None
    operation: str | None
    level: str
    status: str | None
    message: str
    error_type: str | None
    correlation_id: str | None
    metadata: dict | None
    source: str
    source_file: str | None = None
    source_line: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedLogsResponse(BaseModel):
    items: list[LogOut]
    next_cursor: str | None = None
