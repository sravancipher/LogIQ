from __future__ import annotations

import time
import uuid
from typing import Any, Callable

from monitor_sdk.context import reset_correlation_id, set_correlation_id


class MonitorASGIMiddleware:
    """ASGI middleware that propagates correlation IDs and logs request lifecycle."""

    def __init__(self, app: Callable[..., Any], monitor: Any):
        self.app = app
        self.monitor = monitor

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any], send: Callable[..., Any]) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        correlation_id = headers.get("x-request-id") or headers.get("x-correlation-id") or str(uuid.uuid4())
        token = set_correlation_id(correlation_id)

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        started = time.perf_counter()
        status_code = 500

        async def wrapped_send(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
            self.monitor.log(
                message=f"{method} {path}",
                level="INFO" if status_code < 500 else "ERROR",
                operation="http_request",
                status=str(status_code),
                metadata={"method": method, "path": path, "duration_ms": int((time.perf_counter() - started) * 1000)},
                correlation_id=correlation_id,
            )
        except Exception as exc:
            self.monitor.capture_exception(
                exc,
                operation="http_request",
                metadata={"method": method, "path": path},
                correlation_id=correlation_id,
            )
            raise
        finally:
            reset_correlation_id(token)


def attach_flask_middleware(app: Any, monitor: Any) -> None:
    """Attach request logging middleware to Flask app.

    Flask is optional. Importing this function does not require Flask,
    but calling it does.
    """

    try:
        from flask import g, request
    except Exception as exc:  # pragma: no cover - only hit when Flask missing
        raise RuntimeError("Flask is not installed. Install flask to use Flask middleware.") from exc

    @app.before_request
    def _before_request() -> None:
        correlation_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        g._monitor_started = time.perf_counter()
        g._monitor_token = set_correlation_id(correlation_id)
        g._monitor_correlation_id = correlation_id

    @app.after_request
    def _after_request(response: Any) -> Any:
        started = getattr(g, "_monitor_started", time.perf_counter())
        correlation_id = getattr(g, "_monitor_correlation_id", None)
        monitor.log(
            message=f"{request.method} {request.path}",
            level="INFO" if response.status_code < 500 else "ERROR",
            operation="http_request",
            status=str(response.status_code),
            metadata={
                "method": request.method,
                "path": request.path,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
            correlation_id=correlation_id,
        )
        token = getattr(g, "_monitor_token", None)
        if token is not None:
            reset_correlation_id(token)
        return response
