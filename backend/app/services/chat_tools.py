from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.log import Log
from app.services import insights_service
from app.services.health_service import compute_service_health
from app.services.redaction import redact_value

# Small, fixed bounds so a single tool call can never pull an unbounded number of rows
# or blow up the LLM prompt - the chat assistant must never see "all logs", only a
# deliberately narrow slice per call (see CLAUDE.md Known Issues: no vector DB / no
# raw dumps to the LLM in this codebase's design intent).
MAX_LOGS_PER_CALL = 20
MAX_CONTEXT_LOGS = 10
MESSAGE_CHARS = 400


class SearchLogsArgs(BaseModel):
    service_name: str | None = None
    level: str | None = None
    error_type: str | None = None
    search_text: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=10, ge=1, le=MAX_LOGS_PER_CALL)


class GetLogContextArgs(BaseModel):
    log_id: int
    before: int = Field(default=5, ge=0, le=MAX_CONTEXT_LOGS)
    after: int = Field(default=5, ge=0, le=MAX_CONTEXT_LOGS)


class GetServiceHealthArgs(BaseModel):
    lookback_minutes: int = Field(default=60, ge=5, le=10080)


class GetLatestInsightArgs(BaseModel):
    pass


def _log_to_dict(row: Log) -> dict[str, Any]:
    # metadata_json is deliberately omitted - it's arbitrary customer-supplied JSON
    # and a much larger redaction surface than a single message string; out of scope
    # for this first pass.
    return {
        "log_id": row.id,
        "timestamp": row.created_at.isoformat(),
        "service_name": row.service_name,
        "operation": row.operation,
        "level": row.level,
        "status": row.status,
        "message": redact_value(row.message[:MESSAGE_CHARS]),
        "error_type": row.error_type,
        "correlation_id": row.correlation_id,
    }


def search_logs(db: Session, project_id: uuid.UUID, args: SearchLogsArgs) -> dict[str, Any]:
    """Search this project's logs by service/level/error_type/free-text/time range."""
    filters = [Log.project_id == project_id]
    if args.service_name:
        filters.append(Log.service_name == args.service_name)
    if args.level:
        filters.append(func.upper(Log.level) == args.level.upper())
    if args.error_type:
        filters.append(Log.error_type == args.error_type)
    if args.search_text:
        filters.append(Log.message.ilike(f"%{args.search_text}%"))
    if args.start_time:
        filters.append(Log.created_at >= args.start_time)
    if args.end_time:
        filters.append(Log.created_at <= args.end_time)

    rows = db.scalars(
        select(Log).where(*filters).order_by(Log.created_at.desc(), Log.id.desc()).limit(args.limit)
    ).all()

    return {"count": len(rows), "logs": [_log_to_dict(r) for r in rows]}


def get_log_context(db: Session, project_id: uuid.UUID, args: GetLogContextArgs) -> dict[str, Any]:
    """Fetch the logs immediately before/after a specific log_id from the same project."""
    target = db.scalar(select(Log).where(Log.project_id == project_id, Log.id == args.log_id))
    if target is None:
        return {"error": f"log_id {args.log_id} was not found in this project"}

    before_rows = db.scalars(
        select(Log)
        .where(Log.project_id == project_id, Log.created_at <= target.created_at, Log.id <= target.id)
        .order_by(Log.created_at.desc(), Log.id.desc())
        .limit(args.before + 1)
    ).all()
    after_rows = db.scalars(
        select(Log)
        .where(Log.project_id == project_id, Log.created_at >= target.created_at, Log.id > target.id)
        .order_by(Log.created_at.asc(), Log.id.asc())
        .limit(args.after)
    ).all()

    ordered = list(reversed(before_rows)) + list(after_rows)
    return {"target_log_id": target.id, "logs": [_log_to_dict(r) for r in ordered]}


def get_service_health(db: Session, project_id: uuid.UUID, args: GetServiceHealthArgs) -> dict[str, Any]:
    """Per-service log/error totals and health status for this project (reuses the same
    logic as GET /services)."""
    health = compute_service_health(db, project_id, args.lookback_minutes)
    return {
        "lookback_minutes": args.lookback_minutes,
        "services": [
            {
                "service_name": h.service_name,
                "total_logs": h.total_logs,
                "error_logs": h.error_logs,
                "status": h.status,
                "last_seen": h.last_seen.isoformat() if h.last_seen else None,
            }
            for h in health
        ],
    }


def get_latest_insight(db: Session, project_id: uuid.UUID, args: GetLatestInsightArgs) -> dict[str, Any]:
    """The project's most recently computed AI/rule-based root-cause analysis, if any.
    Reads the persisted snapshot only (see GET /insights/latest) - never recomputes,
    never makes its own LLM call."""
    latest = insights_service.get_latest_insight(db, project_id)
    if not latest.has_analysis or latest.insight is None:
        return {"has_analysis": False}

    insight = latest.insight
    return {
        "has_analysis": True,
        "computed_at": insight.computed_at,
        "lookback_minutes": insight.lookback_minutes,
        "total_logs": insight.total_logs,
        "error_logs": insight.error_logs,
        "top_error_type": insight.top_error_type,
        "top_service": insight.top_service,
        "root_cause": insight.root_cause,
        "suggestion": insight.suggestion,
        "analysis_mode": insight.analysis_mode,
    }


ToolFunc = Callable[[Session, uuid.UUID, BaseModel], dict[str, Any]]

# Each entry is (argument schema, implementation). The argument schema is the only
# thing the LLM's tool call is validated against - it has no project_id field on any
# tool, so a project_id the model tries to supply is structurally impossible to act on;
# the real project_id always comes from the authenticated request, never from the LLM.
TOOL_REGISTRY: dict[str, tuple[type[BaseModel], ToolFunc]] = {
    "search_logs": (SearchLogsArgs, search_logs),
    "get_log_context": (GetLogContextArgs, get_log_context),
    "get_service_health": (GetServiceHealthArgs, get_service_health),
    "get_latest_insight": (GetLatestInsightArgs, get_latest_insight),
}

TOOL_CATALOG = """\
- search_logs(service_name?, level?, error_type?, search_text?, start_time?, end_time?, limit<=20): \
search recent logs matching filters (all optional). Returns up to `limit` logs, newest first.
- get_log_context(log_id, before<=10, after<=10): fetch the logs immediately before/after one \
specific log_id (from an earlier search_logs result), to see what happened around it.
- get_service_health(lookback_minutes<=10080): per-service log/error totals and health status \
(healthy/degraded/critical) for the project in the given window.
- get_latest_insight(): the project's most recently computed root-cause analysis, if one exists. \
Free to call (no LLM cost)."""
