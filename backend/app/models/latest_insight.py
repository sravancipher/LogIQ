import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LatestInsight(Base):
    """One row per project: a snapshot of the most recently computed AI Insights
    result, regardless of which lookback/levels/deep_analysis params produced it.

    This lets the Overview page and the AI Insights page (on remount, after
    navigating away) both show the exact same "last analysis" instead of each
    silently triggering its own separate computation - the whole response is
    stored as JSON (response_json) since InsightsResponse has a rich nested shape.
    """

    __tablename__ = "latest_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lookback_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
