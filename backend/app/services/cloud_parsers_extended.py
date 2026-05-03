"""
cloud_parsers_extended.py — Additional cloud service parsers
All functions follow the pattern: parse_X(raw, project_id) -> list[dict]
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def parse_activity_log(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Azure Activity Log events."""
    operation_name = raw.get("operationName", "Unknown")
    event_name = raw.get("eventName", operation_name)
    level_raw = raw.get("level", "Informational")
    level = "ERROR" if level_raw == "Error" else "WARN" if level_raw == "Warning" else "INFO"

    resource_group = raw.get("resourceGroupName", "")
    resource_name = raw.get("resourceName", "")
    provider = raw.get("resourceProvider", "")
    status = raw.get("status", "Succeeded")

    message = f"{event_name} on {resource_name} ({resource_group})"
    if status != "Succeeded":
        message += f" — {status}"

    return [
        dict(
            project_id=project_id,
            service_name=provider or "azure-service",
            operation="activity-log",
            level=level,
            status="error" if status != "Succeeded" else "ok",
            message=message[:2000],
            error_type=None if status == "Succeeded" else "ActivityLogError",
            correlation_id=raw.get("correlationId"),
            metadata_json={
                "resourceGroup": resource_group,
                "resourceName": resource_name,
                "provider": provider,
                "status": status,
            },
            source="azure-activity-log",
            created_at=_parse_iso(raw.get("eventTimestamp")) or datetime.now(timezone.utc),
        )
    ]


def parse_app_insights(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """Azure App Insights alerts."""
    alert_name = raw.get("AlertRuleName", "App Insights Alert")
    alert_context = raw.get("AlertContext", {})
    condition = alert_context.get("Condition", {})
    metric_value = condition.get("Value", 0)
    threshold = condition.get("Threshold", 0)

    level = "ERROR" if metric_value > threshold else "WARN"
    message = f"{alert_name}: metric={metric_value}, threshold={threshold}"

    return [
        dict(
            project_id=project_id,
            service_name="azure-app-insights",
            operation="app-insights-alert",
            level=level,
            status="error" if level == "ERROR" else "warn",
            message=message[:2000],
            error_type="AppInsightsAlert",
            correlation_id=raw.get("AlertId"),
            metadata_json={
                "metricValue": metric_value,
                "threshold": threshold,
                "alertName": alert_name,
            },
            source="azure-app-insights",
            created_at=_parse_iso(raw.get("Timestamp")) or datetime.now(timezone.utc),
        )
    ]


def parse_gcp_logging(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """GCP Cloud Logging entries."""
    proto = raw.get("protoPayload", {})
    json_payload = raw.get("jsonPayload", {})
    text_payload = raw.get("textPayload", "")

    severity = raw.get("severity", "DEFAULT")
    level = "ERROR" if severity == "ERROR" else "WARN" if severity == "WARNING" else "INFO"

    if proto:
        message = f"API call: {proto.get('methodName', 'unknown')}"
    elif json_payload:
        message = json.dumps(json_payload)[:2000]
    else:
        message = text_payload[:2000]

    resource = raw.get("resource", {})
    resource_type = resource.get("type", "unknown")
    labels = resource.get("labels", {})

    return [
        dict(
            project_id=project_id,
            service_name=labels.get("service_name") or resource_type,
            operation="gcp-logging",
            level=level,
            status="error" if level == "ERROR" else "ok",
            message=message,
            error_type=None,
            correlation_id=raw.get("trace"),
            metadata_json={
                "severity": severity,
                "resourceType": resource_type,
                "labels": labels,
            },
            source="gcp-cloud-logging",
            created_at=_parse_iso(raw.get("timestamp")) or datetime.now(timezone.utc),
        )
    ]


def parse_gcp_monitoring(raw: dict[str, Any], project_id: uuid.UUID) -> list[dict[str, Any]]:
    """GCP Cloud Monitoring (Alerting) incidents."""
    incident_id = raw.get("incident_id", str(uuid.uuid4()))
    incident_url = raw.get("incident_url", "")
    policy_name = raw.get("policy_name", "GCP Alert")
    condition_name = raw.get("condition_name", "")
    state = raw.get("state", "OPEN")

    level = "ERROR" if state == "OPEN" else "INFO"
    message = f"{policy_name}: {condition_name}"

    return [
        dict(
            project_id=project_id,
            service_name="gcp-monitoring",
            operation="monitoring-incident",
            level=level,
            status="error" if state == "OPEN" else "ok",
            message=message[:2000],
            error_type="MonitoringAlert",
            correlation_id=incident_id,
            metadata_json={
                "policyName": policy_name,
                "conditionName": condition_name,
                "state": state,
                "incidentUrl": incident_url,
            },
            source="gcp-cloud-monitoring",
            created_at=datetime.now(timezone.utc),
        )
    ]


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse ISO 8601 timestamp."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
