import uuid

from app.core.config import settings
from app.schemas.alert import AlertTestRequest, InsightNotifyRequest
from app.schemas.insight import InsightsResponse
from app.services.alert_service import (
    _escape_slack_text,
    _escape_teams_text,
    send_insight_notification,
    send_slack_alert,
    send_teams_alert,
)
from app.services.alert_settings_service import resolve_alert_config


class _FakeScalarDb:
    def __init__(self, row=None):
        self._row = row

    def scalar(self, *_args, **_kwargs):
        return self._row


def _make_alert_settings_row(**overrides):
    defaults = dict(
        project_id=uuid.uuid4(),
        slack_webhook_url=None,
        teams_webhook_url=None,
        alert_email_from=None,
        alert_email_to=None,
        smtp_host=None,
        smtp_port=None,
        smtp_username=None,
        smtp_password=None,
    )
    defaults.update(overrides)
    return type("AlertSettingsRow", (), defaults)()


def test_resolve_alert_config_with_no_override_matches_system_defaults():
    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())

    assert config.slack_webhook_url == settings.slack_webhook_url
    assert config.smtp_port == settings.smtp_port


def test_resolve_alert_config_merges_partial_override_with_system_defaults():
    row = _make_alert_settings_row(slack_webhook_url="https://hooks.slack.com/services/project-specific")
    config = resolve_alert_config(_FakeScalarDb(row=row), uuid.uuid4())

    assert config.slack_webhook_url == "https://hooks.slack.com/services/project-specific"
    # Fields left unset on the row still fall back to system defaults.
    assert config.teams_webhook_url == settings.teams_webhook_url
    assert config.smtp_port == settings.smtp_port


def test_slack_text_escaping_neutralizes_channel_mention():
    assert _escape_slack_text("<!channel> urgent") == "&lt;!channel&gt; urgent"


def test_teams_text_escaping_neutralizes_markdown():
    assert _escape_teams_text("**bold** [link](http://evil.example)") == r"\*\*bold\*\* \[link\]\(http://evil.example\)"


