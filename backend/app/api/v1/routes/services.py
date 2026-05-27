from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.log import Log
from app.schemas.service import ServiceSummary, ServicesListResponse

router = APIRouter(prefix="/services", tags=["services"])


def _compute_status(error_logs: int, total_logs: int) -> str:
    if error_logs == 0:
        return "healthy"
    ratio = error_logs / total_logs if total_logs else 1.0
    return "critical" if ratio >= 0.30 else "degraded"


@router.get("", response_model=ServicesListResponse)
def list_services(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
    lookback_minutes: int = Query(default=1440, ge=1, le=10080),
) -> ServicesListResponse:
    """
    Return all distinct uvicorn/service instances that have sent logs within
    the given lookback window, along with per-service error counts and status.
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
            Log.project_id == auth.project_id,
            Log.created_at >= since,
            Log.service_name.is_not(None),
        )
        .group_by(Log.service_name)
        .order_by(func.max(Log.created_at).desc())
    ).all()

    services: list[ServiceSummary] = []
    for row in rows:
        total = row.total_logs or 0
        errors = row.error_logs or 0
        services.append(
            ServiceSummary(
                service_name=row.service_name,
                total_logs=total,
                error_logs=errors,
                last_seen=row.last_seen,
                status=_compute_status(errors, total),
            )
        )

    return ServicesListResponse(services=services)
