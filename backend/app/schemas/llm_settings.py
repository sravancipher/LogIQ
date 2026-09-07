from typing import Literal

from pydantic import BaseModel, Field

# "azure_openai": deployment-based Azure OpenAI Service.
# "anthropic": Anthropic's own Messages API (api.anthropic.com).
# "bedrock": Amazon Bedrock's Anthropic-native route, authenticated with a Bedrock API key
#            (no AWS SigV4 signing / boto3 required) - same request/response shape as "anthropic".
LlmProvider = Literal["ollama", "openai_compatible", "azure_openai", "anthropic", "bedrock"]


class LlmSettingsUpdate(BaseModel):
    enabled: bool = Field(..., description="Whether AI-powered log analysis is enabled for this project")
    provider: LlmProvider = Field(..., description="Which LLM backend to call")
    base_url: str | None = Field(
        None,
        max_length=500,
        description=(
            "Base endpoint URL. Examples - ollama: http://localhost:11434; "
            "openai_compatible: https://api.openai.com/v1; "
            "azure_openai: https://<resource>.openai.azure.com; "
            "anthropic: https://api.anthropic.com; "
            "bedrock: https://bedrock-runtime.<region>.amazonaws.com/anthropic"
        ),
    )
    model: str | None = Field(
        None,
        max_length=255,
        description="Model name/identifier. For azure_openai, this is the deployment name, not the model name.",
    )
    api_key: str | None = Field(
        None,
        max_length=500,
        description=(
            "API key/credential for the endpoint (for bedrock, a Bedrock API key - see AWS docs 'Amazon "
            "Bedrock API keys'). Omit this field entirely to keep the currently stored key unchanged; "
            "send an empty string to clear it."
        ),
    )
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    api_version: str | None = Field(
        None,
        max_length=50,
        description="Only used by azure_openai (e.g. '2024-06-01'); ignored by every other provider.",
    )


class LlmSettingsResponse(BaseModel):
    has_override: bool = Field(..., description="Whether this project has its own LLM configuration")
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    temperature: float
    api_version: str | None = None


class LlmSettingsTestResponse(BaseModel):
    success: bool
    message: str
