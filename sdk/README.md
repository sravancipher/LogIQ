# logiq-sdk

Official Python SDK for [LogIQ](https://logiq.thetechvoyager.in) — batches structured log/error events on a background thread and ships them to your LogIQ project over HTTP, so you can point your app at the platform with one import and a few lines of setup.

```bash
pip install logiq-sdk
```

The distribution is named `logiq-sdk`; the importable module is `logiq`:

```python
from logiq import Monitor
```

- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Configuring `Monitor`](#configuring-monitor)
- [Sending logs](#sending-logs)
- [Capturing exceptions](#capturing-exceptions)
- [Timing operations with `trace()`](#timing-operations-with-trace)
- [Catching unhandled exceptions process-wide](#catching-unhandled-exceptions-process-wide)
- [Correlation IDs](#correlation-ids)
- [ASGI middleware (FastAPI / Starlette)](#asgi-middleware-fastapi--starlette)
- [Flask middleware](#flask-middleware)
- [Heartbeats (Servers dashboard)](#heartbeats-servers-dashboard)
- [Manual flush, shutdown, and delivery guarantees](#manual-flush-shutdown-and-delivery-guarantees)
- [Full FastAPI example](#full-fastapi-example)
- [API reference summary](#api-reference-summary)

## Quick start

```python
from logiq import Monitor

monitor = Monitor(
    api_key="<YOUR_LOGIQ_API_KEY>",
    base_url="https://your-logiq-backend.example.com",
    service_name="checkout-service",
)

monitor.info("Order placed", operation="create_order", metadata={"order_id": 123})

try:
    charge_card(order)
except Exception as exc:
    monitor.capture_exception(exc, operation="create_order")
```

Get `api_key`/`base_url` from your LogIQ project's onboarding page (project creation mints the key once — store it securely, it isn't retrievable again).

## How it works

- Every `log()`/`info()`/`warn()`/`error()`/`debug()`/`capture_exception()` call appends an event to an in-memory buffer — it never blocks on network I/O.
- A background thread flushes the buffer to `POST {base_url}/api/v1/logs` either every `flush_interval` seconds, or immediately once the buffer reaches `batch_size` events.
- Failed sends are retried with exponential backoff; if all retries are exhausted the batch is moved to an in-memory dead-letter list rather than raised as an exception.
- `atexit` is registered automatically — on normal process exit, `close()` runs and performs one final flush.

## Configuring `Monitor`

```python
monitor = Monitor(
    api_key="...",              # required — your project's API key (X-API-Key header)
    base_url="...",             # required — your LogIQ backend origin, no trailing slash needed
    service_name="checkout",    # default service_name attached to every event, can be overridden per-call
    source="sdk",                # default `source` field attached to every event
    batch_size=50,               # flush once this many events are buffered
    flush_interval=2.0,          # seconds between scheduled background flushes
    timeout_seconds=5.0,         # per-request HTTP timeout
    max_retries=3,                # retries per batch before it's moved to the dead-letter list
    retry_backoff_seconds=0.5,   # base backoff; actual wait = retry_backoff_seconds * 2**(attempt-1)
    min_level="WARN",            # events below this level are silently dropped, see Log levels below
    session=None,                 # pass a pre-configured requests.Session() to reuse connections/pooling
    start_background=True,       # False = don't start the flush thread (you'll drive flush() yourself)
)
```

**Log levels & `min_level`.** Levels, lowest to highest priority: `DEBUG` < `INFO` < `WARN`/`WARNING` < `ERROR` < `CRITICAL`. The default `min_level="WARN"` means **`.info()` and `.debug()` calls are silently dropped** unless you lower it:

```python
monitor = Monitor(api_key=..., base_url=..., min_level="INFO")  # or "DEBUG" to see everything
```

## Sending logs

```python
monitor.info("Cache warmed", operation="startup")
monitor.warn("Upstream latency high", operation="charge", metadata={"latency_ms": 1200})
monitor.error("Payment declined", operation="charge", error_type="CardDeclined")
monitor.debug("Computed discount", operation="pricing", metadata={"discount_pct": 10})

# Or call log() directly for full control:
monitor.log(
    "Custom event",
    level="ERROR",
    operation="reconcile",
    status="failed",
    error_type="ReconciliationMismatch",
    metadata={"expected": 100, "actual": 97},
    correlation_id="req-abc-123",   # falls back to the active correlation ID if omitted, see below
    service_name="billing-service",  # overrides the Monitor-level default for this one event
    source="worker",                  # overrides the Monitor-level default for this one event
)
```

`message` is the only required field for every call — an empty/falsy message is silently dropped without raising.

## Capturing exceptions

```python
try:
    process_payment(order)
except Exception as exc:
    monitor.capture_exception(exc, operation="process_payment", metadata={"order_id": order.id})
```

This always logs at `ERROR`, sets `error_type` to the exception's class name, `status="error"`, and stores the full formatted traceback under `metadata["traceback"]`.

## Timing operations with `trace()`

A context manager that logs a `start` (`DEBUG`) event on entry and either a `completed` (`INFO`, with `duration_ms`) event on clean exit, or routes to `capture_exception` (also with `duration_ms` in `metadata`) if the block raises:

```python
with monitor.trace("charge_card", metadata={"order_id": order.id}):
    charge_card(order)   # any exception here is captured automatically, with duration_ms attached
```

## Catching unhandled exceptions process-wide

```python
monitor.install_excepthook()
```

Wraps `sys.excepthook`: any unhandled exception is captured (`operation="unhandled_exception"`), flushed immediately, then passed on to whatever exception hook was previously installed (so default traceback printing still happens).

## Correlation IDs

Correlation IDs use `contextvars`, so they propagate correctly across `async`/`await` and threads started via the standard concurrency primitives, scoped to the current request/task:

```python
from logiq import set_correlation_id, get_correlation_id, reset_correlation_id

token = set_correlation_id("req-abc-123")
try:
    monitor.info("Handling request")   # picks up correlation_id="req-abc-123" automatically
    downstream_call()                    # anything reading get_correlation_id() sees the same ID
finally:
    reset_correlation_id(token)
```

`log()`/`info()`/`warn()`/`error()`/`debug()`/`capture_exception()` all use `get_correlation_id()` as the fallback whenever you don't pass `correlation_id=` explicitly. The ASGI and Flask middleware (below) set this for you automatically for every request.

### Propagating a correlation ID to another service

The behavior above only covers one process: `contextvars` don't cross a network call. If your handler calls another service over HTTP and you want that service's logs linked to the same incident, attach the ID to the outbound request yourself with `get_correlation_headers()` (or `monitor.correlation_headers()`) — it returns `{}` when there's no active correlation ID, so it's always safe to merge into your headers:

```python
from logiq import get_correlation_headers
import requests

requests.post(
    "http://payment-service/charge",
    json=payload,
    headers={"Content-Type": "application/json", **get_correlation_headers()},
)
```

On the receiving side, `MonitorASGIMiddleware`/`attach_flask_middleware` reads the same `X-Correlation-Id` (or `X-Request-Id`) header, so that service continues the same correlation ID instead of minting a new one — this is what lets LogIQ's AI Insights link errors from both services into one incident (see "contributing error groups" in the dashboard).

## ASGI middleware (FastAPI / Starlette)

```python
from fastapi import FastAPI
from logiq import MonitorASGIMiddleware

app = FastAPI()
app.add_middleware(MonitorASGIMiddleware, monitor=monitor)
```

For every HTTP request, this:
- Reads a correlation ID from the `X-Request-ID` or `X-Correlation-ID` request header, generating a new UUID if neither is present.
- Sets it as the active correlation ID for the duration of the request (propagates into any `monitor.*` calls made by your handler).
- After the response, logs one event: `INFO` for status `< 500`, `ERROR` otherwise, with `metadata={"method", "path", "duration_ms"}`.
- If the handler raises, calls `capture_exception` (same metadata) and re-raises — the exception isn't swallowed.
- Resets the correlation ID afterward so it doesn't leak into unrelated requests.
- Only instruments `http` scope requests — websocket/lifespan scopes pass straight through untouched.

## Flask middleware

```python
from flask import Flask
from logiq import attach_flask_middleware

app = Flask(__name__)
attach_flask_middleware(app, monitor)
```

Same behavior as the ASGI middleware (correlation ID from `X-Request-ID`/`X-Correlation-ID`, one request-lifecycle log event, `INFO`/`ERROR` by status code), implemented via `before_request`/`after_request` hooks. Flask is an optional dependency — installing `logiq-sdk` alone does **not** require Flask; it's only imported when `attach_flask_middleware()` is actually called (raises a clear `RuntimeError` if Flask isn't installed).

## Heartbeats (Servers dashboard)

Heartbeats register your service with LogIQ's Servers dashboard even before any real log traffic occurs, and bypass `min_level` entirely:

```python
monitor.heartbeat()                 # one-off, e.g. right after startup
monitor.start_heartbeat_loop(30)    # background thread, sends every 30s until monitor.close()
```

`start_heartbeat_loop()` runs on its own daemon thread and stops automatically when `monitor.close()` is called (including via the automatic `atexit` handler).

## Manual flush, shutdown, and delivery guarantees

```python
monitor.flush()   # force-send everything currently buffered, right now
monitor.close()   # stop background threads, then flush one final time
```

- `close()` is also called automatically on normal interpreter exit via `atexit`, so buffered-but-unsent events generally get a last delivery attempt even if you never call it yourself.
- Events that still fail after `max_retries` attempts land in an in-memory dead-letter list — nothing is raised into your application code. Inspect it with:

  ```python
  failed_events = monitor.dead_letter()
  ```

  This list is **not persisted** — read it before the process exits if you need to react to permanent delivery failures (e.g. write it to disk or re-queue it yourself).
- If you need to control the flush thread's lifecycle yourself (e.g. in a short-lived script or a test), pass `start_background=False` and call `monitor.flush()` explicitly when you want events sent.

## Full FastAPI example

```python
from fastapi import FastAPI
from logiq import Monitor, MonitorASGIMiddleware

monitor = Monitor(
    api_key="<YOUR_LOGIQ_API_KEY>",
    base_url="https://your-logiq-backend.example.com",
    service_name="checkout-service",
    min_level="INFO",
)
monitor.start_heartbeat_loop(30)
monitor.install_excepthook()

app = FastAPI()
app.add_middleware(MonitorASGIMiddleware, monitor=monitor)


@app.post("/orders")
def create_order(order: OrderIn):
    with monitor.trace("create_order", metadata={"sku": order.sku}):
        return place_order(order)
```

## API reference summary

| Import | Purpose |
|---|---|
| `Monitor(...)` | The client — construct once per process/service and reuse it |
| `monitor.log(message, *, level=, operation=, status=, error_type=, metadata=, correlation_id=, service_name=, source=)` | Core event method — all convenience methods below call this |
| `monitor.info/warn/error/debug(message, **kwargs)` | Shortcuts for `log(message, level=..., **kwargs)` |
| `monitor.capture_exception(exc, *, operation=, metadata=, correlation_id=)` | Log an exception with traceback captured in `metadata["traceback"]` |
| `monitor.trace(operation, *, metadata=)` | Context manager: logs start/completion (or captures the exception) with `duration_ms` |
| `monitor.install_excepthook()` | Route uncaught exceptions process-wide through `capture_exception` |
| `monitor.heartbeat(service_name=None)` | One-off "service is up" event, bypasses `min_level` |
| `monitor.start_heartbeat_loop(interval=30.0)` | Background periodic heartbeat, stops on `close()` |
| `monitor.flush()` | Force-send everything buffered right now |
| `monitor.close()` | Stop background threads and flush once more (also runs automatically via `atexit`) |
| `monitor.dead_letter()` | List of batches that failed delivery after all retries |
| `MonitorASGIMiddleware` | FastAPI/Starlette middleware — correlation IDs + one log event per request |
| `attach_flask_middleware(app, monitor)` | Same, for Flask |
| `set_correlation_id(id)` / `get_correlation_id()` / `reset_correlation_id(token)` | Manual correlation ID propagation via `contextvars` |
| `get_correlation_headers(header_name="X-Correlation-Id")` / `monitor.correlation_headers(header_name=...)` | Header dict for an outbound HTTP call, so a downstream service continues the same correlation ID (`{}` if none is active) |

## License

MIT
