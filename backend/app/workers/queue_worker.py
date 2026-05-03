from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.queue_service import fetch_pending_jobs, mark_job_done, mark_job_failed

logger = logging.getLogger(__name__)


def process_job_payload(task_type: str, payload: dict | None) -> None:
    # Placeholder processor; replace with correlation, grouping, and RCA jobs.
    if task_type not in {"process_log_batch"}:
        raise ValueError(f"Unsupported task type: {task_type}")
    _ = payload


def run_worker() -> None:
    logger.info("Queue worker started")
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
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Worker cycle failed")
        finally:
            db.close()

        time.sleep(settings.queue_poll_interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
