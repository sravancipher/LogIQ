from app.schemas.alert import AlertTestResponse


class _FakeDb:
    def scalar(self, *_args, **_kwargs):
        return None


def test_alerts_test_endpoint(client, override_db, monkeypatch):
    from app.api.v1.routes import alerts as alerts_route

    override_db(_FakeDb())

    monkeypatch.setattr(
        alerts_route,
        "send_test_alert",
        lambda _payload, _config: AlertTestResponse(slack=True, teams=False, email=False),
    )

    response = client.post(
        "/api/v1/alerts/test",
        json={"title": "Test", "message": "Alert message", "severity": "HIGH"},
    )

    assert response.status_code == 200
    assert response.json() == {"slack": True, "teams": False, "email": False}


def test_insights_notify_sends_llm_error_notification_when_llm_unavailable(client, override_db, monkeypatch):
    from app.api.v1.routes import alerts as alerts_route
    from app.schemas.alert import InsightNotifyResponse
    from app.services.insights_service import LlmAnalysisUnavailableError

    override_db(_FakeDb())

    def _raise(**_kwargs):
        raise LlmAnalysisUnavailableError("LLM analysis is disabled for this project")

    monkeypatch.setattr(alerts_route, "build_insights", _raise)
    monkeypatch.setattr(
        alerts_route,
        "send_llm_error_notification",
        lambda reason, payload, config: InsightNotifyResponse(
            email=False,
            slack=True,
            teams=False,
            recipient_email=None,
            target_error_group="unknown-service / UnhandledError / unknown-operation",
            analysis_mode="llm_error",
            message="LLM error notification sent",
        ),
    )

    response = client.post("/api/v1/alerts/insights/notify", json={"channels": ["slack"]})

    # No fabricated insight content - a distinct, honest "LLM unavailable" notice instead.
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_mode"] == "llm_error"
    assert body["slack"] is True
