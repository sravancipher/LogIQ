import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertSettings(Base):
    __tablename__ = "alert_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # None on any of these means "inherit the system-wide default" (app.core.config.settings).
    # Stored as plain text, same posture as CloudIntegration.webhook_token today.
    slack_webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    teams_webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    alert_email_from: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    alert_email_to: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    smtp_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    smtp_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
