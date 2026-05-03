from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.log import Log
from app.schemas.insight import InsightTimelineEvent, InsightsResponse


def build_insights(db: Session, project_id: uuid.UUID, lookback_minutes: int) -> InsightsResponse:
    metrics, recent_logs = _collect_insight_inputs(db=db, project_id=project_id, lookback_minutes=lookback_minutes)
    fallback = _build_rule_based_insights(project_id, lookback_minutes, metrics, recent_logs)

    if not settings.llm_enabled:
        print("LLM analysis disabled, returning rule-based insights")
        fallback.fallback_reason = "LLM analysis disabled"
        return fallback

    llm_response = _generate_llm_analysis(project_id, lookback_minutes, metrics, recent_logs)
    if llm_response is None:
        print("LLM analysis failed or returned invalid response, falling back to rule-based insights")
        fallback.fallback_reason = "LLM analysis unavailable or response invalid"
        return fallback

    return llm_response


def _collect_insight_inputs(
    db: Session,
    project_id: uuid.UUID,
    lookback_minutes: int,
) -> tuple[dict[str, Any], list[Log]]:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=lookback_minutes)
    base_filters = [Log.project_id == project_id, Log.created_at >= window_start]

    total_logs = db.scalar(select(func.count()).select_from(Log).where(*base_filters)) or 0
    error_logs = (
        db.scalar(
            select(func.count())
            .select_from(Log)
            .where(*base_filters, func.upper(Log.level).in_(["ERROR", "CRITICAL"]))
        )
        or 0
    )

    top_error_type = db.execute(
        select(Log.error_type, func.count().label("count"))
        .where(*base_filters, Log.error_type.is_not(None))
        .group_by(Log.error_type)
        .order_by(func.count().desc())
        .limit(1)
    ).first()

    top_service = db.execute(
        select(Log.service_name, func.count().label("count"))
        .where(*base_filters, Log.service_name.is_not(None))
        .group_by(Log.service_name)
        .order_by(func.count().desc())
        .limit(1)
    ).first()

    recent_logs = db.scalars(
        select(Log)
        .where(*base_filters)
        .order_by(Log.created_at.desc(), Log.id.desc())
        .limit(settings.ollama_max_logs)
    ).all()

    return {
        "total_logs": total_logs,
        "error_logs": error_logs,
        "top_error_type": top_error_type[0] if top_error_type else None,
        "top_service": top_service[0] if top_service else None,
    }, recent_logs


def _build_rule_based_insights(
    project_id: uuid.UUID,
    lookback_minutes: int,
    metrics: dict[str, Any],
    recent_logs: list[Log],
) -> InsightsResponse:
    total_logs = metrics["total_logs"]
    error_logs = metrics["error_logs"]
    err_type_value = metrics["top_error_type"]
    service_value = metrics["top_service"]

    if error_logs == 0:
        root_cause = "No critical error pattern detected in the selected time window."
        suggestion = "Continue monitoring and increase lookback window if issue was earlier."
        incident_summary = "No active incident pattern was detected from recent logs."
        action_plan = [
            "Continue monitoring the service health dashboard.",
            "Increase the lookback window if the issue happened earlier.",
        ]
        confidence = 0.35
    else:
        root_cause = (
            f"Primary issue appears to be '{err_type_value or 'UnhandledError'}'"
            f" in service '{service_value or 'unknown-service'}'."
        )
        suggestion = (
            "Validate upstream dependencies, inspect recent deployments, and add retry/backoff around failing operations."
        )
        incident_summary = (
            f"Detected {error_logs} error log(s) out of {total_logs} total log(s) in the last {lookback_minutes} minutes. "
            f"Most frequent service: {service_value or 'unknown-service'}. "
            f"Most frequent error type: {err_type_value or 'UnhandledError'}."
        )
        action_plan = [
            "Inspect the most recent deployment or configuration change.",
            "Check upstream dependencies and network timeouts.",
            "Add retries or circuit breaking around the failing operation.",
        ]
        confidence = min(0.9, 0.5 + (error_logs / max(total_logs, 1)) * 0.4)

    return InsightsResponse(
        project_id=str(project_id),
        lookback_minutes=lookback_minutes,
        total_logs=total_logs,
        error_logs=error_logs,
        top_error_type=err_type_value,
        top_service=service_value,
        root_cause=root_cause,
        suggestion=suggestion,
        confidence=round(confidence, 2),
        incident_summary=incident_summary,
        action_plan=action_plan,
        timeline=_build_timeline(recent_logs),
        analysis_mode="fallback",
        model_name=None,
        fallback_reason=None,
    )


