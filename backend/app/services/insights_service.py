from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.log import Log
from app.schemas.insight import (
    InsightDependentErrorGroup,
    InsightErrorGroup,
    InsightErrorGroupRef,
    InsightTimelineEvent,
    InsightsResponse,
)


def build_insights(
    db: Session,
    project_id: uuid.UUID,
    lookback_minutes: int,
    deep_analysis: bool = False,
) -> InsightsResponse:
    metrics, recent_logs = _collect_insight_inputs(db=db, project_id=project_id, lookback_minutes=lookback_minutes)
    fallback = _build_rule_based_insights(project_id, lookback_minutes, metrics, recent_logs)

    if not settings.llm_enabled:
        print("LLM analysis disabled, returning rule-based insights")
        fallback.fallback_reason = "LLM analysis disabled"
        return fallback

    llm_response = _generate_llm_analysis(
        project_id,
        lookback_minutes,
        metrics,
        recent_logs,
        deep_analysis=deep_analysis,
    )
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

    error_groups_rows = db.execute(
        select(
            func.coalesce(Log.service_name, "unknown-service").label("service_name"),
            func.coalesce(Log.error_type, "UnhandledError").label("error_type"),
            func.coalesce(Log.operation, "unknown-operation").label("operation"),
            func.count().label("count"),
            func.max(Log.created_at).label("last_seen"),
        )
        .where(*base_filters, func.upper(Log.level).in_(["ERROR", "CRITICAL"]))
        .group_by(Log.service_name, Log.error_type, Log.operation)
        .order_by(func.count().desc(), func.max(Log.created_at).desc())
        .limit(5)
    ).all()

    error_groups: list[InsightErrorGroup] = [
        InsightErrorGroup(
            service_name=str(row.service_name),
            error_type=str(row.error_type),
            operation=str(row.operation),
            count=int(row.count),
            last_seen=row.last_seen.isoformat() if row.last_seen else datetime.now(timezone.utc).isoformat(),
        )
        for row in error_groups_rows
    ]

    recent_logs = db.scalars(
        select(Log)
        .where(*base_filters)
        .order_by(Log.created_at.desc(), Log.id.desc())
        .limit(settings.ollama_max_logs)
    ).all()

    target_error_group = _to_group_ref(error_groups[0]) if error_groups else None
    contributing_error_groups = _infer_contributing_error_groups(recent_logs, error_groups)

    return {
        "total_logs": total_logs,
        "error_logs": error_logs,
        "top_error_type": top_error_type[0] if top_error_type else None,
        "top_service": top_service[0] if top_service else None,
        "error_groups": error_groups,
        "target_error_group": target_error_group,
        "contributing_error_groups": contributing_error_groups,
    }, recent_logs


def _group_key(service_name: str, error_type: str, operation: str) -> tuple[str, str, str]:
    return service_name, error_type, operation


def _to_group_ref(group: InsightErrorGroup) -> InsightErrorGroupRef:
    return InsightErrorGroupRef(
        service_name=group.service_name,
        error_type=group.error_type,
        operation=group.operation,
    )


