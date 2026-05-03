from pydantic import BaseModel, Field


class AlertTestRequest(BaseModel):
    title: str = Field(min_length=3, max_length=150)
    message: str = Field(min_length=3, max_length=2000)
    severity: str = Field(default="HIGH", max_length=20)


class AlertTestResponse(BaseModel):
    slack: bool
    teams: bool
    email: bool
