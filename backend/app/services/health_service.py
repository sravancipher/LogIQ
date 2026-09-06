from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.log import Log

CRITICAL_ERROR_RATIO = 0.30


def compute_status(error_logs: int, total_logs: int) -> str:
    if error_logs == 0:
        return "healthy"
    ratio = error_logs / total_logs if total_logs else 1.0
    return "critical" if ratio >= CRITICAL_ERROR_RATIO else "degraded"


@dataclass
class ServiceHealth:
    service_name: str
    total_logs: int
    error_logs: int
    last_seen: datetime | None
    status: str


def compute_service_health(db: Session, project_id: uuid.UUID, lookback_minutes: int) -> list[ServiceHealth]:
    """Per-service log/error rollup and status for one project, in the given lookback
    window. Shared by GET /services and the automated health-check alerting - keep
    both in sync with this single source of truth rather than duplicating the query.
    """
    since = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)

    rows = db.execute(
        select(
            Log.service_name,
            func.count().label("total_logs"),
            func.sum(
                case((func.upper(Log.level).in_(["ERROR", "CRITICAL"]), 1), else_=0)
            ).label("error_logs"),
            func.max(Log.created_at).label("last_seen"),
        )
        .where(
            Log.project_id == project_id,
            Log.created_at >= since,
            Log.service_name.is_not(None),
        )
        .group_by(Log.service_name)
        .order_by(func.max(Log.created_at).desc())
    ).all()

    results: list[ServiceHealth] = []
    for row in rows:
        total = row.total_logs or 0
        errors = row.error_logs or 0
        results.append(
            ServiceHealth(
                service_name=row.service_name,
                total_logs=total,
                error_logs=errors,
                last_seen=row.last_seen,
                status=compute_status(errors, total),
            )
        )
    return results
