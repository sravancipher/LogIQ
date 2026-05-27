# project-monitor-sdk

Python SDK for [Project Monitor](https://github.com/your-org/project-monitor) — send logs, capture exceptions, and keep your services visible in the dashboard.

## Install

```bash
pip install project-monitor-sdk
```

## Quick start

```python
from monitor_sdk import Monitor

monitor = Monitor(
    api_key="pm_your_api_key",
    base_url="http://localhost:8000",
    service_name="my-service",
    min_level="WARN",
)

# Register the service in the dashboard immediately
monitor.heartbeat()
monitor.start_heartbeat_loop(interval=30)

# Logging
monitor.info("server started", operation="startup")
monitor.warn("high memory usage", operation="health_check", metadata={"pct": 87})
monitor.error("payment failed", operation="checkout", error_type="TimeoutError")

# Capture exceptions
try:
    call_external_api()
except Exception as exc:
    monitor.capture_exception(exc, operation="external_api")

# Trace a block
with monitor.trace("checkout_flow"):
    process_order()

# FastAPI / Starlette middleware — auto-logs every request
from fastapi import FastAPI
from monitor_sdk import MonitorASGIMiddleware

app = FastAPI()
app.add_middleware(MonitorASGIMiddleware, monitor=monitor)
```

## Configuration

| Parameter | Description |
|-----------|-------------|
| `api_key` | Project Monitor API key (`pm_...`) |
| `base_url` | Backend URL, e.g. `http://localhost:8000` |
| `service_name` | Name shown in the Servers dashboard |
| `min_level` | Drop events below this level — `DEBUG` / `INFO` / `WARN` / `ERROR` / `CRITICAL` |
| `batch_size` | Flush when the buffer reaches this many events (default `50`) |
| `flush_interval` | Seconds between automatic flushes (default `2.0`) |
| `max_retries` | HTTP retries per batch with exponential back-off (default `3`) |

## Links

- [Full documentation & setup guide](https://github.com/your-org/project-monitor#readme)
- [Changelog](https://github.com/your-org/project-monitor/releases)
- [Issues](https://github.com/your-org/project-monitor/issues)

## License

MIT

