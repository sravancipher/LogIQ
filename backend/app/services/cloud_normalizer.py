"""
cloud_normalizer.py — Universal Cloud Webhook Normalizer
---------------------------------------------------------
Parses webhooks from AWS, Azure, and GCP cloud services into normalized logs.

Supports:
  AWS:  CloudWatch, CloudTrail, GuardDuty, RDS, Lambda, Security Hub, EventBridge
  Azure: Monitor Alerts, Activity Log, App Insights, Service Health, Defender, AKS, Event Grid
  GCP:  Cloud Logging, Cloud Monitoring, Security Command Center
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import requests


# ═════════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT — Auto-routing by source
# ═════════════════════════════════════════════════════════════════════════════

def normalize_webhook(
    raw: dict[str, Any],
    project_id: uuid.UUID,
    source_hint: str | None = None,
) -> list[dict[str, Any]]:
    """
    Universal webhook normalizer. Routes to correct parser based on hints and payload shape.
    
    Args:
        raw: Raw webhook body (as dict)
        project_id: Project UUID
        source_hint: Optional hint like "cloudtrail", "guardduty", "activity_log", etc.
    
    Returns:
        List of normalized log dicts ready for Log model
    """
    # If explicit hint provided, try it first
    if source_hint:
        hint = source_hint.lower().strip().replace("-", "_")
        if hint in {"aws", "cloudwatch", "cloudwatch_alarm", "cloudwatch_logs"}:
            return normalize_aws(raw, project_id)
        if hint in {"cloudtrail"}:
            return _normalize_cloudtrail(raw, project_id)
        if hint in {"guardduty"}:
            return _normalize_guardduty(raw, project_id)
        if hint in {"rds", "lambda", "security_hub", "securityhub", "eventbridge"}:
            return _normalize_aws_event(raw, project_id)
        if hint in {"azure", "azure_monitor", "monitor", "action_group"}:
            return normalize_azure(raw, project_id)
        if hint in {"activity_log"}:
            return _normalize_activity_log(raw, project_id)
        if hint in {"app_insights", "application_insights", "insights"}:
            return _normalize_app_insights(raw, project_id)
        if hint in {"service_health", "defender", "aks", "event_grid"}:
            return _normalize_azure_generic(raw, project_id)
        if hint in {"gcp", "google", "gcp_logging", "cloud_logging", "security_command_center", "scc"}:
            return _normalize_gcp(raw, project_id)
        if hint in {"gcp_monitoring", "cloud_monitoring"}:
            return _normalize_gcp_monitoring(raw, project_id)
    
    # Auto-detect by payload structure
    # CloudTrail: Records[] with eventID
    if "Records" in raw and isinstance(raw.get("Records"), list):
        if raw["Records"] and "eventID" in raw["Records"][0]:
            return _normalize_cloudtrail(raw, project_id)
    
    # GuardDuty: detail.finding
    if "detail" in raw and "finding" in raw.get("detail", {}):
        return _normalize_guardduty(raw, project_id)

    # AWS EventBridge and service events
    if "detail-type" in raw and str(raw.get("source", "")).startswith("aws."):
        return _normalize_aws_event(raw, project_id)
    
    # Azure Activity Log: operationName or properties.eventName
    if "operationName" in raw or ("properties" in raw and "eventName" in raw.get("properties", {})):
        return _normalize_activity_log(raw, project_id)
    
    # App Insights: AlertRuleName or AlertContext
    if "AlertRuleName" in raw or "AlertContext" in raw:
        return _normalize_app_insights(raw, project_id)

    # Azure Event Grid / service health style payloads
    if "subject" in raw or "topic" in raw:
        return _normalize_azure_generic(raw, project_id)
    
    # GCP: logging payloads
    if "protoPayload" in raw or ("resource" in raw and "type" in raw.get("resource", {})):
        return _normalize_gcp(raw, project_id)

    # GCP monitoring incidents
    if "incident" in raw or "incident_url" in raw:
        return _normalize_gcp_monitoring(raw, project_id)
    
    # Default to AWS (CloudWatch Alarms + Logs)
    return normalize_aws(raw, project_id)


# ═════════════════════════════════════════════════════════════════════════════
# AWS PARSERS
# ═════════════════════════════════════════════════════════════════════════════

_AWS_SEVERITY_MAP = {
    "ALARM": "ERROR",
    "INSUFFICIENT_DATA": "WARN",
    "OK": "INFO",
}


def normalize_aws(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Legacy wrapper. Detects CloudWatch or direct logs."""
    msg_type = raw.get("Type")
    if msg_type == "SubscriptionConfirmation":
        subscribe_url = raw.get("SubscribeURL", "")
        if subscribe_url.startswith("https://sns.amazonaws.com/"):
            try:
                requests.get(subscribe_url, timeout=10)
            except Exception:
                pass
        return []

    if msg_type == "Notification":
        try:
            inner = json.loads(raw.get("Message", "{}"))
        except (json.JSONDecodeError, TypeError):
            inner = {}
        return _normalize_aws_message(inner, project_id)

    if "logEvents" in raw:
        return _normalize_aws_message(raw, project_id)

    if "AlarmName" in raw:
        return _normalize_aws_message(raw, project_id)

    return []


