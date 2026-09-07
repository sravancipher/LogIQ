import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.models.log import Log
from app.schemas.insight import InsightsResponse
from app.services import insights_service
from app.services.insights_service import (
    _extract_llm_content,
    _request_anthropic_style,
    _request_azure_openai,
    _build_timeline,
    _merge_partial_llm_response,
    resolve_llm_config,
)


class _FakeScalarDb:
    def __init__(self, row=None):
        self._row = row

    def scalar(self, *_args, **_kwargs):
        return self._row


def _make_llm_settings_row(**overrides):
    defaults = dict(
        project_id=uuid.uuid4(),
        enabled=None,
        provider=None,
        base_url=None,
        model=None,
        api_key=None,
        temperature=None,
        api_version=None,
    )
    defaults.update(overrides)
    return type("LlmSettingsRow", (), defaults)()


def test_resolve_llm_config_with_no_override_matches_system_defaults():
    config = resolve_llm_config(_FakeScalarDb(row=None), uuid.uuid4())

    assert config.enabled == settings.llm_enabled
    assert config.provider == settings.llm_provider
    assert config.base_url == settings.resolved_llm_base_url
    assert config.model == settings.resolved_llm_model
    assert config.temperature == settings.resolved_llm_temperature


def test_resolve_llm_config_merges_partial_override_with_system_defaults():
    row = _make_llm_settings_row(enabled=True, model="llama3.1", api_key="proj-key")
    config = resolve_llm_config(_FakeScalarDb(row=row), uuid.uuid4())

    # Explicitly overridden fields win...
    assert config.enabled is True
    assert config.model == "llama3.1"
    assert config.api_key == "proj-key"
    # ...fields left None on the row still fall back to system defaults.
    assert config.provider == settings.llm_provider
    assert config.base_url == settings.resolved_llm_base_url
    assert config.temperature == settings.resolved_llm_temperature


def test_resolve_llm_config_anthropic_falls_back_to_public_default_base_url():
    # System default provider is "ollama" (per config.py), so an Anthropic override with
    # no base_url must NOT inherit Ollama's URL - it should use Anthropic's public endpoint.
    row = _make_llm_settings_row(enabled=True, provider="anthropic", api_key="sk-ant-...")
    config = resolve_llm_config(_FakeScalarDb(row=row), uuid.uuid4())

    assert config.provider == "anthropic"
    assert config.base_url == "https://api.anthropic.com"


def test_resolve_llm_config_azure_has_no_unsafe_default_base_url():
    # Azure has no universal default endpoint (it's account-specific) - if the project
    # didn't set one, base_url must come back blank rather than something misleading.
    row = _make_llm_settings_row(enabled=True, provider="azure_openai")
    config = resolve_llm_config(_FakeScalarDb(row=row), uuid.uuid4())

    assert config.provider == "azure_openai"
    assert config.base_url == ""


