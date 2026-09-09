import uuid
from datetime import datetime, timezone

from app.services import chat_tools


class _Row:
    def __init__(self, id, created_at, message="msg", **kw):
        self.id = id
        self.created_at = created_at
        self.message = message
        self.service_name = kw.get("service_name", "svc")
        self.operation = kw.get("operation", "op")
        self.level = kw.get("level", "ERROR")
        self.status = kw.get("status", "error")
        self.error_type = kw.get("error_type", "TimeoutError")
        self.correlation_id = kw.get("correlation_id")


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    """scalars() responses are consumed in call order from `scalars_queue`; scalar()
    always returns `scalar_value` (get_log_context only ever calls it once)."""

    def __init__(self, scalars_queue=None, scalar_value=None):
        self._scalars_queue = list(scalars_queue or [])
        self._scalar_value = scalar_value

    def scalars(self, *_args, **_kwargs):
        rows = self._scalars_queue.pop(0) if self._scalars_queue else []
        return _ScalarsResult(rows)

    def scalar(self, *_args, **_kwargs):
        return self._scalar_value


def test_search_logs_returns_bounded_dicts():
    now = datetime.now(timezone.utc)
    db = _FakeDb(scalars_queue=[[_Row(2, now, "second"), _Row(1, now, "first")]])

    result = chat_tools.search_logs(db, uuid.uuid4(), chat_tools.SearchLogsArgs(limit=5))

    assert result["count"] == 2
    assert result["logs"][0]["log_id"] == 2
    assert result["logs"][0]["message"] == "second"


def test_search_logs_redacts_message_content():
    now = datetime.now(timezone.utc)
    db = _FakeDb(scalars_queue=[[_Row(1, now, "login failed password=hunter2secret")]])

    result = chat_tools.search_logs(db, uuid.uuid4(), chat_tools.SearchLogsArgs())

    assert "hunter2secret" not in result["logs"][0]["message"]


def test_get_log_context_reports_error_when_log_not_found():
    db = _FakeDb(scalar_value=None)

    result = chat_tools.get_log_context(db, uuid.uuid4(), chat_tools.GetLogContextArgs(log_id=999))

    assert "error" in result


def test_get_log_context_orders_before_and_after_chronologically():
    now = datetime.now(timezone.utc)
    target = _Row(5, now, "target")
    db = _FakeDb(
        scalar_value=target,
        scalars_queue=[
            [target, _Row(4, now, "before")],  # before query (desc order, includes target)
            [_Row(6, now, "after")],  # after query (asc order)
        ],
    )

    result = chat_tools.get_log_context(db, uuid.uuid4(), chat_tools.GetLogContextArgs(log_id=5))

    ids = [row["log_id"] for row in result["logs"]]
    assert ids == [4, 5, 6]


def test_tool_args_ignore_llm_supplied_project_id():
    # None of the tool argument schemas declare a project_id field, so even if the LLM
    # includes one in its tool-call JSON, it is silently dropped - the real project_id
    # always comes from the authenticated request, never from model output.
    args = chat_tools.SearchLogsArgs(**{"project_id": "some-other-project", "level": "ERROR"})

    assert not hasattr(args, "project_id")
    assert args.level == "ERROR"
