from __future__ import annotations

import atexit
import threading
import time
import traceback
import uuid
from dataclasses import dataclass
from typing import Any, Optional

import requests

from monitor_sdk.context import get_correlation_id


_LEVEL_PRIORITY: dict[str, int] = {
    "DEBUG": 0,
    "INFO": 1,
    "WARN": 2,
    "WARNING": 2,
    "ERROR": 3,
    "CRITICAL": 4,
}


@dataclass
class _MonitorConfig:
    api_key: str
    base_url: str
    service_name: str | None
    source: str
    batch_size: int
    flush_interval: float
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    min_level: str


class Monitor:
    """Client SDK for Project Monitor log ingestion.

    Features:
    - non-blocking batching on background thread
    - retry with exponential backoff
    - request context propagation through correlation IDs
    - exception capture helpers
    - min_level filter: events below the threshold are silently dropped
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        service_name: str | None = None,
        source: str = "sdk",
        batch_size: int = 50,
        flush_interval: float = 2.0,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        retry_backoff_seconds: float = 0.5,
        min_level: str = "WARN",
        session: Optional[requests.Session] = None,
        start_background: bool = True,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not base_url:
            raise ValueError("base_url is required")
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        if flush_interval <= 0:
            raise ValueError("flush_interval must be > 0")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        if min_level.upper() not in _LEVEL_PRIORITY:
            raise ValueError(f"min_level must be one of {list(_LEVEL_PRIORITY)}")

        self._cfg = _MonitorConfig(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            service_name=service_name,
            source=source,
            batch_size=batch_size,
            flush_interval=flush_interval,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            min_level=min_level.upper(),
        )

        self._session = session or requests.Session()
        self._lock = threading.Lock()
        self._buffer: list[dict[str, Any]] = []
        self._dead_letter: list[dict[str, Any]] = []
        self._stop_event = threading.Event()
        self._flush_thread: threading.Thread | None = None

        if start_background:
            self.start()
        atexit.register(self.close)

    def start(self) -> None:
        if self._flush_thread and self._flush_thread.is_alive():
            return
        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_loop, name="monitor-sdk-flush", daemon=True
        )
        self._flush_thread.start()

    def close(self) -> None:
        self._stop_event.set()
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2.0)
        self.flush()

    def dead_letter(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._dead_letter)

    def log(
        self,
        message: str,
        *,
        level: str = "INFO",
        operation: str | None = None,
        status: str | None = None,
        error_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
        service_name: str | None = None,
        source: str | None = None,
    ) -> None:
        if not message:
            return
        if _LEVEL_PRIORITY.get(level.upper(), 1) < _LEVEL_PRIORITY[self._cfg.min_level]:
            return

        resolved_correlation = correlation_id or get_correlation_id()
        payload = {
            "service_name": service_name or self._cfg.service_name,
            "operation": operation,
            "level": level.upper(),
            "status": status,
            "message": message,
            "error_type": error_type,
            "correlation_id": resolved_correlation,
            "metadata": metadata,
            "source": source or self._cfg.source,
        }

        with self._lock:
            self._buffer.append(payload)
            should_flush = len(self._buffer) >= self._cfg.batch_size

        if should_flush:
            self.flush()

    def info(self, message: str, **kwargs: Any) -> None:
        self.log(message, level="INFO", **kwargs)

    def warn(self, message: str, **kwargs: Any) -> None:
        self.log(message, level="WARN", **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self.log(message, level="ERROR", **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self.log(message, level="DEBUG", **kwargs)

    def capture_exception(
        self,
        exc: BaseException,
        *,
        operation: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        exc_type = type(exc).__name__
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("traceback", detail)

        self.log(
            message=str(exc) or exc_type,
            level="ERROR",
            operation=operation,
            status="error",
            error_type=exc_type,
            metadata=merged_metadata,
            correlation_id=correlation_id,
        )

    def trace(self, operation: str, *, metadata: dict[str, Any] | None = None):
        return _TraceContext(self, operation=operation, metadata=metadata)

    def install_excepthook(self) -> None:
        import sys

        previous_hook = sys.excepthook

        def _hook(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
            self.capture_exception(exc, operation="unhandled_exception")
            self.flush()
            previous_hook(exc_type, exc, tb)

        sys.excepthook = _hook

    def flush(self) -> None:
        while True:
            batch = self._drain_batch(self._cfg.batch_size)
            if not batch:
                return
            success = self._send_batch(batch)
            if not success:
                with self._lock:
                    self._dead_letter.extend(batch)

    def _flush_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._cfg.flush_interval)
            if self._stop_event.is_set():
                break
            self.flush()

    def _drain_batch(self, n: int) -> list[dict[str, Any]]:
        with self._lock:
            if not self._buffer:
                return []
            batch = self._buffer[:n]
            self._buffer = self._buffer[n:]
            return batch

    def _send_batch(self, batch: list[dict[str, Any]]) -> bool:
        url = f"{self._cfg.base_url}/api/v1/logs"
        attempt = 0
        while attempt <= self._cfg.max_retries:
            attempt += 1
            try:
                resp = self._session.post(
                    url,
                    json={"logs": batch},
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": self._cfg.api_key,
                        "Idempotency-Key": str(uuid.uuid4()),
                    },
                    timeout=self._cfg.timeout_seconds,
                )
                if 200 <= resp.status_code < 300:
                    return True
            except requests.RequestException:
                pass

            if attempt <= self._cfg.max_retries:
                time.sleep(self._cfg.retry_backoff_seconds * (2 ** (attempt - 1)))

        return False


class _TraceContext:
    def __init__(self, monitor: Monitor, *, operation: str, metadata: dict[str, Any] | None):
        self._monitor = monitor
        self._operation = operation
        self._metadata = metadata or {}
        self._start = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        self._monitor.debug(
            message=f"{self._operation} started",
            operation=self._operation,
            metadata=self._metadata,
            status="start",
        )
        return self

    def __exit__(self, exc_type, exc, _tb):
        duration_ms = int((time.perf_counter() - self._start) * 1000)
        metadata = dict(self._metadata)
        metadata["duration_ms"] = duration_ms

        if exc is None:
            self._monitor.info(
                message=f"{self._operation} completed",
                operation=self._operation,
                status="ok",
                metadata=metadata,
            )
            return False

        self._monitor.capture_exception(
            exc,
            operation=self._operation,
            metadata=metadata,
        )
        return False
