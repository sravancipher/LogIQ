import uuid
from datetime import datetime, timezone


class _FakeLlmSettingsDb:
    """Minimal fake DB supporting the single scalar(select(LlmSettings)...) query
    used by the llm-settings routes, plus add/commit/delete."""

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


def test_get_llm_settings_with_no_override_returns_system_defaults(client, override_db):
    db = _FakeLlmSettingsDb(existing_row=None)
    override_db(db)

    response = client.get("/api/v1/llm-settings")

    assert response.status_code == 200
    body = response.json()
    assert body["has_override"] is False
    assert body["api_key_configured"] is False
    # System default from config.py is llm_enabled=False when unconfigured.
    assert body["enabled"] is False


def test_put_llm_settings_creates_override_and_hides_api_key(client, override_db):
    db = _FakeLlmSettingsDb(existing_row=None)
    override_db(db)

    response = client.put(
        "/api/v1/llm-settings",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3",
            "api_key": "super-secret",
            "temperature": 0.2,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_override"] is True
    assert body["enabled"] is True
    assert body["provider"] == "ollama"
    assert body["base_url"] == "http://localhost:11434"
    assert body["model"] == "llama3"
    assert body["temperature"] == 0.2
    assert body["api_key_configured"] is True
    assert "api_key" not in body
    assert db.committed is True
    assert db.row.api_key == "super-secret"


def test_put_llm_settings_omitting_api_key_keeps_existing_key(client, override_db):
    existing = type(
        "Row",
        (),
        dict(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            enabled=True,
            provider="ollama",
            base_url="http://localhost:11434",
            model="llama3",
            api_key="already-set",
            temperature=0.2,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )()
    db = _FakeLlmSettingsDb(existing_row=existing)
    override_db(db)

    response = client.put(
        "/api/v1/llm-settings",
        json={
            "enabled": True,
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llama3.1",
            "temperature": 0.5,
        },
    )

    assert response.status_code == 200
    assert db.row.api_key == "already-set"
    assert db.row.model == "llama3.1"


def test_delete_llm_settings_removes_override(client, override_db):
    existing = type("Row", (), dict(project_id=uuid.uuid4()))()
    db = _FakeLlmSettingsDb(existing_row=existing)
    override_db(db)

    response = client.delete("/api/v1/llm-settings")

    assert response.status_code == 204
    assert db.deleted == [existing]
    assert db.committed is True


def test_test_llm_settings_when_disabled_reports_failure_not_crash(client, override_db):
    db = _FakeLlmSettingsDb(existing_row=None)
    override_db(db)

    response = client.post("/api/v1/llm-settings/test")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "disabled" in body["message"].lower()
