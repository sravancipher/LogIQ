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
