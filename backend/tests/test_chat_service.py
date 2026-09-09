import uuid
from datetime import datetime, timezone

from app.services import chat_service
from app.services.insights_service import LlmRuntimeConfig


def _llm_config(enabled=True, model="qwen3:4b-q4_K_M") -> LlmRuntimeConfig:
    return LlmRuntimeConfig(
        enabled=enabled,
        provider="ollama",
        base_url="http://localhost:11434",
        model=model,
        api_key=None,
        temperature=0.1,
        timeout_seconds=20,
        max_tokens=2048,
    )


class _Row:
    def __init__(self, id, message="msg"):
        self.id = id
        self.created_at = datetime.now(timezone.utc)
        self.message = message
        self.service_name = "smarthub-backend"
        self.operation = "op"
        self.level = "ERROR"
        self.status = "error"
        self.error_type = "TokenExpiredError"
        self.correlation_id = None
        self.source_file = "/app/auth/tokens.py"
        self.source_line = 42


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    def scalars(self, *_args, **_kwargs):
        return _ScalarsResult([_Row(1, "JWT token expired")])

    def scalar(self, *_args, **_kwargs):
        return None


def test_investigate_returns_disabled_message_when_llm_disabled(monkeypatch):
    monkeypatch.setattr(chat_service, "resolve_llm_config", lambda db, project_id: _llm_config(enabled=False))

    result = chat_service.investigate(_FakeDb(), uuid.uuid4(), "why did it fail?", 60)

    assert result.analysis_mode == "unavailable"
    assert "disabled" in result.answer.lower()


def test_investigate_calls_a_tool_then_returns_grounded_final_answer(monkeypatch):
    monkeypatch.setattr(chat_service, "resolve_llm_config", lambda db, project_id: _llm_config())

    responses = [
        {"action": "call_tool", "tool": "search_logs", "arguments": {"level": "ERROR"}},
        {
            "action": "final_answer",
            "answer": "JWT tokens were expiring, causing authentication failures.",
            "evidence": [{"description": "1 matching error log", "log_id": 1}],
            "confidence": "high",
        },
    ]
    monkeypatch.setattr(chat_service, "_call_llm", lambda llm_config, prompt: responses.pop(0))

    result = chat_service.investigate(_FakeDb(), uuid.uuid4(), "why did smarthub fail?", 60)

    assert result.analysis_mode == "llm"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool == "search_logs"
    assert result.evidence[0].log_id == 1


def test_investigate_drops_evidence_log_id_that_was_never_seen(monkeypatch):
    monkeypatch.setattr(chat_service, "resolve_llm_config", lambda db, project_id: _llm_config())
    monkeypatch.setattr(
        chat_service,
        "_call_llm",
        lambda llm_config, prompt: {
            "action": "final_answer",
            "answer": "No evidence was actually retrieved.",
            "evidence": [{"description": "hallucinated", "log_id": 999}],
            "confidence": "low",
        },
    )

    result = chat_service.investigate(_FakeDb(), uuid.uuid4(), "why?", 60)

    assert result.evidence[0].log_id is None


def test_investigate_reports_unreachable_llm_without_pretending_to_answer(monkeypatch):
    monkeypatch.setattr(chat_service, "resolve_llm_config", lambda db, project_id: _llm_config())
    monkeypatch.setattr(chat_service, "_call_llm", lambda llm_config, prompt: None)

    result = chat_service.investigate(_FakeDb(), uuid.uuid4(), "why?", 60)

    assert result.analysis_mode == "unavailable"
    assert "unreachable" in result.answer.lower()
    assert result.tool_calls == []


def test_investigate_stops_after_max_tool_calls_without_hallucinating_an_answer(monkeypatch):
    monkeypatch.setattr(chat_service, "resolve_llm_config", lambda db, project_id: _llm_config())
    monkeypatch.setattr(
        chat_service,
        "_call_llm",
        lambda llm_config, prompt: {"action": "call_tool", "tool": "get_latest_insight", "arguments": {}},
    )

    result = chat_service.investigate(_FakeDb(), uuid.uuid4(), "why?", 60)

    assert result.analysis_mode == "unavailable"
    assert len(result.tool_calls) == chat_service.MAX_TOOL_CALLS
    assert "budget" in result.answer.lower()
