import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Friendly label for this connection")
    provider: Literal["aws", "azure", "gcp"] = Field(
        ...,
        description="Cloud provider: 'aws', 'azure', or 'gcp'",
    )


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    provider: str
    status: str
    # The webhook URL the cloud should POST to
    webhook_url: str
    # The token the cloud must include as ?token=<webhook_token>
    webhook_token: str
    created_at: datetime

    model_config = {"from_attributes": True}


class IntegrationListResponse(BaseModel):
    items: list[IntegrationResponse]


class WebhookAckResponse(BaseModel):
    accepted: int
    message: str
