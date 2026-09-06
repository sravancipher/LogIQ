from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.health_alert_service import check_and_alert_unhealthy_services
from app.services.queue_service import fetch_pending_jobs, mark_job_done, mark_job_failed

logger = logging.getLogger(__name__)


def process_job_payload(task_type: str, payload: dict | None) -> None:
    # Placeholder processor; replace with correlation, grouping, and RCA jobs.
    if task_type not in {"process_log_batch"}:
        raise ValueError(f"Unsupported task type: {task_type}")
    _ = payload


def run_worker() -> None:
    logger.info("Queue worker started")
    next_health_check_at = datetime.now(timezone.utc)

    while True:
        db = SessionLocal()
        try:
            jobs = fetch_pending_jobs(db, limit=25)
            for job in jobs:
                try:
                    process_job_payload(job.task_type, job.payload)
                    mark_job_done(db, job)
                except Exception as exc:  # noqa: BLE001
                    mark_job_failed(db, job, str(exc))
            db.commit()

            now = datetime.now(timezone.utc)
            if settings.health_check_enabled and now >= next_health_check_at:
                alerts_sent = check_and_alert_unhealthy_services(db)
                if alerts_sent:
                    logger.info("Sent %d service-health alert(s)", alerts_sent)
                next_health_check_at = now + timedelta(seconds=settings.health_check_interval_seconds)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Worker cycle failed")
        finally:
            db.close()

        time.sleep(settings.queue_poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
