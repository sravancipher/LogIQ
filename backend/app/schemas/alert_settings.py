from pydantic import BaseModel, Field, field_validator

from app.schemas.alert import _validate_email_format


class AlertSettingsUpdate(BaseModel):
    slack_webhook_url: str | None = Field(
        None, max_length=500, description="Omit to keep unchanged; send an empty string to clear."
    )
    teams_webhook_url: str | None = Field(
        None, max_length=500, description="Omit to keep unchanged; send an empty string to clear."
    )
    alert_email_from: str | None = Field(None, max_length=320)
    alert_email_to: str | None = Field(None, max_length=320)
    smtp_host: str | None = Field(None, max_length=255)
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_username: str | None = Field(None, max_length=255)
    smtp_password: str | None = Field(
        None, max_length=500, description="Omit to keep unchanged; send an empty string to clear."
    )

    @field_validator("alert_email_from", "alert_email_to")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        return _validate_email_format(v)


class AlertSettingsResponse(BaseModel):
    has_override: bool = Field(..., description="Whether this project has its own alert channel configuration")
    slack_configured: bool
    teams_configured: bool
    alert_email_from: str | None
    alert_email_to: str | None
    smtp_host: str | None
    smtp_port: int | None
    smtp_username: str | None
    smtp_password_configured: bool
