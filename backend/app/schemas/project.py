import uuid

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None


class ProjectCreateResponse(BaseModel):
    project_id: uuid.UUID
    api_key: str
