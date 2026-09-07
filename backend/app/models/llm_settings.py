import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmSettings(Base):
    __tablename__ = "llm_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # None on any of these means "inherit the system-wide default" (app.core.config.settings).
    enabled: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Stored as plain text, same posture as CloudIntegration.webhook_token today.
    # Unlike webhook_token, this is never re-serialized in a response after being set.
    api_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Only meaningful for provider="azure_openai" (e.g. "2024-06-01"); ignored otherwise.
    api_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
