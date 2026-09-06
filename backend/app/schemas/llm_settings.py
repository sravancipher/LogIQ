from typing import Literal

from pydantic import BaseModel, Field


class LlmSettingsUpdate(BaseModel):
    enabled: bool = Field(..., description="Whether AI-powered log analysis is enabled for this project")
    provider: Literal["openai_compatible", "ollama"] = Field(
        ..., description="Which LLM backend to call: an OpenAI-compatible HTTP API, or a native Ollama server"
    )
    base_url: str | None = Field(None, max_length=500, description="Base URL of the LLM/Ollama endpoint")
    model: str | None = Field(None, max_length=255, description="Model name/identifier to request")
    api_key: str | None = Field(
        None,
        max_length=500,
        description=(
            "API key for the LLM endpoint. Omit this field entirely to keep the currently stored key "
            "unchanged; send an empty string to clear it."
        ),
    )
    temperature: float | None = Field(None, ge=0.0, le=2.0)


class LlmSettingsResponse(BaseModel):
    has_override: bool = Field(..., description="Whether this project has its own LLM configuration")
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    temperature: float


class LlmSettingsTestResponse(BaseModel):
    success: bool
    message: str
