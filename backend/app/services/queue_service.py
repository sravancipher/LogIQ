from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.work_queue import WorkQueueItem


def enqueue_log_batch(db: Session, project_id: uuid.UUID, count: int) -> None:
    db.add(
        WorkQueueItem(
            project_id=project_id,
            task_type="process_log_batch",
            payload={"count": count},
            status="pending",
        )
    )


def fetch_pending_jobs(db: Session, limit: int = 50) -> list[WorkQueueItem]:
    stmt = (
        select(WorkQueueItem)
        .where(WorkQueueItem.status == "pending")
        .order_by(WorkQueueItem.created_at.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def mark_job_done(db: Session, item: WorkQueueItem) -> None:
    item.status = "done"


def mark_job_failed(db: Session, item: WorkQueueItem, error: str) -> None:
    item.status = "failed"
    item.error_message = error[:2000]
