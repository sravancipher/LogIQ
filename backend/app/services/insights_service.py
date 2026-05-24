from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from requests import Response
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
        fallback=fallback,
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
        .limit(settings.resolved_llm_max_logs)
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
    fallback: InsightsResponse,
    deep_analysis: bool = False,
) -> InsightsResponse | None:
    model_name = settings.resolved_llm_model
    provider = settings.llm_provider.strip().lower()
    print(f"Requesting LLM analysis from provider '{provider}' using model '{model_name}' with deep_analysis={deep_analysis}")
    prompt = _build_llm_prompt(
        project_id,
        lookback_minutes,
        metrics,
        recent_logs,
    )
    try:
        response = _request_llm_completion(
            provider=provider,
            prompt=prompt,
            model_name=model_name,
            deep_analysis=deep_analysis,
        )
        response.raise_for_status()
        print(f"LLM response status: {response.status_code}")
        content = _extract_llm_content(response, provider)
        print(f"LLM raw content: {content[:500]}...")  # Print first 500 chars for debugging
        parsed = _parse_llm_json(content)
        print(f"LLM parsed content: {parsed}")
        if not parsed:
            partial_target_group = _extract_partial_target_error_group(content)
            if partial_target_group is not None:
                print(f"LLM partial content recovered as target_error_group: {partial_target_group}")
                return _merge_partial_llm_response(fallback, partial_target_group, model_name)
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
        model_name=model_name,
        fallback_reason=None,
    )


def _merge_partial_llm_response(
    fallback: InsightsResponse,
    target_error_group: dict[str, str],
    model_name: str,
) -> InsightsResponse:
    return InsightsResponse(
        project_id=fallback.project_id,
        lookback_minutes=fallback.lookback_minutes,
        total_logs=fallback.total_logs,
        error_logs=fallback.error_logs,
        top_error_type=fallback.top_error_type,
        top_service=fallback.top_service,
        root_cause=fallback.root_cause,
        suggestion=fallback.suggestion,
        confidence=fallback.confidence,
        incident_summary=fallback.incident_summary,
        action_plan=fallback.action_plan,
        error_groups=fallback.error_groups,
        target_error_group=InsightErrorGroupRef(
            service_name=target_error_group["service_name"],
            error_type=target_error_group["error_type"],
            operation=target_error_group["operation"],
        ),
        contributing_error_groups=fallback.contributing_error_groups,
        timeline=fallback.timeline,
        analysis_mode="llm",
        model_name=model_name,
        fallback_reason="LLM returned partial target_error_group only; rule-based report was reused",
    )


def _request_llm_completion(
    provider: str,
    prompt: str,
    model_name: str,
    deep_analysis: bool,
) -> Response:
    if provider in {"openai", "openai_compatible", "openai-compatible", "akash"}:
        return _request_openai_compatible(prompt=prompt, model_name=model_name)

    return _request_ollama(prompt=prompt, model_name=model_name, deep_analysis=deep_analysis)


def _request_ollama(prompt: str, model_name: str, deep_analysis: bool) -> Response:
    return requests.post(
        f"{settings.resolved_llm_base_url}/api/generate",
        json={
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": settings.resolved_llm_temperature,
                "think": deep_analysis,
            },
        },
        timeout=settings.resolved_llm_timeout_seconds,
    )


def _request_openai_compatible(prompt: str, model_name: str) -> Response:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    api_key = settings.resolved_llm_api_key
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    return requests.post(
        f"{settings.resolved_llm_base_url}/chat/completions",
        headers=headers,
        json={
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": settings.resolved_llm_temperature,
            "response_format": {"type": "json_object"},
        },
        timeout=settings.resolved_llm_timeout_seconds,
    )


