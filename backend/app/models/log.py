import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


Index("idx_logs_project", Log.project_id)
Index("idx_logs_service", Log.service_name)
Index("idx_logs_level", Log.level)
Index("idx_logs_correlation", Log.correlation_id)
Index("idx_logs_time", Log.created_at)
