from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

import requests

from app.core.config import settings
from app.schemas.alert import AlertTestRequest, AlertTestResponse, InsightNotifyRequest, InsightNotifyResponse
from app.schemas.insight import InsightsResponse


def _post_webhook(url: str | None, payload: dict) -> bool:
    if not url:
        return False
    try:
        response = requests.post(url, json=payload, timeout=10)
        return 200 <= response.status_code < 300
    except requests.RequestException:
        return False


def send_slack_alert(payload: AlertTestRequest) -> bool:
    body = {
        "text": f"[{payload.severity}] {payload.title}\n{payload.message}",
    }
    return _post_webhook(settings.slack_webhook_url, body)


def send_teams_alert(payload: AlertTestRequest) -> bool:
    body = {
        "title": f"[{payload.severity}] {payload.title}",
        "text": payload.message,
    }
    return _post_webhook(settings.teams_webhook_url, body)


def send_email_alert(payload: AlertTestRequest) -> bool:
    recipient = (payload.recipient_email or "").strip() or settings.alert_email_to

    if not all(
        [
            settings.smtp_host,
            settings.alert_email_from,
            recipient,
            settings.smtp_username,
            settings.smtp_password,
        ]
    ):
        return False

    msg = EmailMessage()
    msg["Subject"] = f"[{payload.severity}] {payload.title}"
    msg["From"] = settings.alert_email_from
    msg["To"] = recipient
    msg.set_content(payload.message)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(msg)
    except smtplib.SMTPException:
        return False

    return True


def send_test_alert(payload: AlertTestRequest) -> AlertTestResponse:
    return AlertTestResponse(
        slack=send_slack_alert(payload),
        teams=send_teams_alert(payload),
        email=send_email_alert(payload),
    )


def _group_label(group: Any) -> str:
    if not group:
        return "unknown-service / UnhandledError / unknown-operation"
    return f"{group.service_name} / {group.error_type} / {group.operation}"


def _resolve_focus_group(insights: InsightsResponse, payload: InsightNotifyRequest) -> tuple[str, str, str]:
    if payload.target_service_name and payload.target_error_type and payload.target_operation:
        return payload.target_service_name, payload.target_error_type, payload.target_operation

    target = insights.target_error_group
    if target:
        return target.service_name, target.error_type, target.operation

    if insights.error_groups:
        first = insights.error_groups[0]
        return first.service_name, first.error_type, first.operation

    return "unknown-service", "UnhandledError", "unknown-operation"


def send_insight_notify_email(insights: InsightsResponse, payload: InsightNotifyRequest) -> InsightNotifyResponse:
    service_name, error_type, operation = _resolve_focus_group(insights, payload)
    target_group = f"{service_name} / {error_type} / {operation}"

    action_lines = insights.action_plan[:3] if insights.action_plan else []
    action_text = "\n".join(f"{idx + 1}. {step}" for idx, step in enumerate(action_lines)) or "- none"

    note_text = f"\nUser Note:\n{payload.note.strip()}\n" if payload.note and payload.note.strip() else ""

    message = (
        f"Target Error Group:\n{target_group}\n\n"
        f"Root Cause:\n{insights.root_cause}\n\n"
        f"Suggested Fix:\n{insights.suggestion}\n\n"
        f"Action Plan:\n{action_text}\n"
        f"{note_text}"
    )

    send_payload = AlertTestRequest(
        title=f"[{payload.severity}] Insight Notification - {target_group}",
        message=message,
        severity=payload.severity,
        recipient_email=payload.recipient_email,
    )

    sent = send_email_alert(send_payload)
    return InsightNotifyResponse(
        email=sent,
        recipient_email=payload.recipient_email,
        target_error_group=target_group,
        analysis_mode=insights.analysis_mode,
        message="Insight notification sent" if sent else "Failed to send insight notification",
    )
