# Project Monitor Backend (Phase 1 MVP)

This backend provides the Phase 1 APIs:

- `POST /api/v1/projects`
- `POST /api/v1/logs`
- `GET /api/v1/logs`
- `GET /api/v1/insights`
- `POST /api/v1/alerts/test`
- `GET /health`
- `GET /dashboard`

## 1. Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy environment file:

```bash
copy .env.example .env
```

4. Ensure PostgreSQL is running and database exists:

```sql
CREATE DATABASE project_monitor;
```

5. Apply migrations:

```bash
alembic upgrade head
```

## 2. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 3. Worker (Queue Pipeline Scaffold)

Run the background queue worker in a second terminal:

```bash
python -m app.workers.queue_worker
```

This processes pending records from `work_queue_items` and is the starter for async processing.

## 4. API Quick Test

### Create project and API key

```bash
curl -X POST http://localhost:8000/api/v1/projects ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"demo-project\",\"description\":\"phase1\"}"
```

Use returned `api_key` in the next calls.

### Ingest logs

```bash
curl -X POST http://localhost:8000/api/v1/logs ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: <YOUR_API_KEY>" ^
  -H "Idempotency-Key: ingest-001" ^
  -d "{\"logs\":[{\"service_name\":\"payment\",\"operation\":\"charge\",\"level\":\"ERROR\",\"status\":\"error\",\"message\":\"Stripe timeout\",\"error_type\":\"TimeoutError\",\"correlation_id\":\"req_123\",\"metadata\":{\"user_id\":\"u1\"},\"source\":\"sdk\"}]}"
```

Repeat the exact same request with the same `Idempotency-Key`; it returns the same accepted count and avoids duplicate insertion.

### Query logs

```bash
curl -X GET "http://localhost:8000/api/v1/logs?limit=50" ^
  -H "X-API-Key: <YOUR_API_KEY>"
```

Cursor pagination example:

1. First page:

```bash
curl -X GET "http://localhost:8000/api/v1/logs?limit=2" ^
  -H "X-API-Key: <YOUR_API_KEY>"
```

2. Use returned `next_cursor`:

```bash
curl -X GET "http://localhost:8000/api/v1/logs?limit=2&cursor=<NEXT_CURSOR>" ^
  -H "X-API-Key: <YOUR_API_KEY>"
```

### Get insights

```bash
curl -X GET "http://localhost:8000/api/v1/insights?lookback_minutes=60" ^
  -H "X-API-Key: <YOUR_API_KEY>"
```

When LLM analysis is enabled, the response also includes:

- `incident_summary`
- `action_plan`
- `timeline`
- `analysis_mode` (`llm` or `fallback`)
- `model_name`
- `fallback_reason`

### Submit insight feedback

```bash
curl -X POST "http://localhost:8000/api/v1/insights/feedback" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: <YOUR_API_KEY>" ^
  -d "{\"rating\":\"down\",\"lookback_minutes\":60,\"root_cause\":\"Wrong RCA\",\"suggestion\":\"Wrong action\",\"incident_summary\":\"Wrong summary\",\"analysis_mode\":\"llm\",\"model_name\":\"qwen3:4b-q4_K_M\",\"correction\":\"Issue was DNS resolution failure\"}"
```

### Test alert channel integration stubs

```bash
curl -X POST "http://localhost:8000/api/v1/alerts/test" ^
  -H "Content-Type: application/json" ^
  -H "X-API-Key: <YOUR_API_KEY>" ^
  -d "{\"title\":\"High Error Rate\",\"message\":\"Spike in timeout errors\",\"severity\":\"HIGH\"}"
```

## 5. Automated Tests

```bash
pytest -q
```

## 6. LLM Insights (Ollama)

To enable Ollama-backed root cause analysis, add these settings to `.env`:

```bash
LLM_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b-q4_K_M
OLLAMA_TIMEOUT_SECONDS=20
OLLAMA_MAX_LOGS=25
OLLAMA_MAX_CHARS_PER_LOG=400
OLLAMA_TEMPERATURE=0.1
```

Behavior:

- Uses recent logs plus summary metrics as prompt input
- Calls Ollama `/api/generate` with `stream=false`
- Expects strict JSON output for RCA, incident summary, and action plan
- Falls back to the rule-based insight engine if Ollama is disabled, unreachable, or returns invalid JSON
- Caps prompt size by limiting log count and message length

## 7. Python SDK (`monitor_sdk`)

The repository now includes a Python SDK package at `monitor_sdk` for app-side logging.

### Basic Usage

```python
from monitor_sdk import Monitor

monitor = Monitor(
  api_key="pm_xxx",
  base_url="http://localhost:8000",
  service_name="payment-service",
)

monitor.info("order accepted", operation="create_order")
monitor.warn("retrying upstream call", operation="charge", metadata={"attempt": 2})
monitor.error("stripe timeout", operation="charge", error_type="TimeoutError")

try:
  raise RuntimeError("checkout failed")
except Exception as exc:
  monitor.capture_exception(exc, operation="checkout")

monitor.flush()
monitor.close()
```

### Features Included

- Non-blocking batching with configurable `batch_size` and `flush_interval`
- Retry with exponential backoff (`max_retries`, `retry_backoff_seconds`)
- Context propagation using correlation IDs
- Exception capture with traceback metadata
- ASGI middleware and Flask middleware hooks

### Correlation Context

```python
from monitor_sdk import set_correlation_id, reset_correlation_id

token = set_correlation_id("req-123")
try:
  monitor.info("processing request")
finally:
  reset_correlation_id(token)
```

### ASGI Middleware Example

```python
from fastapi import FastAPI
from monitor_sdk import Monitor, MonitorASGIMiddleware

app = FastAPI()
monitor = Monitor(api_key="pm_xxx", base_url="http://localhost:8000", service_name="api")
app.add_middleware(MonitorASGIMiddleware, monitor=monitor)
```

### Flask Middleware Example

```python
from flask import Flask
from monitor_sdk import Monitor, attach_flask_middleware

app = Flask(__name__)
monitor = Monitor(api_key="pm_xxx", base_url="http://localhost:8000", service_name="api")
attach_flask_middleware(app, monitor)
```