def test_send_slack_alert_escapes_payload_before_posting(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("app.services.alert_service.requests.post", fake_post)

    payload = AlertTestRequest(title="<!channel> down", message="check <http://internal>", severity="HIGH")
    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.slack_webhook_url = "https://hooks.slack.com/services/test"

    result = send_slack_alert(payload, config)

    assert result is True
    assert "&lt;!channel&gt;" in captured["json"]["text"]
    assert "<!channel>" not in captured["json"]["text"]


def test_send_teams_alert_posts_a_valid_adaptive_card(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("app.services.alert_service.requests.post", fake_post)

    payload = AlertTestRequest(title="Payment timeout", message="Errors spiking", severity="HIGH")
    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.teams_webhook_url = "https://example.webhook.office.com/webhookb2/test"

    result = send_teams_alert(payload, config)

    assert result is True
    body = captured["json"]
    # The auto-generated Teams Workflow reads the card from a top-level "attachments"
    # array (Bot Framework Activity shape); a bare AdaptiveCard at the root leaves that
    # array null and misroutes the flow (observed as a Graph "not a ChatThread" error).
    assert body["type"] == "message"
    card = body["attachments"][0]["content"]
    assert card["type"] == "AdaptiveCard"
    assert "$schema" in card
    assert any("Payment timeout" in block["text"] for block in card["body"])
    assert any("Errors spiking" in block["text"] for block in card["body"])
    assert len(card["body"]) == 2  # no hidden target_email block when recipient_email is unset


def test_send_teams_alert_includes_hidden_target_email_block_when_provided(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

    def fake_post(url, json, timeout):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr("app.services.alert_service.requests.post", fake_post)

    payload = AlertTestRequest(
        title="Payment timeout", message="Errors spiking", severity="HIGH", recipient_email="owner@example.com"
    )
    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.teams_webhook_url = "https://example.webhook.office.com/webhookb2/test"

    send_teams_alert(payload, config)

    card = captured["json"]["attachments"][0]["content"]
    assert len(card["body"]) == 3
    target_block = card["body"][2]
    assert target_block == {
        "type": "TextBlock",
        "id": "target_email",
        "text": "owner@example.com",
        "isVisible": False,
    }


def _make_insights(**overrides) -> InsightsResponse:
    defaults = dict(
        project_id=str(uuid.uuid4()),
        lookback_minutes=60,
        total_logs=5,
        error_logs=2,
        top_error_type="TimeoutError",
        top_service="payment-service",
        root_cause="Primary issue appears to be 'TimeoutError' in service 'payment-service'.",
        suggestion="Validate upstream dependencies.",
        confidence=0.7,
        incident_summary="Detected 2 error log(s).",
        action_plan=["Inspect upstream service"],
        analysis_mode="fallback",
        model_name=None,
        fallback_reason=None,
    )
    defaults.update(overrides)
    return InsightsResponse(**defaults)


def test_send_insight_notification_only_hits_selected_channels(monkeypatch):
    posted_urls = []

    class _Resp:
        status_code = 200

    def fake_post(url, json, timeout):
        posted_urls.append(url)
        return _Resp()

    monkeypatch.setattr("app.services.alert_service.requests.post", fake_post)

    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.slack_webhook_url = "https://hooks.slack.com/services/test"
    config.teams_webhook_url = "https://example.webhook.office.com/webhookb2/test"
    # No SMTP config, so email would fail even if selected - but it isn't selected here.

    payload = InsightNotifyRequest(channels=["slack", "teams"])
    result = send_insight_notification(_make_insights(), payload, config)

    assert result.slack is True
    assert result.teams is True
    assert result.email is False
    assert posted_urls == [config.slack_webhook_url, config.teams_webhook_url]


def test_send_insight_notification_requires_recipient_email_for_email_channel():
    import pytest

    with pytest.raises(ValueError, match="recipient_email is required"):
        InsightNotifyRequest(channels=["email"])


def test_insight_notify_rejects_non_https_teams_webhook_url():
    import pytest

    with pytest.raises(ValueError, match="https://"):
        InsightNotifyRequest(channels=["teams"], teams_webhook_url="http://insecure.example.com/hook")


def test_send_insight_notification_ad_hoc_teams_webhook_overrides_saved_one(monkeypatch):
    posted_urls = []

    class _Resp:
        status_code = 200

    def fake_post(url, json, timeout):
        posted_urls.append(url)
        return _Resp()

    monkeypatch.setattr("app.services.alert_service.requests.post", fake_post)

    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.teams_webhook_url = "https://example.webhook.office.com/webhookb2/saved-channel"

    ad_hoc_url = "https://example.webhook.office.com/webhookb2/one-to-one-chat"
    payload = InsightNotifyRequest(channels=["teams"], teams_webhook_url=ad_hoc_url)
    result = send_insight_notification(_make_insights(), payload, config)

    assert result.teams is True
    assert posted_urls == [ad_hoc_url]
    # The project's saved webhook must be untouched by the override.
    assert config.teams_webhook_url == "https://example.webhook.office.com/webhookb2/saved-channel"


def test_send_insight_notification_falls_back_to_saved_teams_webhook_when_ad_hoc_blank(monkeypatch):
    posted_urls = []

    class _Resp:
        status_code = 200

    def fake_post(url, json, timeout):
        posted_urls.append(url)
        return _Resp()

    monkeypatch.setattr("app.services.alert_service.requests.post", fake_post)

    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.teams_webhook_url = "https://example.webhook.office.com/webhookb2/saved-channel"

    payload = InsightNotifyRequest(channels=["teams"])
    result = send_insight_notification(_make_insights(), payload, config)

    assert result.teams is True
    assert posted_urls == [config.teams_webhook_url]


def test_send_insight_notification_email_only_does_not_touch_webhooks(monkeypatch):
    calls = {"webhook": 0}

    def fake_post_webhook(url, payload, channel):
        calls["webhook"] += 1
        return True

    monkeypatch.setattr("app.services.alert_service._post_webhook", fake_post_webhook)
    monkeypatch.setattr("app.services.alert_service.send_email_alert", lambda payload, config: True)

    config = resolve_alert_config(_FakeScalarDb(row=None), uuid.uuid4())
    config.slack_webhook_url = "https://hooks.slack.com/services/test"
    config.teams_webhook_url = "https://example.webhook.office.com/webhookb2/test"

    payload = InsightNotifyRequest(channels=["email"], recipient_email="owner@example.com")
    result = send_insight_notification(_make_insights(), payload, config)

    assert result.email is True
    assert result.slack is False
    assert result.teams is False
    assert calls["webhook"] == 0
