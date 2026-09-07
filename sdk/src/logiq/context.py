from __future__ import annotations

import contextvars

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "logiq_correlation_id", default=None
)


def set_correlation_id(correlation_id: str | None) -> contextvars.Token:
    return _correlation_id_var.set(correlation_id)


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id_var.reset(token)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()


def get_correlation_headers(header_name: str = "X-Correlation-Id") -> dict[str, str]:
    """Header dict to attach to an outbound HTTP call so the receiving service's
    middleware (MonitorASGIMiddleware / attach_flask_middleware) continues the same
    correlation ID, instead of minting a new one for the downstream request.

    Returns {} when no correlation ID is active, so it's always safe to splat into
    an existing headers dict, e.g.:
        requests.post(url, headers={**my_headers, **get_correlation_headers()})
    """
    correlation_id = get_correlation_id()
    if not correlation_id:
        return {}
    return {header_name: correlation_id}
