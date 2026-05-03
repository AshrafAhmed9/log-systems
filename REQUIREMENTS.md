# Distributed Log Processing & Analytics System
### Requirements Specification v1.0

---

## 1. Introduction

**Project Name:** Distributed Log Processing & Analytics System

**Purpose:** A backend system that ingests logs from multiple services, processes them asynchronously through a streaming pipeline, stores them in a database, and exposes real-time analytics and alerting — modelled after production observability platforms.

**Scope:** Covers ingestion API, message queue, stream processor, storage, query API, analytics endpoints, alert system, and internal metrics. Does not cover a frontend UI.

**Glossary:**
| Term | Definition |
|---|---|
| Log | A structured event record from a service (timestamp, level, message) |
| Producer | Any service sending logs to the ingestion API |
| Worker | Background process that consumes logs from the queue and writes to DB |
| Stream | Redis Streams channel used as the message queue |
| DLQ | Dead-Letter Queue — where failed messages are sent after exhausting retries |
| Error Rate | Percentage of ERROR-level logs out of total logs in a time window |

---

## 2. Stakeholders & Goals

**Primary Goal:** Build a resume-ready, GitHub-uploadable project that demonstrates distributed systems, real-time stream processing, and production-grade backend engineering.

**Secondary Goal:** Learn the concepts behind systems like ELK Stack, Datadog, and Splunk by building a simplified version from scratch.

**Success Criteria:**
- System handles 1000+ logs/sec under load test
- All analytics endpoints return correct data
- Alert fires within 5 seconds of an error spike
- Code is clean, simple, and explainable in an interview

---

## 2.5 Real-World Use Case

This system simulates a **production observability platform** used by backend services (e.g., auth, payments, recommendation systems) to monitor system health, detect anomalies, and trigger alerts in real time.

It is designed to replicate real-world logging pipelines used in distributed systems — similar to:
- **ELK Stack** (Elasticsearch + Logstash + Kibana)
- **Datadog** (log ingestion + alerting)
- **Splunk** (log search + analytics)

> Interview framing: *"I built a real-time log monitoring system similar to production observability platforms, with a streaming pipeline, anomaly detection, and alerting — all running in Docker."*

---

## 3. Functional Requirements

Priority scale: **M** = Must Have, **S** = Should Have, **C** = Could Have

| ID | Priority | Requirement |
|---|---|---|
| FR-001 | M | System accepts log events via `POST /logs` with fields: `timestamp`, `service_name`, `log_level`, `message` |
| FR-002 | M | Each accepted log is pushed onto a Redis Streams queue immediately |
| FR-003 | M | A background worker consumes logs from the queue asynchronously |
| FR-004 | M | Worker parses each log and enriches it with metadata (ingestion time, processing latency) |
| FR-005 | M | Worker batch-inserts enriched logs into PostgreSQL |
| FR-006 | M | `GET /logs` returns stored logs with filters: `service_name`, `log_level`, `start_time`, `end_time` |
| FR-007 | M | `GET /analytics/error-rate` returns error percentage per service over a configurable time window |
| FR-008 | M | `GET /analytics/top-errors` returns services ranked by error count |
| FR-009 | M | `GET /analytics/trends` returns log count per minute and identifies spikes |
| FR-010 | M | Alert system fires when error rate exceeds a configurable threshold within a time window |
| FR-011 | M | Load simulator script sends logs from 3 simulated services: `auth-service`, `payment-service`, `recommendation-service` |
| FR-012 | M | Load simulator targets 500–1000 logs/sec to enable performance measurement |
| FR-013 | S | `GET /health` returns system status (API up, Redis connected, DB connected) |
| FR-014 | S | `GET /internal/metrics` returns internal counters (logs ingested, worker lag, queue depth) |
| FR-015 | C | WebSocket endpoint for live log streaming to a connected client |

---

## 4. Non-Functional Requirements

### Performance Targets
| Metric | Target |
|---|---|
| Ingestion throughput | ≥ 1000 logs/sec |
| Ingestion latency (P99) | < 100ms |
| Concurrent producers supported | 500+ |
| Query response time (P95) | < 200ms |
| Alert detection latency | < 5 seconds from spike |
| Sustained capacity | 1M+ logs without performance degradation |

### Scalability
- API and worker are stateless — multiple instances can run behind a load balancer
- Redis Streams supports consumer groups, allowing multiple workers to share load

