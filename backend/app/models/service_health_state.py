import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceHealthState(Base):
    __tablename__ = "service_health_state"
    __table_args__ = (
        UniqueConstraint("project_id", "service_name", name="uq_service_health_state_project_service"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    service_name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Most recently observed status, updated on every check.
    last_status: Mapped[str] = mapped_column(String(20), nullable=False)
    # The status an alert was last sent for - None until the first alert. Comparing
    # against this (not last_status) is what prevents re-alerting every poll cycle
    # while a service stays in the same unhealthy state.
    last_alerted_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


Index("idx_service_health_state_project", ServiceHealthState.project_id)
