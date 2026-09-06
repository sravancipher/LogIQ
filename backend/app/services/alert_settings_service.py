from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert_settings import AlertSettings


@dataclass
class AlertChannelConfig:
    slack_webhook_url: str | None
    teams_webhook_url: str | None
    alert_email_from: str | None
    alert_email_to: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None


def resolve_alert_config(db: Session, project_id: uuid.UUID) -> AlertChannelConfig:
    """Merge a project's optional alert-channel override (alert_settings) with the
    system-wide defaults. Any field left unset (None/blank) on the project's row falls
    back to app.core.config.settings, so a project with no override behaves exactly as
    before this feature existed.
    """
    row = db.scalar(select(AlertSettings).where(AlertSettings.project_id == project_id))

    return AlertChannelConfig(
        slack_webhook_url=(row.slack_webhook_url if row and row.slack_webhook_url else settings.slack_webhook_url),
        teams_webhook_url=(row.teams_webhook_url if row and row.teams_webhook_url else settings.teams_webhook_url),
        alert_email_from=(row.alert_email_from if row and row.alert_email_from else settings.alert_email_from),
        alert_email_to=(row.alert_email_to if row and row.alert_email_to else settings.alert_email_to),
        smtp_host=(row.smtp_host if row and row.smtp_host else settings.smtp_host),
        smtp_port=(row.smtp_port if row and row.smtp_port else settings.smtp_port),
        smtp_username=(row.smtp_username if row and row.smtp_username else settings.smtp_username),
        smtp_password=(row.smtp_password if row and row.smtp_password else settings.smtp_password),
    )
