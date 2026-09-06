import uuid

from app.core.config import settings
from app.schemas.alert import AlertTestRequest
from app.services.alert_service import _escape_slack_text, _escape_teams_text, send_slack_alert, send_teams_alert
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
