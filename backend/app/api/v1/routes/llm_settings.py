"""
llm_settings.py — per-project LLM configuration for AI Insights.

Authenticated routes (require X-API-Key):
  GET    /api/v1/llm-settings         — view this project's effective LLM configuration
  PUT    /api/v1/llm-settings         — set/replace this project's LLM override
  DELETE /api/v1/llm-settings         — remove the override, revert to system defaults
  POST   /api/v1/llm-settings/test    — send a real test request to the configured LLM

A project with no override behaves exactly as it did before this feature existed
(system-wide defaults from app.core.config.settings). The stored api_key is never
returned in a response after being set — only whether one is configured.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.llm_settings import LlmSettings
from app.schemas.llm_settings import LlmSettingsResponse, LlmSettingsTestResponse, LlmSettingsUpdate
from app.services.insights_service import resolve_llm_config, test_llm_connection

router = APIRouter(prefix="/llm-settings", tags=["llm-settings"])


def _build_response(db: Session, project_id: uuid.UUID, has_override: bool) -> LlmSettingsResponse:
    config = resolve_llm_config(db, project_id)
    return LlmSettingsResponse(
        has_override=has_override,
        enabled=config.enabled,
        provider=config.provider,
        base_url=config.base_url,
        model=config.model,
        api_key_configured=bool(config.api_key),
        temperature=config.temperature,
        api_version=config.api_version,
    )


@router.get("", response_model=LlmSettingsResponse)
def get_llm_settings(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> LlmSettingsResponse:
    row = db.scalar(select(LlmSettings).where(LlmSettings.project_id == auth.project_id))
    return _build_response(db, auth.project_id, has_override=row is not None)


@router.put("", response_model=LlmSettingsResponse)
def upsert_llm_settings(
    payload: LlmSettingsUpdate,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> LlmSettingsResponse:
    row = db.scalar(select(LlmSettings).where(LlmSettings.project_id == auth.project_id))
    if row is None:
        row = LlmSettings(project_id=auth.project_id)
        db.add(row)

    row.enabled = payload.enabled
    row.provider = payload.provider
    row.base_url = payload.base_url or None
    row.model = payload.model or None
    if "api_key" in payload.model_fields_set:
        row.api_key = payload.api_key or None
    row.temperature = payload.temperature
    row.api_version = payload.api_version or None

    db.commit()
    return _build_response(db, auth.project_id, has_override=True)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_settings(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> None:
    row = db.scalar(select(LlmSettings).where(LlmSettings.project_id == auth.project_id))
    if row is not None:
        db.delete(row)
        db.commit()


@router.post("/test", response_model=LlmSettingsTestResponse)
def test_llm_settings(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> LlmSettingsTestResponse:
    success, message = test_llm_connection(db, auth.project_id)
    return LlmSettingsTestResponse(success=success, message=message)
