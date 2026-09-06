"""
alert_settings.py — per-project alert channel configuration (Slack/Teams/SMTP).

Authenticated routes (require X-API-Key):
  GET    /api/v1/alert-settings   — view this project's effective alert channel configuration
  PUT    /api/v1/alert-settings   — set/replace this project's alert channel override
  DELETE /api/v1/alert-settings   — remove the override, revert to system defaults

A project with no override behaves exactly as it did before this feature existed
(system-wide defaults from app.core.config.settings). Webhook URLs and the SMTP
password are never returned in a response after being set — only whether one is configured.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.alert_settings import AlertSettings
from app.schemas.alert_settings import AlertSettingsResponse, AlertSettingsUpdate
from app.services.alert_settings_service import resolve_alert_config

router = APIRouter(prefix="/alert-settings", tags=["alert-settings"])


def _build_response(db: Session, project_id: uuid.UUID, has_override: bool) -> AlertSettingsResponse:
    config = resolve_alert_config(db, project_id)
    return AlertSettingsResponse(
        has_override=has_override,
        slack_configured=bool(config.slack_webhook_url),
        teams_configured=bool(config.teams_webhook_url),
        alert_email_from=config.alert_email_from,
        alert_email_to=config.alert_email_to,
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_username=config.smtp_username,
        smtp_password_configured=bool(config.smtp_password),
    )


@router.get("", response_model=AlertSettingsResponse)
def get_alert_settings(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> AlertSettingsResponse:
    row = db.scalar(select(AlertSettings).where(AlertSettings.project_id == auth.project_id))
    return _build_response(db, auth.project_id, has_override=row is not None)


@router.put("", response_model=AlertSettingsResponse)
def upsert_alert_settings(
    payload: AlertSettingsUpdate,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> AlertSettingsResponse:
    row = db.scalar(select(AlertSettings).where(AlertSettings.project_id == auth.project_id))
    if row is None:
        row = AlertSettings(project_id=auth.project_id)
        db.add(row)

    fields_set = payload.model_fields_set
    if "slack_webhook_url" in fields_set:
        row.slack_webhook_url = payload.slack_webhook_url or None
    if "teams_webhook_url" in fields_set:
        row.teams_webhook_url = payload.teams_webhook_url or None
    if "alert_email_from" in fields_set:
        row.alert_email_from = payload.alert_email_from or None
    if "alert_email_to" in fields_set:
        row.alert_email_to = payload.alert_email_to or None
    if "smtp_host" in fields_set:
        row.smtp_host = payload.smtp_host or None
    if "smtp_port" in fields_set:
        row.smtp_port = payload.smtp_port
    if "smtp_username" in fields_set:
        row.smtp_username = payload.smtp_username or None
    if "smtp_password" in fields_set:
        row.smtp_password = payload.smtp_password or None

    db.commit()
    return _build_response(db, auth.project_id, has_override=True)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_settings(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> None:
    row = db.scalar(select(AlertSettings).where(AlertSettings.project_id == auth.project_id))
    if row is not None:
        db.delete(row)
        db.commit()
