import re

from pydantic import BaseModel, Field, field_validator

# Lenient boundary check: rejects obviously malformed input (no "@", no ".", embedded
# whitespace) without imposing a new dependency (pydantic's EmailStr needs email-validator,
# which isn't in requirements.txt) or risking false negatives on valid-but-unusual addresses.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email_format(value: str | None) -> str | None:
    if value is None or value == "":
        return value
    if not _EMAIL_RE.match(value):
        raise ValueError("must be a valid email address")
    return value


class AlertTestRequest(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=3, max_length=2000)
    severity: str = Field(default="HIGH", max_length=20)
    recipient_email: str | None = Field(default=None, max_length=320)

    @field_validator("recipient_email")
    @classmethod
    def _check_recipient_email(cls, v: str | None) -> str | None:
        return _validate_email_format(v)


class AlertTestResponse(BaseModel):
    slack: bool
    teams: bool
    email: bool


class InsightNotifyRequest(BaseModel):
    recipient_email: str = Field(min_length=5, max_length=320)
    lookback_minutes: int = Field(default=60, ge=5, le=43200)
    deep_analysis: bool = False
    severity: str = Field(default="HIGH", max_length=20)
    note: str | None = Field(default=None, max_length=1000)
    target_service_name: str | None = Field(default=None, max_length=120)
    target_error_type: str | None = Field(default=None, max_length=120)
    target_operation: str | None = Field(default=None, max_length=120)

    @field_validator("recipient_email")
    @classmethod
    def _check_recipient_email(cls, v: str) -> str:
        return _validate_email_format(v)


class InsightNotifyResponse(BaseModel):
    email: bool
    recipient_email: str
    target_error_group: str
    analysis_mode: str
    message: str