def test_request_azure_openai_uses_deployment_url_and_api_key_header(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(insights_service.requests, "post", fake_post)

    config = insights_service.LlmRuntimeConfig(
        enabled=True,
        provider="azure_openai",
        base_url="https://myresource.openai.azure.com",
        model="my-deployment",
        api_key="azure-key",
        temperature=0.2,
        timeout_seconds=20,
        max_tokens=2048,
        api_version="2024-06-01",
    )

    _request_azure_openai("prompt text", "my-deployment", config)

    assert "/openai/deployments/my-deployment/chat/completions" in captured["url"]
    assert "api-version=2024-06-01" in captured["url"]
    assert captured["headers"]["api-key"] == "azure-key"
    assert "Authorization" not in captured["headers"]
    assert "model" not in captured["json"]


def test_request_anthropic_style_sends_expected_headers_and_body(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(insights_service.requests, "post", fake_post)

    config = insights_service.LlmRuntimeConfig(
        enabled=True,
        provider="anthropic",
        base_url="https://api.anthropic.com",
        model="claude-3-5-sonnet-20241022",
        api_key="sk-ant-...",
        temperature=0.2,
        timeout_seconds=20,
        max_tokens=2048,
        api_version=None,
    )

    _request_anthropic_style("prompt text", "claude-3-5-sonnet-20241022", config)

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-..."
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["max_tokens"] == 2048
    assert captured["json"]["model"] == "claude-3-5-sonnet-20241022"


def test_extract_llm_content_handles_anthropic_and_bedrock_shape():
    class _Resp:
        def json(self):
            return {"content": [{"type": "text", "text": "hello from claude"}]}

    assert _extract_llm_content(_Resp(), "anthropic") == "hello from claude"
    assert _extract_llm_content(_Resp(), "bedrock") == "hello from claude"


def test_extract_llm_content_handles_azure_openai_shape():
    class _Resp:
        def json(self):
            return {"choices": [{"message": {"content": "hello from azure"}}]}

    assert _extract_llm_content(_Resp(), "azure_openai") == "hello from azure"


def _make_log(seconds_ago: int) -> Log:
    return Log(
        level="ERROR",
        message=f"log from {seconds_ago}s ago",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=seconds_ago),
    )


def test_collect_insight_inputs_filters_by_level(monkeypatch):
    captured_filters = {}

    class _FakeResult:
        def all(self):
            return []

        def first(self):
            return None

    class _FakeQueryDb:
        def scalar(self, stmt, *_args, **_kwargs):
            captured_filters["whereclause"] = str(stmt)
            return 0

        def execute(self, *_args, **_kwargs):
            return _FakeResult()

        def scalars(self, *_args, **_kwargs):
            return _FakeResult()

    insights_service._collect_insight_inputs(
        db=_FakeQueryDb(), project_id=uuid.uuid4(), lookback_minutes=60, levels=["WARN", "error"]
    )

    # The level filter must be case-normalized (upper) and present in the compiled query.
    assert "upper(logs.level) IN" in captured_filters["whereclause"]


def test_build_insights_echoes_levels_filter(monkeypatch):
    project_id = uuid.uuid4()
    fake_metrics = {
        "total_logs": 2,
        "error_logs": 0,
        "top_error_type": None,
        "top_service": None,
        "error_groups": [],
        "target_error_group": None,
        "contributing_error_groups": [],
    }

    monkeypatch.setattr(
        insights_service,
        "_collect_insight_inputs",
        lambda db, project_id, lookback_minutes, levels=None: (fake_metrics, []),
    )
    monkeypatch.setattr(
        insights_service,
        "resolve_llm_config",
        lambda db, project_id: insights_service.LlmRuntimeConfig(
            enabled=False,
            provider="ollama",
            base_url="",
            model="",
            api_key=None,
            temperature=0.1,
            timeout_seconds=10,
            max_tokens=2048,
        ),
    )
    monkeypatch.setattr(insights_service, "_save_latest_insight", lambda db, project_id, insights: None)

    result = insights_service.build_insights(
        db=None, project_id=project_id, lookback_minutes=60, levels=["WARN", "ERROR"]
    )

    assert result.levels_filter == ["WARN", "ERROR"]


class _FakeLatestInsightDb:
    """Minimal fake supporting the scalar-select-then-add/commit pattern used by
    _save_latest_insight, plus the added rows so a subsequent get_latest_insight-style
    lookup can find them (mirrors how a real Session behaves within one request)."""

    def __init__(self):
        self.rows = []
        self.committed = False

    def scalar(self, *_args, **_kwargs):
        return self.rows[0] if self.rows else None

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        self.committed = True


def test_save_and_get_latest_insight_round_trips():
    project_id = uuid.uuid4()
    db = _FakeLatestInsightDb()
    fallback = _make_fallback()
    fallback.levels_filter = ["ERROR"]

    insights_service._save_latest_insight(db, project_id, fallback)

    assert db.committed is True
    assert fallback.computed_at is not None  # stamped by _save_latest_insight

    result = insights_service.get_latest_insight(db, project_id)

    assert result.has_analysis is True
    assert result.insight.root_cause == fallback.root_cause
    assert result.insight.levels_filter == ["ERROR"]
    assert result.insight.computed_at == fallback.computed_at


def test_save_latest_insight_overwrites_existing_row_not_duplicates():
    project_id = uuid.uuid4()
    db = _FakeLatestInsightDb()

    insights_service._save_latest_insight(db, project_id, _make_fallback())
    insights_service._save_latest_insight(db, project_id, _make_fallback())

    assert len(db.rows) == 1


def test_get_latest_insight_reports_no_analysis_when_none_saved():
    result = insights_service.get_latest_insight(_FakeScalarDb(row=None), uuid.uuid4())

    assert result.has_analysis is False
    assert result.insight is None


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
