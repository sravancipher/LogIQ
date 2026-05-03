import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CloudIntegration(Base):
    __tablename__ = "cloud_integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Human-readable label, e.g. "prod-aws-us-east-1"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # "aws" or "azure"
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Random token sent by the cloud caller in ?token=xxx to authenticate webhook calls.
    # Stored as plain text (user chose this). Add encryption later via cryptography/Fernet.
    webhook_token: Mapped[str] = mapped_column(String(64), nullable=False)
    # "active" | "inactive"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


Index("idx_cloud_integrations_project", CloudIntegration.project_id)
