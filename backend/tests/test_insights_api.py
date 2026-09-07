import uuid
from datetime import datetime, timezone

from app.schemas.insight import InsightsResponse, LatestInsightResponse


def test_insights_endpoint_falls_back_when_llm_disabled(client, monkeypatch):
    from app.api.v1.routes import insights as insights_route

    monkeypatch.setattr(
        insights_route,
        "build_insights",
        lambda db, project_id, lookback_minutes, deep_analysis=False, levels=None: InsightsResponse(
            project_id=str(project_id),
            lookback_minutes=lookback_minutes,
            total_logs=3,
            error_logs=1,
            top_error_type="TimeoutError",
            top_service="payment-service",
            root_cause="Primary issue appears to be 'TimeoutError' in service 'payment-service'.",
            suggestion="Validate upstream dependencies.",
            confidence=0.61,
            incident_summary="Detected one timeout incident.",
            action_plan=["Inspect upstream service", "Review deployment", "Add retries"],
            timeline=[],
            analysis_mode="fallback",
            model_name=None,
            fallback_reason="LLM analysis disabled",
        ),
    )

    response = client.get("/api/v1/insights?lookback_minutes=60")

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_mode"] == "fallback"
    assert body["incident_summary"] == "Detected one timeout incident."
    assert len(body["action_plan"]) == 3


def test_latest_insight_endpoint_returns_no_analysis_when_never_computed(client, monkeypatch):
    from app.api.v1.routes import insights as insights_route

    monkeypatch.setattr(
        insights_route, "get_latest_insight", lambda db, project_id: LatestInsightResponse(has_analysis=False)
    )

    response = client.get("/api/v1/insights/latest")

    assert response.status_code == 200
    assert response.json() == {"has_analysis": False, "insight": None}


def test_latest_insight_endpoint_returns_cached_analysis(client, monkeypatch):
    from app.api.v1.routes import insights as insights_route

    cached = InsightsResponse(
        project_id=str(uuid.uuid4()),
        lookback_minutes=60,
        total_logs=3,
        error_logs=1,
        top_error_type="TimeoutError",
        top_service="payment-service",
        root_cause="Primary issue appears to be 'TimeoutError' in service 'payment-service'.",
        suggestion="Validate upstream dependencies.",
        confidence=0.61,
        incident_summary="Detected one timeout incident.",
        analysis_mode="fallback",
        computed_at="2026-09-07T09:00:00+00:00",
    )
    monkeypatch.setattr(
        insights_route, "get_latest_insight", lambda db, project_id: LatestInsightResponse(has_analysis=True, insight=cached)
    )

    response = client.get("/api/v1/insights/latest")

    assert response.status_code == 200
    body = response.json()
    assert body["has_analysis"] is True
    assert body["insight"]["computed_at"] == "2026-09-07T09:00:00+00:00"


class _FakeDb:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)


def test_insight_feedback_endpoint_saves_feedback(client, override_db):
    db = _FakeDb()
    override_db(db)

    response = client.post(
        "/api/v1/insights/feedback",
        json={
            "rating": "down",
            "lookback_minutes": 60,
            "root_cause": "Wrong diagnosis",
            "suggestion": "Wrong action",
            "incident_summary": "Bad summary",
            "analysis_mode": "llm",
            "model_name": "qwen3:4b-q4_K_M",
            "correction": "Real issue was a DNS outage",
        },
    )

    assert response.status_code == 201
    assert response.json()["message"] == "Feedback recorded"
    assert db.committed is True
    assert len(db.added) == 1
    assert db.added[0].rating == "down"