def _extract_llm_content(response: Response, provider: str) -> str:
    payload = response.json()

    if provider in {"openai", "openai_compatible", "openai-compatible", "akash"}:
        return str(payload["choices"][0]["message"]["content"])

    return str(payload.get("response", ""))


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
                "message": row.message[: settings.resolved_llm_max_chars_per_log],
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
        "- Return the full schema below. Do not return only target_error_group or only service/error/operation fields.\n"
        "- If a field cannot be inferred, use null, an empty array, or a short honest explanation instead of omitting the key.\n"
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
    content = _strip_code_fences(content)

    # Try direct parse first; if that fails, find the first {...} JSON object in the response.
    parsed: Any = None
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(content)
        if candidate is None:
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None

    parsed = _unwrap_llm_payload(parsed)
    parsed = _normalize_llm_keys(parsed)

    if not isinstance(parsed, dict):
        print(f"LLM parse rejected: expected object, got {type(parsed).__name__}")
        return None

    required = ["root_cause", "incident_summary", "suggestion", "confidence", "action_plan"]
    missing = [key for key in required if key not in parsed]
    if missing:
        print(f"LLM parse rejected: missing required keys {missing}; raw keys were {sorted(parsed.keys())}")
        return None

    action_plan = _normalize_action_plan(parsed["action_plan"])
    if not action_plan:
        print("LLM parse rejected: action_plan was empty or unusable")
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


def _normalize_action_plan(raw_action_plan: Any) -> list[str]:
    if isinstance(raw_action_plan, list):
        return [str(item).strip() for item in raw_action_plan if str(item).strip()]

    if isinstance(raw_action_plan, str):
        lines = [line.strip() for line in raw_action_plan.splitlines() if line.strip()]
        if lines:
            return lines

        parts = [part.strip() for part in re.split(r"[;|]", raw_action_plan) if part.strip()]
        return parts

    return []


def _strip_code_fences(content: str) -> str:
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return content


def _extract_first_json_object(content: str) -> str | None:
    start = content.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(content)):
        char = content[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[start : index + 1]

    return None


def _unwrap_llm_payload(parsed: Any) -> Any:
    if not isinstance(parsed, dict):
        return parsed

    for key in ("analysis", "result", "data", "output", "response"):
        nested = parsed.get(key)
        if isinstance(nested, dict) and any(field in nested for field in ("root_cause", "incident_summary", "suggestion", "confidence", "action_plan")):
            return nested

    return parsed


def _extract_partial_target_error_group(content: str) -> dict[str, str] | None:
    try:
        parsed: Any = json.loads(_strip_code_fences(re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()))
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(content)
        if candidate is None:
            return None
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None

    parsed = _unwrap_llm_payload(parsed)
    parsed = _normalize_llm_keys(parsed)
    if not isinstance(parsed, dict):
        return None

    service_name = str(parsed.get("service_name", "")).strip()
    error_type = str(parsed.get("error_type", "")).strip()
    operation = str(parsed.get("operation", "")).strip()
    if service_name and error_type and operation:
        return {
            "service_name": service_name,
            "error_type": error_type,
            "operation": operation,
        }

    return None


def _normalize_llm_keys(parsed: Any) -> Any:
    if not isinstance(parsed, dict):
        return parsed

    alias_map = {
        "rootCause": "root_cause",
        "rootcause": "root_cause",
        "incidentSummary": "incident_summary",
        "incidentsummary": "incident_summary",
        "actionPlan": "action_plan",
        "actionplan": "action_plan",
        "targetErrorGroup": "target_error_group",
        "targeterrorgroup": "target_error_group",
        "contributingErrorGroups": "contributing_error_groups",
        "contributingerrorgroups": "contributing_error_groups",
        "suggestion": "suggestion",
        "confidence": "confidence",
    }

    normalized: dict[str, Any] = {}
    for key, value in parsed.items():
        normalized_key = alias_map.get(key, alias_map.get(key.replace("_", ""), key))
        normalized[normalized_key] = value

    return normalized


def _calibrate_confidence(raw_confidence: Any, metrics: dict[str, Any]) -> float:
    try:
        llm_confidence = float(raw_confidence)
    except (TypeError, ValueError):
        llm_confidence = 0.45

    llm_confidence = max(0.0, min(1.0, llm_confidence))
    error_ratio = (metrics["error_logs"] / max(metrics["total_logs"], 1)) if metrics["total_logs"] else 0.0
    calibrated = (llm_confidence * 0.7) + (min(error_ratio, 1.0) * 0.3)
    return round(max(0.1, min(0.95, calibrated)), 2)
