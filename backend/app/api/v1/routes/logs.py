from datetime import datetime
from typing import Optional
import base64

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.ingest_request import IngestRequest
from app.models.log import Log
from app.models.work_queue import WorkQueueItem
from app.schemas.log import LogIngestRequest, LogIngestResponse, LogOut, PaginatedLogsResponse

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=LogIngestResponse, status_code=status.HTTP_202_ACCEPTED)
def ingest_logs(
    payload: LogIngestRequest,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> LogIngestResponse:
    ingest_marker: IngestRequest | None = None
    if idempotency_key:
        ingest_marker = db.scalar(
            select(IngestRequest).where(
                IngestRequest.project_id == auth.project_id,
                IngestRequest.idempotency_key == idempotency_key,
            )
        )
        if ingest_marker:
            return LogIngestResponse(accepted=ingest_marker.accepted_count)

    rows = [
        Log(
            project_id=auth.project_id,
            service_name=item.service_name,
            operation=item.operation,
            level=item.level.upper(),
            status=item.status,
            message=item.message,
            error_type=item.error_type,
            correlation_id=item.correlation_id,
            metadata_json=item.metadata,
            source=item.source,
        )
        for item in payload.logs
    ]

    try:
        if idempotency_key:
            marker = IngestRequest(
                project_id=auth.project_id,
                idempotency_key=idempotency_key,
                accepted_count=len(rows),
            )
            db.add(marker)

        db.bulk_save_objects(rows)
        db.add(
            WorkQueueItem(
                project_id=auth.project_id,
                task_type="process_log_batch",
                payload={"count": len(rows)},
                status="pending",
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if not idempotency_key:
            raise
        existing = db.scalar(
            select(IngestRequest).where(
                IngestRequest.project_id == auth.project_id,
                IngestRequest.idempotency_key == idempotency_key,
            )
        )
        if existing:
            return LogIngestResponse(accepted=existing.accepted_count)
        raise

    return LogIngestResponse(accepted=len(rows))


def _encode_cursor(created_at: datetime, row_id: int) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[datetime, int]:
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        ts, row_id = decoded.split("|", maxsplit=1)
        return datetime.fromisoformat(ts), int(row_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cursor format")


@router.get("", response_model=PaginatedLogsResponse)
def get_logs(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
    service_name: str | None = Query(default=None),
    level: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
) -> PaginatedLogsResponse:
    stmt: Select[tuple[Log]] = select(Log).where(Log.project_id == auth.project_id)

    if service_name:
        stmt = stmt.where(Log.service_name == service_name)
    if level:
        stmt = stmt.where(func.upper(Log.level) == level.upper())
    if start_time:
        stmt = stmt.where(Log.created_at >= start_time)
    if end_time:
        stmt = stmt.where(Log.created_at <= end_time)

    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Log.created_at < cursor_created_at,
                and_(Log.created_at == cursor_created_at, Log.id < cursor_id),
            )
        )

    stmt = stmt.order_by(Log.created_at.desc(), Log.id.desc()).limit(limit + 1)
    logs = db.scalars(stmt).all()

    has_next = len(logs) > limit
    page_rows = logs[:limit]

    items = [
        LogOut(
            id=row.id,
            service_name=row.service_name,
            operation=row.operation,
            level=row.level,
            status=row.status,
            message=row.message,
            error_type=row.error_type,
            correlation_id=row.correlation_id,
            metadata=row.metadata_json,
            source=row.source,
            created_at=row.created_at,
        )
        for row in page_rows
    ]

    next_cursor = None
    if has_next and page_rows:
        last = page_rows[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return PaginatedLogsResponse(items=items, next_cursor=next_cursor)
