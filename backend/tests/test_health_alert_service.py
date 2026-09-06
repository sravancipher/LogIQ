import uuid
from datetime import datetime, timezone

from app.schemas.alert import AlertTestResponse
from app.services import health_alert_service
from app.services.health_alert_service import decide_alert
from app.services.health_service import ServiceHealth


def test_decide_alert_no_alert_when_healthy_and_never_alerted():
    assert decide_alert(last_alerted_status=None, current_status="healthy") is None


def test_decide_alert_fires_on_first_unhealthy_observation():
    severity, verb = decide_alert(last_alerted_status=None, current_status="degraded")
    assert severity == "MEDIUM"
    assert "degraded" in verb


def test_decide_alert_uses_critical_severity():
    severity, _ = decide_alert(last_alerted_status=None, current_status="critical")
    assert severity == "CRITICAL"


def test_decide_alert_does_not_repeat_for_unchanged_status():
    assert decide_alert(last_alerted_status="critical", current_status="critical") is None
    assert decide_alert(last_alerted_status="degraded", current_status="degraded") is None


def test_decide_alert_fires_again_on_severity_change():
    severity, _ = decide_alert(last_alerted_status="degraded", current_status="critical")
    assert severity == "CRITICAL"


def test_decide_alert_fires_recovery_notice():
    severity, verb = decide_alert(last_alerted_status="critical", current_status="healthy")
    assert severity == "LOW"
    assert "recovered" in verb


def test_decide_alert_no_recovery_noise_if_never_alerted():
    # Already healthy and never alerted before - nothing to "recover" from.
    assert decide_alert(last_alerted_status=None, current_status="healthy") is None
    assert decide_alert(last_alerted_status="healthy", current_status="healthy") is None


class _FakeDb:
    def __init__(self):
        self.added = []
        self.committed = False

    def scalar(self, *_args, **_kwargs):
        return None  # no prior ServiceHealthState row for any service in these tests

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


def test_check_project_services_alerts_on_new_critical_service(monkeypatch):
    project_id = uuid.uuid4()
    db = _FakeDb()

    monkeypatch.setattr(
        health_alert_service,
        "compute_service_health",
        lambda _db, _pid, _lookback: [
            ServiceHealth(
                service_name="payments",
                total_logs=10,
                error_logs=8,
                last_seen=datetime.now(timezone.utc),
                status="critical",
            ),
        ],
    )
    monkeypatch.setattr(health_alert_service, "resolve_alert_config", lambda _db, _pid: "fake-config")

    sent = []

    def _fake_send_test_alert(payload, config):
        sent.append((payload, config))
        return AlertTestResponse(slack=True, teams=False, email=False)

    monkeypatch.setattr(health_alert_service, "send_test_alert", _fake_send_test_alert)

    checked, alerts_sent = health_alert_service.check_project_services(db, project_id)

    assert checked == 1
    assert alerts_sent == 1
    assert len(sent) == 1
    payload, config = sent[0]
    assert payload.severity == "CRITICAL"
    assert "payments" in payload.title
    assert config == "fake-config"
    assert db.committed is True
    assert len(db.added) == 1
    assert db.added[0].last_alerted_status == "critical"


def test_check_project_services_sends_no_alert_when_all_healthy(monkeypatch):
    project_id = uuid.uuid4()
    db = _FakeDb()

    monkeypatch.setattr(
        health_alert_service,
        "compute_service_health",
        lambda _db, _pid, _lookback: [
            ServiceHealth(
                service_name="payments",
                total_logs=10,
                error_logs=0,
                last_seen=datetime.now(timezone.utc),
                status="healthy",
            ),
        ],
    )

    sent = []
    monkeypatch.setattr(health_alert_service, "send_test_alert", lambda payload, config: sent.append(1))

    checked, alerts_sent = health_alert_service.check_project_services(db, project_id)

    assert checked == 1
    assert alerts_sent == 0
    assert sent == []
    assert db.committed is True
