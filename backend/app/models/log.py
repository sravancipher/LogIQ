import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, PrimaryKeyConstraint, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Log(Base):
    __tablename__ = "logs"
    # created_at is part of the PK (not just id) because logs is a native Postgres
    # RANGE-partitioned-by-day table (see migration 20260915_0012) - Postgres requires
    # every unique constraint on a partitioned table to include the partition key.
    __table_args__ = (
        PrimaryKeyConstraint("id", "created_at"),
        Index("idx_logs_project_created", "project_id", "created_at"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[int] = mapped_column(autoincrement=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    service_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    operation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    level: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    source: Mapped[str] = mapped_column(String(50), nullable=False, default="agent")
    # Where in the caller's source this log/error actually came from: for
    # capture_exception() this is the deepest frame of the exception's own traceback
    # (where it was raised); for a plain log()/error() call with no exception object,
    # the SDK falls back to the caller's own stack frame. Both optional - not every
    # ingest path (e.g. cloud-webhook-normalized logs) can populate these.
    source_file: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_line: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


Index("idx_logs_project", Log.project_id)
Index("idx_logs_service", Log.service_name)
Index("idx_logs_level", Log.level)
Index("idx_logs_correlation", Log.correlation_id)
Index("idx_logs_time", Log.created_at)
