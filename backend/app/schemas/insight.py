from typing import Literal

from pydantic import BaseModel, Field


class InsightTimelineEvent(BaseModel):
    timestamp: str
    level: str
    service_name: str | None = None
    message: str
    error_type: str | None = None
    correlation_id: str | None = None


class InsightsResponse(BaseModel):
    project_id: str
    lookback_minutes: int
    total_logs: int
    error_logs: int
    top_error_type: str | None
    top_service: str | None
    root_cause: str
    suggestion: str
    confidence: float
    incident_summary: str
    action_plan: list[str] = Field(default_factory=list)
    timeline: list[InsightTimelineEvent] = Field(default_factory=list)
    analysis_mode: Literal["llm", "fallback"] = "fallback"
    model_name: str | None = None
    fallback_reason: str | None = None


class InsightFeedbackCreate(BaseModel):
    rating: Literal["up", "down"]
    lookback_minutes: int = Field(ge=5, le=1440)
    root_cause: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)
    incident_summary: str | None = None
    analysis_mode: str | None = None
    model_name: str | None = None
    correction: str | None = None


class InsightFeedbackResponse(BaseModel):
    id: str
    message: str