def _infer_contributing_error_groups(
    recent_logs: list[Log],
    error_groups: list[InsightErrorGroup],
    max_items: int = 3,
) -> list[InsightDependentErrorGroup]:
    if len(error_groups) < 2:
        return []

    dominant = error_groups[0]
    dominant_key = _group_key(dominant.service_name, dominant.error_type, dominant.operation)
    other_groups = {
        _group_key(g.service_name, g.error_type, g.operation): g
        for g in error_groups[1:]
    }

    dominant_corr_ids: set[str] = set()
    other_corr_ids: dict[tuple[str, str, str], set[str]] = {}

    for row in recent_logs:
        if row.level.upper() not in {"ERROR", "CRITICAL"}:
            continue
        if not row.correlation_id:
            continue

        key = _group_key(
            row.service_name or "unknown-service",
            row.error_type or "UnhandledError",
            row.operation or "unknown-operation",
        )

        if key == dominant_key:
            dominant_corr_ids.add(row.correlation_id)
        elif key in other_groups:
            other_corr_ids.setdefault(key, set()).add(row.correlation_id)

    if not dominant_corr_ids:
        return []

    scored: list[tuple[tuple[str, str, str], int]] = []
    for key, corr_ids in other_corr_ids.items():
        overlap = len(corr_ids.intersection(dominant_corr_ids))
        if overlap > 0:
            scored.append((key, overlap))

    scored.sort(key=lambda item: item[1], reverse=True)

    return [
        InsightDependentErrorGroup(
            service_name=key[0],
            error_type=key[1],
            operation=key[2],
            shared_correlation_count=overlap,
        )
        for key, overlap in scored[:max_items]
    ]


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
        error_groups=metrics.get("error_groups", []),
        target_error_group=metrics.get("target_error_group"),
        contributing_error_groups=metrics.get("contributing_error_groups", []),
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
    deep_analysis: bool = False,
) -> InsightsResponse | None:
    prompt = _build_llm_prompt(
        project_id,
        lookback_minutes,
        metrics,
        recent_logs,
    )
    try:
        response = requests.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": settings.ollama_temperature,
                    "think": deep_analysis,
                },
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
        error_groups=metrics.get("error_groups", []),
        target_error_group=parsed.get("target_error_group") or metrics.get("target_error_group"),
        contributing_error_groups=parsed.get("contributing_error_groups")
        or metrics.get("contributing_error_groups", []),
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
    error_groups = metrics.get("error_groups", []) or []
    dominant_group = metrics.get("target_error_group")

    def _match_dominant_group(row: Log) -> bool:
        if dominant_group is None:
            return False
        return (
            (row.service_name or "unknown-service") == dominant_group.service_name
            and (row.error_type or "UnhandledError") == dominant_group.error_type
            and (row.operation or "unknown-operation") == dominant_group.operation
            and row.level.upper() in {"ERROR", "CRITICAL"}
        )

    dominant_group_logs = [row for row in recent_logs if _match_dominant_group(row)]
    remaining_logs = [row for row in recent_logs if row not in dominant_group_logs]

    safe_logs = []
    for row in dominant_group_logs + remaining_logs:
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

    safe_error_groups = [
        {
            "service_name": g.service_name,
            "error_type": g.error_type,
            "operation": g.operation,
            "count": g.count,
            "last_seen": g.last_seen,
        }
        for g in error_groups
    ]

    safe_target_group = None
    if metrics.get("target_error_group"):
        g = metrics["target_error_group"]
        safe_target_group = {
            "service_name": g.service_name,
            "error_type": g.error_type,
            "operation": g.operation,
        }

    safe_contributing_groups = [
        {
            "service_name": g.service_name,
            "error_type": g.error_type,
            "operation": g.operation,
            "shared_correlation_count": g.shared_correlation_count,
        }
        for g in (metrics.get("contributing_error_groups") or [])
    ]

    safe_metrics = {
        k: v
        for k, v in metrics.items()
        if k not in {"error_groups", "target_error_group", "contributing_error_groups"}
    }
    safe_metrics["error_groups"] = safe_error_groups
    safe_metrics["target_error_group"] = safe_target_group
    safe_metrics["contributing_error_groups"] = safe_contributing_groups

    payload = {
        "project_id": str(project_id),
        "lookback_minutes": lookback_minutes,
        "metrics": safe_metrics,
        "dominant_error_group": safe_target_group,
        "dependency_candidates": safe_contributing_groups,
        "recent_logs": safe_logs,
    }

    return (
        "You are an expert Site Reliability Engineer (SRE) and incident commander.\n"
        "Your job is to analyze application monitoring data and produce a precise, actionable incident report.\n"
        "\n"
        "STRICT RULES:\n"
        "- Respond with valid JSON only. No prose, no markdown, no code fences.\n"
        "- Base every statement ONLY on evidence present in the logs and metrics provided.\n"
        "- Do NOT speculate about causes that have no log evidence.\n"
        "- If logs are insufficient to determine a cause, say so honestly in root_cause.\n"
        "- Prioritize the highest-severity and most-frequent errors when forming your analysis.\n"
        "- Anchor the analysis on dominant_error_group first when it exists; treat other groups as secondary noise unless evidence proves a shared cause.\n"
        "- If multiple unrelated groups exist, root_cause must clearly name the primary group (service, error_type, operation).\n"
        "- Suggestion and action_plan must target target_error_group explicitly.\n"
        "- contributing_error_groups must include only groups with concrete evidence of dependency (e.g., shared correlation IDs).\n"
        "- Suggestions must be specific, safe, and immediately actionable by an on-call engineer.\n"
        "\n"
        "OUTPUT SCHEMA (return exactly these keys, nothing else):\n"
        "{\n"
        '  "root_cause": "<One clear sentence identifying the primary failure cause based on log evidence>",\n'
        '  "incident_summary": "<2-3 sentence summary: what failed, when, how often, which service>",\n'
        '  "suggestion": "<The single most impactful remediation step an engineer should take right now>",\n'
        '  "confidence": <float 0.0-1.0 — how confident you are given the log evidence quality>,\n'
        '  "target_error_group": {"service_name": "<str>", "error_type": "<str>", "operation": "<str>"} | null,\n'
        '  "contributing_error_groups": [{"service_name": "<str>", "error_type": "<str>", "operation": "<str>", "shared_correlation_count": <int>}],\n'
        '  "action_plan": [\n'
        '    "<Immediate step — do within the next 5 minutes>",\n'
        '    "<Short-term step — do within the next hour>",\n'
        '    "<Preventive step — do after the incident to stop recurrence>"\n'
        "  ]\n"
        "}\n"
        "\n"
        "CONFIDENCE GUIDE:\n"
        "  0.8-1.0 = clear repeating error with obvious root cause in logs\n"
        "  0.5-0.8 = probable cause with partial evidence\n"
        "  0.2-0.5 = insufficient logs; analysis is speculative\n"
        "  0.0-0.2 = no meaningful error signal detected\n"
        "\n"
        "MONITORING DATA:\n"
        f"{json.dumps(payload, ensure_ascii=True, indent=2)}"
    )


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    # Strip qwen3 / thinking-model <think>...</think> blocks before parsing.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    # Try direct parse first; if that fails, find the first {...} JSON object in the response.
    parsed: Any = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group())
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

    target_error_group = None
    raw_target = parsed.get("target_error_group")
    if isinstance(raw_target, dict):
        service_name = str(raw_target.get("service_name", "")).strip()
        error_type = str(raw_target.get("error_type", "")).strip()
        operation = str(raw_target.get("operation", "")).strip()
        if service_name and error_type and operation:
            target_error_group = {
                "service_name": service_name,
                "error_type": error_type,
                "operation": operation,
            }

    contributing_error_groups: list[dict[str, Any]] = []
    raw_contrib = parsed.get("contributing_error_groups", [])
    if isinstance(raw_contrib, list):
        for item in raw_contrib:
            if not isinstance(item, dict):
                continue
            service_name = str(item.get("service_name", "")).strip()
            error_type = str(item.get("error_type", "")).strip()
            operation = str(item.get("operation", "")).strip()
            try:
                shared = int(item.get("shared_correlation_count", 0))
            except (TypeError, ValueError):
                shared = 0
            if service_name and error_type and operation and shared > 0:
                contributing_error_groups.append(
                    {
                        "service_name": service_name,
                        "error_type": error_type,
                        "operation": operation,
                        "shared_correlation_count": shared,
                    }
                )

    return {
        "root_cause": str(parsed["root_cause"]).strip(),
        "incident_summary": str(parsed["incident_summary"]).strip(),
        "suggestion": str(parsed["suggestion"]).strip(),
        "confidence": parsed["confidence"],
        "action_plan": action_plan[:5],
        "target_error_group": target_error_group,
        "contributing_error_groups": contributing_error_groups[:5],
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
