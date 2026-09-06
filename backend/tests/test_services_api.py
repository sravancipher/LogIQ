from datetime import datetime, timezone

from app.services.health_service import ServiceHealth


def test_list_services_returns_computed_health(client, override_db, monkeypatch):
    from app.api.v1.routes import services as services_route

    override_db(object())  # unused: compute_service_health is monkeypatched below

    monkeypatch.setattr(
        services_route,
        "compute_service_health",
        lambda db, project_id, lookback_minutes: [
            ServiceHealth(
                service_name="payments",
                total_logs=10,
                error_logs=5,
                last_seen=datetime.now(timezone.utc),
                status="degraded",
            )
        ],
    )

    response = client.get("/api/v1/services?lookback_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert len(body["services"]) == 1
    assert body["services"][0]["service_name"] == "payments"
    assert body["services"][0]["status"] == "degraded"


def test_run_health_check_endpoint_reports_counts(client, override_db, monkeypatch):
    from app.api.v1.routes import services as services_route

    override_db(object())  # unused: check_project_services is monkeypatched below
    monkeypatch.setattr(services_route, "check_project_services", lambda db, project_id: (3, 1))

    response = client.post("/api/v1/services/health-check")

    assert response.status_code == 200
    assert response.json() == {"services_checked": 3, "alerts_sent": 1}
