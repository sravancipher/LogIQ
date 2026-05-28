<div align="center">

# Project Monit

**AI-powered observability platform for your backend services.**

Collect logs · Surface LLM root-cause analysis · Fire alerts · Track every running service — all from a single self-hosted dashboard.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SDK on PyPI](https://img.shields.io/pypi/v/project-monitor-sdk?style=flat-square&label=project-monitor-sdk&color=0073B7)](https://pypi.org/project/project-monitor-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

</div>

---

## Overview

Project Monitor is a self-hosted platform made up of three components that work together:

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Backend API** | FastAPI + PostgreSQL | Ingests logs, runs AI analysis, fires alerts |
| **React Dashboard** | Vite + React 18 | Live metrics, log explorer, insights, servers view |
| **Python SDK** | `project-monitor-sdk` (PyPI) | Instruments your services with one import |

---

## Features

- **Log ingestion** — batched, idempotent HTTP ingest with `X-API-Key` auth
- **Log Explorer** — paginated search by level, service, and time range
- **AI Insights** — LLM root-cause analysis (OpenAI-compatible or Ollama) with rule-based fallback
- **Servers view** — per-service health status, error ratio, and error drill-down
- **Alerts** — Slack, Microsoft Teams, and Email delivery
- **Cloud integrations** — normalised webhook ingestion from AWS, Azure, and GCP
- **Python SDK** — non-blocking batching, auto-retry, correlation IDs, ASGI middleware, heartbeat

---

## Architecture

```
Your Services (Python)
  └── project-monitor-sdk
        ├── heartbeat() / start_heartbeat_loop()
        └── log() / capture_exception() / trace()
              │
              │  POST /api/v1/logs  (batched · idempotent · retried)
              ▼
┌──────────────────────────────────────────────────────┐
│  FastAPI Backend  ·  port 8000                       │
│                                                      │
│  PostgreSQL                                          │
│  ├── projects & api_keys                             │
│  ├── logs  (indexed by project / service / level)    │
│  ├── work_queue  (background jobs)                   │
│  ├── cloud_integrations                              │
│  └── insight_feedback                                │
│                                                      │
│  Background queue worker                             │
│  AI Insights engine  ·  LLM / Ollama / rule-based   │
│  Alert service  ·  Slack / Teams / Email             │
│  Static file server  →  React build at /app          │
└──────────────────────────────────────────────────────┘
              ▲
              │  /api  proxy
  React Dashboard  ·  port 8001 (dev)

Cloud Providers
  └── POST /api/v1/integrations/webhook/{id}
        └── auto-normalised  →  stored as logs
```

---

## Quick Start

### 1 — Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 14+

### 2 — Backend

```bash
cd backend

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

pip install -r requirements.txt

# Create the database first (PostgreSQL)
# CREATE DATABASE project_monitor;

alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

> API docs available at `http://localhost:8000/docs`

### 3 — Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:8001
```

**Production build** (served by FastAPI at `/app`):
```bash
npm run build        # outputs to frontend/dist/
```

### 4 — SDK

```bash
pip install project-monitor-sdk
```

```python
from monitor_sdk import Monitor

monitor = Monitor(
    api_key="pm_your_api_key",
    base_url="http://localhost:8000",
    service_name="my-service",
    min_level="WARN",
)

monitor.heartbeat()                    # register immediately in the Servers dashboard
monitor.start_heartbeat_loop(30)       # keep pinging every 30 s while running

monitor.info("server started", operation="startup")
monitor.error("payment failed", operation="checkout", error_type="TimeoutError")
```

---

## Create Your First Project

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "my-service", "description": "Production backend"}'
```

```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "api_key": "pm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

> The API key is shown **only once**. Save it before closing the response.

---

## Environment Variables

### Backend — `backend/.env`

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `LLM_ENABLED` | Enable LLM-powered insights (`true` / `false`) |
| `LLM_PROVIDER` | LLM provider — use `openai` for any OpenAI-compatible endpoint |
| `LLM_BASE_URL` | OpenAI-compatible API base URL |
| `LLM_MODEL` | Model name |
| `LLM_API_KEY` | API key for the LLM endpoint |
| `LLM_TIMEOUT_SECONDS` | Request timeout in seconds |
| `LLM_MAX_LOGS` | Max recent logs included in LLM prompt |
| `OLLAMA_BASE_URL` | Ollama endpoint (fallback when `LLM_BASE_URL` is not set) |
| `OLLAMA_MODEL` | Ollama model name |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook for alerts |
| `TEAMS_WEBHOOK_URL` | Microsoft Teams webhook |
| `ALERT_EMAIL_FROM` | SMTP sender address |
| `ALERT_EMAIL_TO` | Default alert recipient |
| `SMTP_HOST` | SMTP host |
| `SMTP_PORT` | SMTP port |
| `SMTP_USERNAME` | SMTP auth username |
| `SMTP_PASSWORD` | SMTP auth password |
| `QUEUE_POLL_INTERVAL_SECONDS` | Background worker poll interval in seconds |

### Frontend — `frontend/.env.development`

| Variable | Description |
|----------|-------------|
| `VITE_API_BASE` | Leave **empty** to use the Vite proxy. Set only when bypassing the proxy. |

---

## API Reference

All routes are prefixed `/api/v1`. Authenticated routes require the header `X-API-Key: pm_...`.

### Projects

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/projects` | — | Create a project; returns `project_id` and `api_key` |

### Logs

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/logs` | ✓ | Ingest a batch of events. Supports `Idempotency-Key` header. |
| `GET` | `/logs` | ✓ | Query logs. Filters: `level`, `service_name`, `start_time`, `end_time`. Cursor pagination. |

<details>
<summary>Ingest payload example</summary>

```json
{
  "logs": [
    {
      "service_name": "payment",
      "level": "ERROR",
      "message": "Stripe timeout",
      "operation": "checkout",
      "status": "error",
      "error_type": "TimeoutError",
      "correlation_id": "req-123",
      "metadata": { "user_id": "u1", "amount": 99.99 },
      "source": "sdk"
    }
  ]
}
```

</details>

### Insights

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/insights` | ✓ | LLM root-cause analysis. Params: `lookback_minutes` (5–1440), `deep_analysis` (bool) |
| `POST` | `/insights/feedback` | ✓ | Submit a rating and optional correction for an insight |

### Alerts

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/alerts/test` | ✓ | Send a test alert — `channel`: `slack`, `teams`, or `email` |
| `POST` | `/alerts/insights/notify` | ✓ | Run insights and email the result |

### Cloud Integrations

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/integrations` | ✓ | Register a cloud provider connection |
| `GET` | `/integrations` | ✓ | List all connections for the project |
| `DELETE` | `/integrations/{id}` | ✓ | Remove a connection |
| `POST` | `/integrations/webhook/{id}?token=…` | — | Receive cloud webhook; auto-normalised and stored as logs |

### Services

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/services` | ✓ | Per-service summary — total logs, errors, `status`, `last_seen`. Param: `lookback_minutes` |

### Health

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/health` | — | Returns `{"status": "ok"}` |

---

## Dashboard Pages

| Page | Description |
|------|-------------|
| **Overview** | Live stat cards, recent errors table, error groups, dependent error groups across services |
| **Log Explorer** | Full log search with level / service / time range filters and cursor pagination |
| **AI Insights** | LLM incident summary, root cause, fix suggestion, error timeline, thumbs feedback |
| **Servers** | All reporting services with health status; click to drill into service-level errors |
| **Alerts** | Configure and test Slack / Teams / Email delivery |
| **Integrations** | Connect AWS, Azure, or GCP; copy the webhook URL into the cloud console |
| **New Project** | Create a project and copy the one-time API key |

---

## SDK — Full Reference

### Install

```bash
pip install project-monitor-sdk
```

### Initialise

```python
from monitor_sdk import Monitor

monitor = Monitor(
    api_key="pm_...",
    base_url="http://localhost:8000",
    service_name="my-service",
    min_level="WARN",           # DEBUG / INFO / WARN / ERROR / CRITICAL
)
```

### Logging methods

```python
monitor.debug("cache miss",        operation="cache_lookup")
monitor.info("order created",      operation="create_order",  metadata={"id": 42})
monitor.warn("high memory",        operation="health_check",  metadata={"pct": 87})
monitor.error("payment declined",  operation="checkout",      error_type="PaymentError")

# Any level explicitly
monitor.log("message", level="CRITICAL", operation="scheduler")
```

### Capture exceptions

```python
try:
    call_external_api()
except Exception as exc:
    monitor.capture_exception(exc, operation="external_api", metadata={"url": url})
# Logs as ERROR, attaches full traceback to metadata["traceback"]
```

### Trace a block

```python
with monitor.trace("checkout_flow", metadata={"cart_id": cart.id}):
    process_order()
# INFO on entry · ERROR with duration_ms if the block raises
```

### ASGI middleware (FastAPI / Starlette)

```python
from fastapi import FastAPI
from monitor_sdk import MonitorASGIMiddleware

app = FastAPI()
app.add_middleware(MonitorASGIMiddleware, monitor=monitor)
# Auto-logs every request · propagates correlation IDs from X-Request-Id header
```

### Correlation ID context

```python
from monitor_sdk.context import set_correlation_id, reset_correlation_id

token = set_correlation_id("req-abc-123")
try:
    monitor.info("processing")   # correlation_id auto-attached
finally:
    reset_correlation_id(token)
```

### Heartbeat

```python
monitor.heartbeat()                  # one-shot — service appears in Servers dashboard immediately
monitor.start_heartbeat_loop(30)     # daemon thread pings every 30 s; stops on monitor.close()
```

Heartbeat events bypass `min_level` so the service is always visible.

### Constructor parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `api_key` | required | API key (`pm_...`) |
| `base_url` | required | Backend base URL |
| `service_name` | `None` | Name shown in the dashboard |
| `source` | `"sdk"` | Source tag on every event |
| `min_level` | `"WARN"` | Minimum level to send |
| `batch_size` | `50` | Events before an automatic flush |
| `flush_interval` | `2.0` | Seconds between background flushes |
| `timeout_seconds` | `5.0` | HTTP timeout per attempt |
| `max_retries` | `3` | Retries per batch (exponential back-off) |
| `retry_backoff_seconds` | `0.5` | Base back-off delay |
| `start_background` | `True` | Start flush thread on init |

---

## Cloud Integrations

Supported providers and event types:

| Provider | Supported Event Types |
|----------|-----------------------|
| **AWS** | CloudWatch Alarms, CloudWatch Logs, CloudTrail, GuardDuty, RDS, Lambda, Security Hub, EventBridge |
| **Azure** | Monitor Alerts, Activity Log, Application Insights, Service Health, Defender, AKS, Event Grid |
| **GCP** | Cloud Logging, Cloud Monitoring, Security Command Center |

**Setup:**
1. `POST /api/v1/integrations` → receive `webhook_url` + `webhook_token`
2. Paste `webhook_url` into your cloud console (SNS, Event Grid topic, Pub/Sub, etc.)
3. Events are auto-detected, normalised, and stored as logs

---

## AI Insights

The insights engine follows this flow on every `GET /api/v1/insights` call:

1. Queries recent logs and computes error metrics, top error types, and service-level groups
2. If `LLM_ENABLED=true` — sends the summary to an OpenAI-compatible endpoint or Ollama
3. Falls back to rule-based heuristics if the LLM is unreachable or returns invalid JSON

**Response includes:**

| Field | Description |
|-------|-------------|
| `incident_summary` | Plain-English summary of the incident |
| `root_cause` | Identified root cause |
| `suggestion` | Recommended fix |
| `error_groups` | Top error types grouped by service and operation |
| `dependent_error_groups` | Correlated errors across services (shared correlation IDs) |
| `timeline` | Chronological significant events |
| `fallback_reason` | Set when rule-based fallback was used |

---

## Database Migrations

```bash
cd backend

alembic upgrade head          # apply all pending migrations
alembic downgrade -1          # roll back one step
alembic revision --autogenerate -m "describe_change"   # generate after model changes
alembic current               # check state
```

| Migration | Changes |
|-----------|---------|
| `0001_initial_schema` | `projects`, `api_keys`, `logs` |
| `0002_add_last_used_at_to_api_keys` | `last_used_at` on `api_keys` |
| `0003_add_ingest_requests_and_work_queue` | Idempotency keys + job queue |
| `0004_add_cloud_integrations` | `cloud_integrations` table |
| `0005_add_insight_feedback` | `insight_feedback` table |

---

## Background Worker

Run the queue worker in a separate terminal to process background jobs:

```bash
cd backend
python -m app.workers.queue_worker
```

---

## Running Tests

```bash
cd backend
pytest tests/ -v
```

| File | Coverage |
|------|---------|
| `test_health.py` | `GET /health` |
| `test_logs_api.py` | Log ingest + paginated query |
| `test_alerts_api.py` | Alert delivery |
| `test_insights_api.py` | Insights + feedback |
| `test_llm.py` | LLM insight generation |
| `test_ollama.py` | Ollama fallback |
| `test_sdk.py` | SDK client unit tests |

---

## Repository Structure

```
Project Monitor/
├── backend/                     FastAPI application
│   ├── app/
│   │   ├── main.py              Entry point; mounts API router + React dist
│   │   ├── core/                Config (Pydantic-settings) + API-key auth
│   │   ├── api/v1/routes/       projects · logs · insights · alerts · integrations · services
│   │   ├── models/              SQLAlchemy ORM models
│   │   ├── schemas/             Pydantic request/response schemas
│   │   ├── services/            Insights engine · alert delivery · cloud normaliser
│   │   ├── workers/             Background queue worker
│   │   └── db/                  Session factory + declarative Base
│   ├── alembic/                 Database migrations
│   └── requirements.txt
│
├── frontend/                    React + Vite dashboard
│   ├── src/
│   │   ├── App.jsx              Root component + AppContext
│   │   ├── components/          Sidebar · Topbar
│   │   └── pages/               Overview · LogExplorer · AIInsights · Servers · Alerts · Integrations · NewProject
│   └── package.json
│
└── sdk/                         Publishable Python SDK
    ├── src/monitor_sdk/
    │   ├── client.py            Monitor class — batching · retry · heartbeat
    │   ├── middleware.py        MonitorASGIMiddleware
    │   └── context.py           ContextVar correlation ID
    └── pyproject.toml           project-monitor-sdk package metadata
```

---

## License

[MIT](LICENSE)


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

## 6. LLM Insights (Flexible Provider)

To enable LLM-backed root cause analysis, configure these generic settings in `.env`:

```bash
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=http://provider.h100.ams.val.akash.pub:32456/v1
LLM_MODEL=Qwen/Qwen3.6-35B-A3B-FP8
LLM_API_KEY=EMPTY
LLM_TIMEOUT_SECONDS=20
LLM_MAX_LOGS=25
LLM_MAX_CHARS_PER_LOG=400
LLM_TEMPERATURE=0.1
```

Ollama example (easy switch):

```bash
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=qwen3:4b-q4_K_M
LLM_API_KEY=
```

Backward compatibility: existing `OLLAMA_*` variables are still supported as fallbacks if `LLM_*` values are not set.

Behavior:

- Uses recent logs plus summary metrics as prompt input
- `LLM_PROVIDER=ollama` calls `/api/generate`
- `LLM_PROVIDER=openai_compatible` calls `/chat/completions`
- Expects strict JSON output for RCA, incident summary, and action plan
- Falls back to the rule-based insight engine if LLM is disabled, unreachable, or returns invalid JSON
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
