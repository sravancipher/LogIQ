from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    lookback_minutes: int = Field(
        default=1440,
        ge=5,
        le=43200,
        description="Default time window tools should use if the question doesn't specify one.",
    )


class ChatEvidenceItem(BaseModel):
    description: str
    log_id: int | None = Field(
        default=None,
        description="Only populated when it refers to a log_id actually returned by a tool call this turn.",
    )


class ChatToolCallLog(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str


class ChatResponse(BaseModel):
    answer: str
    evidence: list[ChatEvidenceItem] = Field(default_factory=list)
    tool_calls: list[ChatToolCallLog] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"
    model_name: str | None = None
    analysis_mode: Literal["llm", "unavailable"] = "llm"
