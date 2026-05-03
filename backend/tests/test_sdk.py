import asyncio

from monitor_sdk import Monitor, MonitorASGIMiddleware, set_correlation_id, reset_correlation_id


class _Resp:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _Session:
    def __init__(self, status_codes=None):
        self.calls = []
        self._codes = list(status_codes or [202])

    def post(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        code = self._codes.pop(0) if self._codes else 202
        return _Resp(code)


def test_monitor_batches_and_flushes_on_batch_size():
    session = _Session([202])
    monitor = Monitor(
        api_key="pm_test",
        base_url="http://localhost:8000",
        service_name="svc",
        batch_size=2,
        flush_interval=60,
        session=session,
        start_background=False,
    )

    monitor.info("one")
    assert len(session.calls) == 0

    monitor.error("two", error_type="RuntimeError")
    assert len(session.calls) == 1
    sent_logs = session.calls[0]["json"]["logs"]
    assert len(sent_logs) == 2
    assert sent_logs[0]["service_name"] == "svc"
    assert sent_logs[1]["level"] == "ERROR"


def test_monitor_retries_before_success():
    session = _Session([500, 500, 202])
    monitor = Monitor(
        api_key="pm_test",
        base_url="http://localhost:8000",
        batch_size=1,
        flush_interval=60,
        retry_backoff_seconds=0,
        max_retries=3,
        session=session,
        start_background=False,
    )

    monitor.info("hello")
    assert len(session.calls) == 3


def test_correlation_context_propagates_to_log_payload():
    session = _Session([202])
    monitor = Monitor(
        api_key="pm_test",
        base_url="http://localhost:8000",
        batch_size=1,
        flush_interval=60,
        session=session,
        start_background=False,
    )

    token = set_correlation_id("corr-123")
    try:
        monitor.info("message from request")
    finally:
        reset_correlation_id(token)

    sent = session.calls[0]["json"]["logs"][0]
    assert sent["correlation_id"] == "corr-123"


def test_capture_exception_includes_traceback_metadata():
    session = _Session([202])
    monitor = Monitor(
        api_key="pm_test",
        base_url="http://localhost:8000",
        batch_size=1,
        flush_interval=60,
        session=session,
        start_background=False,
    )

    try:
        raise ValueError("boom")
    except ValueError as exc:
        monitor.capture_exception(exc, operation="unit_test")

    sent = session.calls[0]["json"]["logs"][0]
    assert sent["level"] == "ERROR"
    assert sent["error_type"] == "ValueError"
    assert "traceback" in sent["metadata"]


def test_asgi_middleware_sets_correlation_and_logs_request():
    class _MonitorStub:
        def __init__(self):
            self.logs = []
            self.exceptions = []

        def log(self, **kwargs):
            self.logs.append(kwargs)

        def capture_exception(self, exc, **kwargs):
            self.exceptions.append((exc, kwargs))

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monitor = _MonitorStub()
    wrapped = MonitorASGIMiddleware(app, monitor)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/health",
        "headers": [(b"x-request-id", b"req-1")],
    }

    sent = []

    async def _recv():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def _send(msg):
        sent.append(msg)

    asyncio.run(wrapped(scope, _recv, _send))

    assert sent[0]["status"] == 200
    assert monitor.logs
    assert monitor.logs[0]["correlation_id"] == "req-1"