### Availability
- Worker uses consumer groups with `NOACK` disabled — messages are not lost if a worker dies
- Redis persistence (AOF mode) ensures queue survives restarts

### System Observability *(meta: observability for the observability system)*
- API logs request latency per endpoint (P50 / P95 / P99)
- Worker tracks processing time per batch
- Queue depth (Redis stream length) is monitored and exposed
- Internal error counts (worker failures, DB write errors) are tracked
- All exposed via `GET /internal/metrics`

### Consistency Model
- System follows **eventual consistency** between ingestion and query layers due to the asynchronous processing pipeline
- A log POSTed to the API will appear in query results only after the worker processes and stores it (typically < 1 second under normal load)

---

## 5. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        PRODUCERS                            │
│   auth-service   payment-service   recommendation-service   │
└───────────────────────────┬─────────────────────────────────┘
                            │  POST /logs
                            ▼
                   ┌─────────────────┐
                   │  FastAPI (API)  │  ← ingestion + query layer
                   └────────┬────────┘
                            │  XADD
                            ▼
                   ┌─────────────────┐
                   │  Redis Streams  │  ← message queue (buffer)
                   └────────┬────────┘
                            │  XREADGROUP
                            ▼
                   ┌─────────────────┐
                   │  Worker         │  ← async consumer + enrichment
                   └────────┬────────┘
                            │  batch INSERT
                            ▼
                   ┌─────────────────┐
                   │  PostgreSQL     │  ← persistent storage
                   └────────┬────────┘
                            │  SELECT
                            ▼
                   ┌─────────────────┐
                   │  Query API      │  ← GET /logs + analytics
                   └─────────────────┘
```

**Horizontal Scaling Plan:**
- Run N API instances behind a load balancer (e.g., Nginx)
- Run M worker instances in the same Redis consumer group — Redis distributes messages across them automatically
- Queues can be partitioned by service name in a future iteration

**Consistency model:** Eventual consistency between ingestion and query layers due to async pipeline.

---

## 6. API Specification

### POST /logs
Ingest a single log event.

**Request Body:**
```json
{
  "service_name": "payment-service",
  "log_level": "ERROR",
  "message": "Transaction failed: timeout",
  "timestamp": "2026-05-03T12:00:00Z"
}
```

**Response 202 Accepted:**
```json
{ "status": "queued", "log_id": "uuid-here" }
```

**Errors:** `422` validation error, `503` queue unavailable

---

### GET /logs
Query stored logs with optional filters.

**Query Parameters:**
| Param | Type | Example |
|---|---|---|
| service_name | string | `payment-service` |
| log_level | string | `ERROR` |
| start_time | ISO datetime | `2026-05-03T00:00:00Z` |
| end_time | ISO datetime | `2026-05-03T23:59:59Z` |
| limit | int (default 100) | `50` |

**Response 200:**
```json
{
  "total": 42,
  "logs": [
    {
      "id": 1,
      "service_name": "payment-service",
      "log_level": "ERROR",
      "message": "Transaction failed",
      "timestamp": "2026-05-03T12:00:00Z",
      "ingested_at": "2026-05-03T12:00:00.050Z"
    }
  ]
}
```

---

### GET /analytics/error-rate
Error percentage per service over a time window.

**Query Params:** `window_seconds` (default: 60)

**Response 200:**
```json
{
  "window_seconds": 60,
  "services": [
    { "service_name": "payment-service", "total": 200, "errors": 40, "error_rate_pct": 20.0 },
    { "service_name": "auth-service",    "total": 150, "errors": 3,  "error_rate_pct": 2.0  }
  ]
}
```

---

### GET /analytics/top-errors
Services ranked by error count.

**Response 200:**
```json
{
  "top_services": [
    { "service_name": "payment-service", "error_count": 320 },
    { "service_name": "auth-service",    "error_count": 45  }
  ]
}
```

---

### GET /analytics/trends
Log volume per minute and spike detection.

**Query Params:** `window_minutes` (default: 10)

**Response 200:**
```json
{
  "window_minutes": 10,
  "buckets": [
    { "minute": "2026-05-03T12:00:00Z", "total": 1200, "errors": 80, "is_spike": false },
    { "minute": "2026-05-03T12:01:00Z", "total": 3400, "errors": 900, "is_spike": true  }
  ]
}
```

---

### GET /health
```json
{ "api": "ok", "redis": "ok", "postgres": "ok" }
```

### GET /internal/metrics
```json
{
  "logs_ingested_total": 54321,
  "queue_depth": 12,
  "worker_lag_ms": 45,
  "worker_errors_total": 3,
  "db_write_errors_total": 0
}
```

---

## 7. Data Models

### PostgreSQL — `logs` table
```sql
CREATE TABLE logs (
    id            BIGSERIAL PRIMARY KEY,
    log_id        UUID NOT NULL UNIQUE,
    service_name  VARCHAR(100) NOT NULL,
    log_level     VARCHAR(20)  NOT NULL,
    message       TEXT         NOT NULL,
    timestamp     TIMESTAMPTZ  NOT NULL,
    ingested_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    processed_at  TIMESTAMPTZ,
    latency_ms    INTEGER
);

