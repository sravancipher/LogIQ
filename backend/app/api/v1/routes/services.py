from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.schemas.service import HealthCheckResponse, ServiceSummary, ServicesListResponse
from app.services.health_alert_service import check_project_services
from app.services.health_service import compute_service_health

router = APIRouter(prefix="/services", tags=["services"])


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
    health = compute_service_health(db, auth.project_id, lookback_minutes)
    services = [
        ServiceSummary(
            service_name=h.service_name,
            total_logs=h.total_logs,
            error_logs=h.error_logs,
            last_seen=h.last_seen,
            status=h.status,
        )
        for h in health
    ]
    return ServicesListResponse(services=services)


@router.post("/health-check", response_model=HealthCheckResponse)
def run_health_check(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> HealthCheckResponse:
    """
    Compute this project's current service health and send an alert (via this
    project's configured Slack/Teams/email channels) for any service that has
    newly become unhealthy, changed severity, or just recovered.

    Call this on a schedule from an external cron/uptime-monitor (e.g. cron-job.org,
    GitHub Actions, UptimeRobot) to get automated alerting without needing a
    separately-hosted always-on background worker process.
    """
    checked, alerts_sent = check_project_services(db, auth.project_id)
    return HealthCheckResponse(services_checked=checked, alerts_sent=alerts_sent)
