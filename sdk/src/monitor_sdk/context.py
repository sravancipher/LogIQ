from __future__ import annotations

import contextvars

_correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "monitor_sdk_correlation_id", default=None
)


def set_correlation_id(correlation_id: str | None) -> contextvars.Token:
    return _correlation_id_var.set(correlation_id)


def reset_correlation_id(token: contextvars.Token) -> None:
    _correlation_id_var.reset(token)


def get_correlation_id() -> str | None:
    return _correlation_id_var.get()