CREATE INDEX idx_logs_service   ON logs (service_name);
CREATE INDEX idx_logs_level     ON logs (log_level);
CREATE INDEX idx_logs_timestamp ON logs (timestamp DESC);
```

### Redis Streams — message payload
```json
{
  "log_id":      "550e8400-e29b-41d4-a716-446655440000",
  "service_name": "payment-service",
  "log_level":   "ERROR",
  "message":     "Transaction failed",
  "timestamp":   "2026-05-03T12:00:00Z",
  "ingested_at": "2026-05-03T12:00:00.030Z"
}
```

Stream name: `logs:stream`
Consumer group: `log-workers`

**Ordering guarantee:** Log ordering is maintained per service within Redis Streams partitions. Global ordering across services is not guaranteed — this is an intentional trade-off for throughput.

### Alert Event
```json
{
  "alert_id":     "uuid",
  "service_name": "payment-service",
  "error_rate":   35.5,
  "threshold":    20.0,
  "window_sec":   60,
  "triggered_at": "2026-05-03T12:01:00Z"
}
```

---

## 8. Alert & Anomaly Detection Spec

**Trigger condition:** `error_rate > ALERT_THRESHOLD_PCT` within the last `ALERT_WINDOW_SECONDS`

**Default config (environment variables):**
```
ALERT_THRESHOLD_PCT=20      # fire if >20% of logs are errors
ALERT_WINDOW_SECONDS=60     # evaluated over the last 60 seconds
```

**Detection algorithm:**
1. Worker checks error rate per service after each batch insert
2. Queries: `SELECT COUNT(*) WHERE log_level='ERROR' / COUNT(*) WHERE timestamp > now - window`
3. If rate exceeds threshold → write alert event to `logs:alerts` stream + print to worker log
4. Alert is deduplicated — same service will not re-alert within the same window

**Alert output:**
- Written to `logs:alerts` Redis stream (persistent)
- Logged to worker stdout (always visible)
- Optional: POST to a webhook URL if `ALERT_WEBHOOK_URL` env var is set

---

## 9. Failure Handling & Reliability

| Scenario | Handling |
|---|---|
| Worker crashes mid-batch | Redis consumer group keeps messages as pending; next worker (or restart) re-claims and reprocesses |
| DB temporarily unavailable | Worker retries with exponential backoff (1s, 2s, 4s, max 30s) |
| Duplicate message delivery | Deduplication by `log_id` (UUID) — DB unique constraint prevents double-writes |
| Redis unavailable | API returns `503`; producers should retry with backoff |
| Message permanently unprocessable | After 3 retry attempts, message moved to `logs:dlq` dead-letter stream |
| Overload / traffic spike | Redis Streams buffers all incoming messages — no messages dropped under temporary load spikes; **backpressure** is handled by the queue absorbing burst traffic |

---

## 10. Tech Stack

| Component | Technology | Reason |
|---|---|---|
| Ingestion & Query API | FastAPI (Python) | Async, fast, auto-generates OpenAPI docs |
| Message Queue | Redis Streams | Lightweight Kafka alternative; supports consumer groups; easy to run in Docker |
| Storage | PostgreSQL | ACID guarantees; powerful time-series queries with indexes |
| Worker | Python (asyncio) | Same language as API; simple to read and debug |
| Load Simulator | Python (httpx async) | Fast concurrent HTTP; easy to adjust concurrency |
| Containerisation | Docker Compose | One command to run entire system; reproducible environment |
| Config | Environment variables (.env) | Industry standard; keeps secrets out of code |

---

## 11. Development Milestones

Build in this exact order — each phase produces working, testable code:

| Phase | What You Build | Deliverable |
|---|---|---|
| 1 | Docker environment | `docker-compose.yml` with Redis + PostgreSQL running |
| 2 | FastAPI skeleton + POST /logs | API accepts and validates log payloads |
| 3 | Redis Streams integration | Logs pushed to queue; verify with `redis-cli XLEN logs:stream` |
| 4 | Worker consumer | Worker reads from queue and prints logs to stdout |
| 5 | PostgreSQL storage | Worker batch-inserts logs; verify with `SELECT COUNT(*) FROM logs` |
| 6 | GET /logs query endpoint | Filter logs by service, level, time range |
| 7 | Analytics endpoints | `/analytics/error-rate`, `/analytics/top-errors`, `/analytics/trends` |
| 8 | Alert system | Error spike detection fires alert to stdout + `logs:alerts` stream |
| 9 | Load simulator | Script sends 1000 logs/sec from 3 services |
| 10 | Performance measurement | Measure and document ingestion latency, throughput, query times |
| 11 | Health + internal metrics | `GET /health`, `GET /internal/metrics` |
| 12 | GitHub polish | README, architecture diagram, demo output |

---

## 12. Testing Strategy

**Unit tests:**
- Log payload validation (missing fields, invalid log level)
- Alert threshold logic (rate calculation, dedup logic)

**Integration tests:**
- `POST /logs` → Redis → worker → PostgreSQL round-trip
- `GET /logs` returns correct filtered results
- Alert fires when error rate exceeds threshold

**Load test (Phase 9):**
- Script: `simulator.py` using `httpx` async client
- Target: 1000 logs/sec sustained for 60 seconds
- Assertions:
  - P99 ingestion latency ≤ 100ms
  - Zero HTTP 5xx errors
  - All logs appear in DB after test (no data loss)

**Manual smoke test (after each phase):**
```bash
# Send one log
curl -X POST http://localhost:8000/logs \
  -H "Content-Type: application/json" \
  -d '{"service_name":"auth-service","log_level":"ERROR","message":"test","timestamp":"2026-05-03T12:00:00Z"}'

