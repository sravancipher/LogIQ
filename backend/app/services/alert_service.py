from __future__ import annotations

import smtplib
from email.message import EmailMessage

import requests

from app.core.config import settings
from app.schemas.alert import AlertTestRequest, AlertTestResponse


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
    if not all(
        [
            settings.smtp_host,
            settings.alert_email_from,
            settings.alert_email_to,
            settings.smtp_username,
            settings.smtp_password,
        ]
    ):
        return False

    msg = EmailMessage()
    msg["Subject"] = f"[{payload.severity}] {payload.title}"
    msg["From"] = settings.alert_email_from
    msg["To"] = settings.alert_email_to
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
