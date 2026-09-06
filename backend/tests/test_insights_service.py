import uuid
from datetime import datetime, timedelta, timezone

from app.models.log import Log
from app.schemas.insight import InsightsResponse
from app.services.insights_service import _build_timeline, _merge_partial_llm_response


def _make_log(seconds_ago: int) -> Log:
    return Log(
        level="ERROR",
        message=f"log from {seconds_ago}s ago",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
    )


def test_build_timeline_returns_newest_logs_oldest_first():
    # recent_logs is ordered created_at DESC (index 0 = newest).
    logs = [_make_log(seconds_ago) for seconds_ago in range(25)]

    timeline = _build_timeline(logs)

    assert len(timeline) == 10
    assert timeline[0].message == "log from 9s ago"
    assert timeline[-1].message == "log from 0s ago"


def _make_fallback() -> InsightsResponse:
    return InsightsResponse(
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
        action_plan=["Inspect upstream service"],
        analysis_mode="fallback",
        model_name=None,
        fallback_reason=None,
    )


def test_merge_partial_llm_response_reports_fallback_mode():
    fallback = _make_fallback()
    target_error_group = {
        "service_name": "payment-service",
        "error_type": "TimeoutError",
        "operation": "charge",
    }

    result = _merge_partial_llm_response(fallback, target_error_group, model_name="qwen3:4b-q4_K_M")

    # All narrative content is reused verbatim from the rule-based fallback, so
    # analysis_mode must say "fallback", not "llm" - see fallback_reason for detail.
    assert result.analysis_mode == "fallback"
    assert result.root_cause == fallback.root_cause
    assert result.suggestion == fallback.suggestion
    assert result.target_error_group.service_name == "payment-service"
    assert "target_error_group only" in result.fallback_reason