def _build_timeline(logs: list[Log]) -> list[InsightTimelineEvent]:
    return [
        InsightTimelineEvent(
            timestamp=row.created_at.isoformat(),
            level=row.level,
            service_name=row.service_name,
            message=row.message[:300],
            error_type=row.error_type,
            correlation_id=row.correlation_id,
        )
        for row in reversed(logs[-10:])
    ]


def _generate_llm_analysis(
    project_id: uuid.UUID,
    lookback_minutes: int,
    metrics: dict[str, Any],
    recent_logs: list[Log],
) -> InsightsResponse | None:
    prompt = _build_llm_prompt(project_id, lookback_minutes, metrics, recent_logs)
    try:
        response = requests.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": settings.ollama_temperature},
            },
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        content = response.json().get("response", "")
        parsed = _parse_llm_json(content)
        if not parsed:
            return None
    except (requests.RequestException, ValueError, KeyError):
        return None

    return InsightsResponse(
        project_id=str(project_id),
        lookback_minutes=lookback_minutes,
        total_logs=metrics["total_logs"],
        error_logs=metrics["error_logs"],
        top_error_type=metrics["top_error_type"],
        top_service=metrics["top_service"],
        root_cause=parsed["root_cause"],
        suggestion=parsed["suggestion"],
        confidence=_calibrate_confidence(parsed.get("confidence"), metrics),
        incident_summary=parsed["incident_summary"],
        action_plan=parsed["action_plan"],
        timeline=_build_timeline(recent_logs),
        analysis_mode="llm",
        model_name=settings.ollama_model,
        fallback_reason=None,
    )


def _build_llm_prompt(
    project_id: uuid.UUID,
    lookback_minutes: int,
    metrics: dict[str, Any],
    recent_logs: list[Log],
) -> str:
    safe_logs = []
    for row in recent_logs:
        safe_logs.append(
            {
                "timestamp": row.created_at.isoformat(),
                "service_name": row.service_name,
                "operation": row.operation,
                "level": row.level,
                "status": row.status,
                "message": row.message[: settings.ollama_max_chars_per_log],
                "error_type": row.error_type,
                "correlation_id": row.correlation_id,
            }
        )

    payload = {
        "project_id": str(project_id),
        "lookback_minutes": lookback_minutes,
        "metrics": metrics,
        "recent_logs": safe_logs,
    }

    return (
        "You are an SRE incident assistant. Analyze monitoring logs and return strict JSON only.\n"
        "Do not invent facts that are not supported by the logs.\n"
        "Keep suggestions concrete and safe.\n"
        "Return JSON with exactly these keys: root_cause, incident_summary, suggestion, confidence, action_plan.\n"
        "confidence must be a number between 0 and 1.\n"
        "action_plan must be an array of 3 short strings.\n"
        f"Input:\n{json.dumps(payload, ensure_ascii=True)}"
    )


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict):
        return None

    required = ["root_cause", "incident_summary", "suggestion", "confidence", "action_plan"]
    if any(key not in parsed for key in required):
        return None
    if not isinstance(parsed["action_plan"], list):
        return None

    action_plan = [str(item).strip() for item in parsed["action_plan"] if str(item).strip()]
    if not action_plan:
        return None

    return {
        "root_cause": str(parsed["root_cause"]).strip(),
        "incident_summary": str(parsed["incident_summary"]).strip(),
        "suggestion": str(parsed["suggestion"]).strip(),
        "confidence": parsed["confidence"],
        "action_plan": action_plan[:5],
    }


def _calibrate_confidence(raw_confidence: Any, metrics: dict[str, Any]) -> float:
    try:
        llm_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        llm_confidence = 0.45

    llm_confidence = max(0.0, min(1.0, llm_confidence))
    error_ratio = (metrics["error_logs"] / max(metrics["total_logs"], 1)) if metrics["total_logs"] else 0.0
    calibrated = (llm_confidence * 0.7) + (min(error_ratio, 1.0) * 0.3)
    return round(max(0.1, min(0.95, calibrated)), 2)
