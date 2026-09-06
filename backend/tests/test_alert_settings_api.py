class _FakeAlertSettingsDb:
    """Minimal fake DB supporting the single scalar(select(AlertSettings)...) query
    used by the alert-settings routes, plus add/commit/delete."""

    def __init__(self, existing_row=None):
        self.row = existing_row
        self.added = []
        self.deleted = []
        self.committed = False

    def scalar(self, *_args, **_kwargs):
        return self.row

    def add(self, obj):
        self.added.append(obj)
        self.row = obj

    def commit(self):
        self.committed = True

    def delete(self, obj):
        self.deleted.append(obj)
        self.row = None


def test_get_alert_settings_with_no_override_returns_system_defaults(client, override_db):
    db = _FakeAlertSettingsDb(existing_row=None)
    override_db(db)

    response = client.get("/api/v1/alert-settings")

    assert response.status_code == 200
    body = response.json()
    # With no project override, the response reflects system-wide settings verbatim
    # (whatever they are in this environment) rather than any project-specific config.
    assert body["has_override"] is False


def test_put_alert_settings_creates_override_and_hides_secrets(client, override_db):
    db = _FakeAlertSettingsDb(existing_row=None)
    override_db(db)

    response = client.put(
        "/api/v1/alert-settings",
        json={
            "slack_webhook_url": "https://hooks.slack.com/services/xyz",
            "alert_email_from": "alerts@example.com",
            "alert_email_to": "oncall@example.com",
            "smtp_host": "smtp.example.com",
            "smtp_port": 587,
            "smtp_username": "user",
            "smtp_password": "super-secret",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_override"] is True
    assert body["slack_configured"] is True
    assert body["smtp_password_configured"] is True
    assert "slack_webhook_url" not in body
    assert "smtp_password" not in body
    assert db.committed is True
    assert db.row.smtp_password == "super-secret"


def test_put_alert_settings_rejects_malformed_email(client, override_db):
    db = _FakeAlertSettingsDb(existing_row=None)
    override_db(db)

    response = client.put(
        "/api/v1/alert-settings",
        json={"alert_email_to": "not-an-email"},
    )

    assert response.status_code == 422


def test_delete_alert_settings_removes_override(client, override_db):
    existing = type("Row", (), dict(project_id="x"))()
    db = _FakeAlertSettingsDb(existing_row=existing)
    override_db(db)

    response = client.delete("/api/v1/alert-settings")

    assert response.status_code == 204
    assert db.deleted == [existing]
    assert db.committed is True