def _normalize_aws_message(msg: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    if "logEvents" in msg:
        log_group: str = msg.get("logGroup", "unknown")
        service = log_group.strip("/").split("/")[-1] or log_group
        events = msg.get("logEvents", [])
        rows = []
        for evt in events:
            raw_msg: str = evt.get("message", "")
            ts_ms = evt.get("timestamp")
            created = (
                datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                if ts_ms
                else datetime.now(timezone.utc)
            )
            level = _infer_level_from_text(raw_msg)
            rows.append(
                dict(
                    project_id=project_id,
                    service_name=service,
                    operation=msg.get("logStream", "cloudwatch"),
                    level=level,
                    status="ok" if level == "INFO" else "error",
                    message=raw_msg[:2000],
                    error_type=_infer_error_type(raw_msg),
                    correlation_id=evt.get("id"),
                    metadata_json={"logGroup": log_group, "logStream": msg.get("logStream")},
                    source="aws-cloudwatch",
                    created_at=created,
                )
            )
        return rows

    # Shape 2: CloudWatch Alarm
    alarm_name: str = msg.get("AlarmName", "UnknownAlarm")
    state: str = msg.get("NewStateValue", "ALARM").upper()
    level = _AWS_SEVERITY_MAP.get(state, "ERROR")
    description: str = msg.get("AlarmDescription") or msg.get("NewStateReason", "")
    region: str = msg.get("Region", "")
    account: str = msg.get("AWSAccountId", "")

    ts_str = msg.get("StateChangeTime")
    created = _parse_iso(ts_str) if ts_str else datetime.now(timezone.utc)

    return [
        dict(
            project_id=project_id,
            service_name=alarm_name,
            operation="cloudwatch-alarm",
            level=level,
            status="error" if level == "ERROR" else "ok",
            message=description[:2000] or f"Alarm {alarm_name} entered {state}",
            error_type="CloudWatchAlarm",
            correlation_id=msg.get("AlarmArn"),
            metadata_json={"state": state, "region": region, "account": account},
            source="aws-cloudwatch",
            created_at=created,
        )
    ]


def _normalize_cloudtrail(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    records = raw.get("Records", [])
    if not isinstance(records, list):
        return []

    rows: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue

        event_source = str(rec.get("eventSource", "aws-cloudtrail"))
        service_name = event_source.split(".", 1)[0] if "." in event_source else event_source
        event_name = str(rec.get("eventName", "CloudTrailEvent"))
        error_code = rec.get("errorCode")
        error_message = rec.get("errorMessage")
        user_identity = rec.get("userIdentity", {}) if isinstance(rec.get("userIdentity"), dict) else {}
        actor = user_identity.get("arn") or user_identity.get("principalId") or "unknown-principal"

        level = "ERROR" if error_code else "INFO"
        created = _parse_iso(str(rec.get("eventTime", ""))) if rec.get("eventTime") else datetime.now(timezone.utc)

        rows.append(
            dict(
                project_id=project_id,
                service_name=service_name,
                operation=event_name,
                level=level,
                status="error" if level == "ERROR" else "ok",
                message=(error_message or f"{event_name} by {actor}")[:2000],
                error_type="CloudTrailEvent" if not error_code else str(error_code),
                correlation_id=rec.get("eventID"),
                metadata_json={
                    "eventSource": event_source,
                    "eventCategory": rec.get("eventCategory"),
                    "awsRegion": rec.get("awsRegion"),
                    "readOnly": rec.get("readOnly"),
                },
                source="aws-cloudtrail",
                created_at=created,
            )
        )

    return rows


def _normalize_guardduty(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    detail = raw.get("detail", {}) if isinstance(raw.get("detail"), dict) else {}
    finding = detail.get("finding", {}) if isinstance(detail.get("finding"), dict) else detail

    severity_value = float(finding.get("severity", 0) or 0)
    if severity_value >= 7:
        level = "ERROR"
    elif severity_value >= 4:
        level = "WARN"
    else:
        level = "INFO"

    finding_type = str(finding.get("type", "GuardDutyFinding"))
    title = str(finding.get("title") or finding.get("description") or finding_type)
    created_hint = finding.get("updatedAt") or finding.get("createdAt") or raw.get("time")
    created = _parse_iso(str(created_hint)) if created_hint else datetime.now(timezone.utc)
    resource = finding.get("resource", {}) if isinstance(finding.get("resource"), dict) else {}

    return [
        dict(
            project_id=project_id,
            service_name=str(resource.get("resourceType", "guardduty")),
            operation="guardduty-finding",
            level=level,
            status="error" if level in ("ERROR", "WARN") else "ok",
            message=title[:2000],
            error_type=finding_type,
            correlation_id=finding.get("id") or raw.get("id"),
            metadata_json={
                "severity": severity_value,
                "region": finding.get("region") or raw.get("region"),
                "accountId": finding.get("accountId") or raw.get("account"),
            },
            source="aws-guardduty",
            created_at=created,
        )
    ]


def _normalize_aws_event(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    source = str(raw.get("source", "aws-eventbridge"))
    detail_type = str(raw.get("detail-type", "AwsEvent"))
    detail = raw.get("detail", {}) if isinstance(raw.get("detail"), dict) else {}

    severity_raw = str(
        detail.get("severity")
        or detail.get("severityLabel")
        or detail.get("state")
        or detail.get("status")
        or ""
    )
    level = _severity_to_level(severity_raw)

    message = str(
        detail.get("message")
        or detail.get("description")
        or detail.get("stateReason")
        or f"{detail_type} received"
    )

    created_hint = raw.get("time")
    created = _parse_iso(str(created_hint)) if created_hint else datetime.now(timezone.utc)
    service_name = source.replace("aws.", "") if source.startswith("aws.") else source

    return [
        dict(
            project_id=project_id,
            service_name=service_name,
            operation=detail_type,
            level=level,
            status="error" if level in ("ERROR", "WARN") else "ok",
            message=message[:2000],
            error_type=detail.get("errorCode") or detail.get("type") or "AwsServiceEvent",
            correlation_id=raw.get("id"),
            metadata_json={"source": source, "resources": raw.get("resources")},
            source="aws-eventbridge",
            created_at=created,
        )
    ]


# ---------------------------------------------------------------------------
# Azure
# ---------------------------------------------------------------------------

_AZURE_SEVERITY_MAP = {
    "Sev0": "ERROR",
    "Sev1": "ERROR",
    "Sev2": "WARN",
    "Sev3": "INFO",
    "Sev4": "DEBUG",
}


def normalize_azure(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Azure Monitor Alerts (Common Alert Schema) — unchanged from original."""
    data = raw.get("data", raw)
    essentials = data.get("essentials", {})
    alert_context = data.get("alertContext", {})

    alert_rule: str = essentials.get("alertRule") or raw.get("alertRule", "AzureAlert")
    severity_raw: str = essentials.get("severity", "Sev2")
    level = _AZURE_SEVERITY_MAP.get(severity_raw, "WARN")

    description: str = essentials.get("description") or ""
    fired_at_str = essentials.get("firedDateTime")
    created = _parse_iso(fired_at_str) if fired_at_str else datetime.now(timezone.utc)

    search_query = alert_context.get("SearchQuery", "")
    message = description or search_query or f"Azure alert '{alert_rule}' fired"

    targets: list[str] = essentials.get("alertTargetIDs", [])
    service = _azure_resource_name(targets[0]) if targets else alert_rule

    return [
        dict(
            project_id=project_id,
            service_name=service,
            operation="azure-monitor-alert",
            level=level,
            status="error" if level in ("ERROR", "WARN") else "ok",
            message=message[:2000],
            error_type="AzureMonitorAlert",
            correlation_id=essentials.get("alertId"),
            metadata_json={
                "severity": severity_raw,
                "monitorCondition": essentials.get("monitorCondition"),
                "signalType": essentials.get("signalType"),
                "monitoringService": essentials.get("monitoringService"),
                "searchQuery": search_query,
            },
            source="azure-monitor",
            created_at=created,
        )
    ]


def _normalize_activity_log(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Azure Activity Log — route to extended parser."""
    try:
        from app.services.cloud_parsers_extended import parse_activity_log
        return parse_activity_log(raw, project_id)
    except ImportError:
        return []


def _normalize_app_insights(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Azure App Insights — route to extended parser."""
    try:
        from app.services.cloud_parsers_extended import parse_app_insights
        return parse_app_insights(raw, project_id)
    except ImportError:
        return []


def _normalize_azure_generic(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    data = raw.get("data", {}) if isinstance(raw.get("data"), dict) else {}
    essentials = data.get("essentials", {}) if isinstance(data.get("essentials"), dict) else {}

    event_name = str(
        raw.get("eventType")
        or raw.get("subject")
        or essentials.get("alertRule")
        or "AzureEvent"
    )
    severity_raw = str(raw.get("level") or essentials.get("severity") or "Warning")
    level = _severity_to_level(severity_raw)

    message = str(
        data.get("message")
        or essentials.get("description")
        or f"{event_name} received"
    )

    target_ids = essentials.get("alertTargetIDs", []) if isinstance(essentials.get("alertTargetIDs"), list) else []
    service_name = _azure_resource_name(target_ids[0]) if target_ids else "azure-service"
    created_hint = raw.get("eventTime") or essentials.get("firedDateTime")
    created = _parse_iso(str(created_hint)) if created_hint else datetime.now(timezone.utc)

    return [
        dict(
            project_id=project_id,
            service_name=service_name,
            operation=event_name,
            level=level,
            status="error" if level in ("ERROR", "WARN") else "ok",
            message=message[:2000],
            error_type="AzureServiceEvent",
            correlation_id=raw.get("id") or essentials.get("alertId"),
            metadata_json={"topic": raw.get("topic"), "subject": raw.get("subject")},
            source="azure-event-grid",
            created_at=created,
        )
    ]


# ---------------------------------------------------------------------------
# GCP
# ---------------------------------------------------------------------------

def _normalize_gcp(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """GCP — routes to logging or monitoring parsers."""
    try:
        from app.services.cloud_parsers_extended import parse_gcp_logging, parse_gcp_monitoring
        
        # Cloud Logging
        if "protoPayload" in raw or "jsonPayload" in raw or "textPayload" in raw:
            return parse_gcp_logging(raw, project_id)
        
        # Cloud Monitoring
        if "incident" in raw or "incident_url" in raw:
            return parse_gcp_monitoring(raw, project_id)
    except ImportError:
        pass
    
    return []


def _normalize_gcp_monitoring(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """GCP monitoring specific parser route."""
    try:
        from app.services.cloud_parsers_extended import parse_gcp_monitoring
        return parse_gcp_monitoring(raw, project_id)
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _infer_level_from_text(text: str) -> str:
    upper = text.upper()
    if "ERROR" in upper or "EXCEPTION" in upper or "FATAL" in upper or "CRITICAL" in upper:
        return "ERROR"
    if "WARN" in upper:
        return "WARN"
    if "DEBUG" in upper:
        return "DEBUG"
    return "INFO"


def _infer_error_type(text: str) -> str | None:
    for candidate in (
        "TimeoutError", "ConnectionError", "NullPointerException",
        "OutOfMemoryError", "KeyError", "ValueError", "TypeError",
        "AttributeError", "IndexError", "RuntimeError",
    ):
        if candidate.lower() in text.lower():
            return candidate
    return None


def _azure_resource_name(resource_id: str) -> str:
    """Extract the last path segment of an Azure resource ID as a readable name."""
    if not resource_id:
        return "azure-resource"
    parts = resource_id.rstrip("/").split("/")
    return parts[-1] if parts else resource_id


def _parse_iso(ts: str) -> datetime:
    """Best-effort ISO 8601 parser with UTC fallback."""
    try:
        # Python 3.11+ handles Z; for 3.10 replace Z manually
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _severity_to_level(severity: str) -> str:
    normalized = severity.upper()
    if any(token in normalized for token in ("SEV0", "SEV1", "CRITICAL", "HIGH", "ERROR", "FAILED", "OPEN")):
        return "ERROR"
    if any(token in normalized for token in ("SEV2", "MEDIUM", "WARNING", "WARN")):
        return "WARN"
    if any(token in normalized for token in ("SEV3", "SEV4", "INFO", "OK", "RESOLVED", "CLOSED")):
        return "INFO"
    return "WARN"
