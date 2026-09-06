from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.project import Project
from app.models.service_health_state import ServiceHealthState
from app.schemas.alert import AlertTestRequest
from app.services.alert_service import send_test_alert
from app.services.alert_settings_service import resolve_alert_config
from app.services.health_service import compute_service_health

logger = logging.getLogger(__name__)


def decide_alert(last_alerted_status: str | None, current_status: str) -> tuple[str, str] | None:
    """Pure decision: should a health-transition alert fire right now, and with what
    (severity, verb)? Returns None when nothing meaningful has changed since the last
    alert, so repeated checks of an unchanged unhealthy state don't re-alert every cycle.
    Comparing against the last *alerted* status (not just the last observed one) is
    what makes this idempotent across repeated polls.
    """
    if current_status == "healthy":
        if last_alerted_status and last_alerted_status != "healthy":
            return "LOW", "has recovered and is healthy again"
        return None

    # degraded or critical
    if last_alerted_status != current_status:
        severity = "CRITICAL" if current_status == "critical" else "MEDIUM"
        return severity, f"is now {current_status}"

    return None


def check_project_services(db: Session, project_id: uuid.UUID) -> tuple[int, int]:
    """Compute current service health for one project, alert on any real transition,
    and persist the new state. Returns (services_checked, alerts_sent).
    """
    health = compute_service_health(db, project_id, settings.health_check_lookback_minutes)
    alerts_sent = 0

    for svc in health:
        state_row = db.scalar(
            select(ServiceHealthState).where(
                ServiceHealthState.project_id == project_id,
                ServiceHealthState.service_name == svc.service_name,
            )
        )
        last_alerted_status = state_row.last_alerted_status if state_row else None
        decision = decide_alert(last_alerted_status, svc.status)

        if state_row is None:
            state_row = ServiceHealthState(
                project_id=project_id, service_name=svc.service_name, last_status=svc.status
            )
            db.add(state_row)
        else:
            state_row.last_status = svc.status
        state_row.last_checked_at = datetime.now(timezone.utc)

        if decision is not None:
            severity, verb = decision
            config = resolve_alert_config(db, project_id)
            payload = AlertTestRequest(
                title=f"[{severity}] Service '{svc.service_name}' {verb}",
                message=(
                    f"Service '{svc.service_name}' {verb} "
                    f"({svc.error_logs}/{svc.total_logs} error log(s) in the last "
                    f"{settings.health_check_lookback_minutes} minutes)."
                ),
                severity=severity,
            )
            send_test_alert(payload, config)
            state_row.last_alerted_status = svc.status
            alerts_sent += 1

    db.commit()
    return len(health), alerts_sent


def check_and_alert_unhealthy_services(db: Session) -> int:
    """Run check_project_services for every project. Used by the standalone queue
    worker process. Never raises - a failure for one project is logged and doesn't
    block the rest. Returns the total number of alerts sent across all projects.
    """
    if not settings.health_check_enabled:
        return 0

    total_alerts_sent = 0
    project_ids = db.scalars(select(Project.id)).all()
    for project_id in project_ids:
        try:
            _, alerts_sent = check_project_services(db, project_id)
            total_alerts_sent += alerts_sent
        except Exception:
            logger.exception("Health check failed for project %s", project_id)
            db.rollback()

    return total_alerts_sent