# Query it back
curl http://localhost:8000/logs?service_name=auth-service
```

---

## 13. Expected System Metrics

These are your **resume bullets** and **interview talking points**:

| Metric | Target |
|---|---|
| Ingestion throughput | ≥ 1000 logs/sec |
| Ingestion latency (P99) | < 100ms |
| Query response time (P95) | < 200ms |
| Alert detection latency | < 5 seconds |
| Data loss under normal operation | Zero |
| Worker crash recovery time | < 10 seconds |
| Sustained ingestion capacity | 1M+ logs without performance degradation |

---

## 14. AI-Native Development Context

Use this file as context at the start of every coding session:

> *"I am building a distributed log processing system. The REQUIREMENTS.md file in my project root describes the full spec. I am currently on Phase [X]. Write simple, readable code — I am learning alongside building. One step at a time."*

**Per-phase prompt hints:**
- Phase 1: *"Help me write a docker-compose.yml that runs Redis and PostgreSQL."*
- Phase 2: *"Help me write a FastAPI app with a POST /logs endpoint that validates this schema: [paste FR-001 schema]."*
- Phase 3: *"Help me add Redis Streams push to the FastAPI endpoint using the redis-py library."*
- Phase 4: *"Help me write a Python worker that reads from a Redis Streams consumer group."*
- Phase 5: *"Help me add batch insert to PostgreSQL inside the worker using asyncpg."*
- Phase 6–8: *"Help me add [endpoint name] as defined in the REQUIREMENTS.md API spec."*
- Phase 9: *"Help me write an async load simulator using httpx that sends 1000 logs/sec."*

**Key invariants to preserve across sessions:**
- All logs must have a UUID `log_id` for idempotency
- Worker always uses a Redis consumer group (never bare `XREAD`)
- DB schema must match the DDL in Section 7 exactly
- Environment config always via `.env` file — never hardcoded

---

## GitHub README Assets *(TODO — create after Phase 12)*

- [ ] Architecture diagram (draw with Excalidraw or draw.io — export as PNG)
- [ ] Demo GIF or terminal screenshot showing load test + analytics output
- [ ] Metrics table (copy from Section 13)
- [ ] Quick-start instructions: `docker compose up` + curl examples
