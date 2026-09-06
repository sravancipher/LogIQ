from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import requests

from app.schemas.alert import AlertTestRequest, InsightNotifyRequest, InsightNotifyResponse, AlertTestResponse
from app.schemas.insight import InsightsResponse
from app.services.alert_settings_service import AlertChannelConfig

logger = logging.getLogger(__name__)


def _escape_slack_text(text: str) -> str:
    # Per Slack's own escaping rules: & < > must be replaced before building message
    # text, otherwise sequences like "<!channel>" or "<@Uxxx>" are parsed as live
    # mentions/links instead of rendered as literal text.
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_teams_text(text: str) -> str:
    # Teams MessageCard "text"/"title" fields render as markdown; escape the characters
    # that could otherwise inject unintended formatting or links.
    for char in ("\\", "*", "_", "~", "`", "[", "]", "(", ")"):
        text = text.replace(char, f"\\{char}")
    return text


def _post_webhook(url: str | None, payload: dict, channel: str) -> bool:
    if not url:
        return False
    try:
        response = requests.post(url, json=payload, timeout=10)
        if not (200 <= response.status_code < 300):
            logger.warning("%s webhook returned status %s", channel, response.status_code)
            return False
        return True
    except requests.RequestException:
        logger.exception("%s webhook request failed", channel)
        return False


def send_slack_alert(payload: AlertTestRequest, config: AlertChannelConfig) -> bool:
    body = {
        "text": f"[{payload.severity}] {_escape_slack_text(payload.title)}\n{_escape_slack_text(payload.message)}",
    }
    return _post_webhook(config.slack_webhook_url, body, channel="Slack")


def send_teams_alert(payload: AlertTestRequest, config: AlertChannelConfig) -> bool:
    # Microsoft retired the legacy Office 365 Connector "MessageCard" format (a plain
    # {"title": ..., "text": ...} body) in favor of Teams Workflows. The auto-generated
    # "When a Teams webhook request is received" flow reads the card from a top-level
    # "attachments" array (a Bot Framework Activity shape) - a bare AdaptiveCard at the
    # request root leaves that array null and sends the flow down the wrong branch.
    adaptive_card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptivecard.json",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"[{payload.severity}] {_escape_teams_text(payload.title)}",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": _escape_teams_text(payload.message),
                "wrap": True,
            },
        ],
    }
    body = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": adaptive_card,
            }
        ],
    }
    return _post_webhook(config.teams_webhook_url, body, channel="Teams")


def send_email_alert(payload: AlertTestRequest, config: AlertChannelConfig) -> bool:
    recipient = (payload.recipient_email or "").strip() or config.alert_email_to

    if not all(
        [
            config.smtp_host,
            config.alert_email_from,
            recipient,
            config.smtp_username,
            config.smtp_password,
        ]
    ):
        return False

    msg = EmailMessage()
    msg["Subject"] = f"[{payload.severity}] {payload.title}"
    msg["From"] = config.alert_email_from
    msg["To"] = recipient
    msg.set_content(payload.message)

    try:
        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(config.smtp_username, config.smtp_password)
            smtp.send_message(msg)
    except smtplib.SMTPException:
        logger.exception("SMTP send failed (host=%s, to=%s)", config.smtp_host, recipient)
        return False
    except OSError:
        logger.exception("SMTP connection failed (host=%s)", config.smtp_host)
        return False

    return True


def send_test_alert(payload: AlertTestRequest, config: AlertChannelConfig) -> AlertTestResponse:
    return AlertTestResponse(
        slack=send_slack_alert(payload, config),
        teams=send_teams_alert(payload, config),
        email=send_email_alert(payload, config),
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


def send_insight_notify_email(
    insights: InsightsResponse, payload: InsightNotifyRequest, config: AlertChannelConfig
) -> InsightNotifyResponse:
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

    sent = send_email_alert(send_payload, config)
    return InsightNotifyResponse(
        email=sent,
        recipient_email=payload.recipient_email,
        target_error_group=target_group,
        analysis_mode=insights.analysis_mode,
        message="Insight notification sent" if sent else "Failed to send insight notification",
    )
