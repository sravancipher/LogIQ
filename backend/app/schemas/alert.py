from pydantic import BaseModel, Field


class AlertTestRequest(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=3, max_length=2000)
    severity: str = Field(default="HIGH", max_length=20)
    recipient_email: str | None = Field(default=None, max_length=320)


class AlertTestResponse(BaseModel):
    slack: bool
    teams: bool
    email: bool


class InsightNotifyRequest(BaseModel):
    recipient_email: str = Field(min_length=5, max_length=320)
    lookback_minutes: int = Field(default=60, ge=5, le=1440)
    deep_analysis: bool = False
    severity: str = Field(default="HIGH", max_length=20)
    note: str | None = Field(default=None, max_length=1000)
    target_service_name: str | None = Field(default=None, max_length=120)
    target_error_type: str | None = Field(default=None, max_length=120)
    target_operation: str | None = Field(default=None, max_length=120)


class InsightNotifyResponse(BaseModel):
    email: bool
    recipient_email: str
    target_error_group: str
    analysis_mode: str
    message: str
