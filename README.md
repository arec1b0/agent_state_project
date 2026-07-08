# Agent Session State Manager

A state-centric backend for LLM agent sessions. It moves agent state out of the orchestration framework and into a dedicated service that provides **event sourcing**, **optimistic concurrency control**, **exactly-once semantics**, and **deterministic rollback** — so consequential agent actions (payments, provisioning, side effects) are never applied twice and can always be audited or replayed.

Ships with a Python client SDK and a drop-in [LangGraph](https://github.com/langchain-ai/langgraph) checkpointer, so an existing LangGraph agent can persist its state through this service with two lines of code.

## Why

LLM agents crash, retry, and race. When an agent's checkpoint lives inside the worker process, a retried tool call can charge a credit card twice, and a crashed run leaves no authoritative record of what happened. This service makes the state transition itself the unit of correctness:

- **Every transition is an event** — appended to a PostgreSQL journal before the state snapshot is updated, giving a complete audit trail.
- **Optimistic concurrency control (OCC)** — each transition must declare the state version it was computed against; stale writers are rejected with `400` instead of silently clobbering state.
- **Exactly-once execution** — every transition carries an idempotency key; replays and duplicate deliveries are rejected with `409` before any side effect is recorded.
- **Deterministic rollback** — state at any historical version can be rebuilt by replaying the journal, and the live snapshot reset to it.
- **Per-session telemetry** — every transition is logged to MLflow (latency, state version, full event payload) under a run tagged with the session id.

## Architecture

```mermaid
flowchart LR
    subgraph Worker["Agent worker process"]
        LG[LangGraph graph] --> CP[APIStateCheckpointer]
        CP --> SDK[AgentStateClient]
    end

    SDK -- "HTTP/JSON" --> API[FastAPI service]

    subgraph Service["State service"]
        API --> Guard[ExactlyOnceGuard]
        API --> SM[StateManager]
        API --> RB[RollbackEngine]
    end

    Guard --> Redis[(Redis<br/>snapshots + idempotency locks)]
    SM --> Redis
    SM --> PG[(PostgreSQL<br/>event journal)]
    RB --> PG
    SM --> ML[MLflow<br/>telemetry]
    RB --> ML
```

| Component | Location | Responsibility |
|---|---|---|
| `StateManager` | `src/agent_session/core/state_manager.py` | Applies events: OCC check → journal append → snapshot write → telemetry |
| `ExactlyOnceGuard` | `src/agent_session/core/exactly_once.py` | Acquires a Redis `SET NX` lock per idempotency key (24 h TTL); rejects duplicates with `409` |
| `RollbackEngine` | `src/agent_session/core/rollback_engine.py` | Rebuilds state at a target version by replaying the journal, then overwrites the snapshot |
| `AgentTelemetry` | `src/agent_session/core/telemetry.py` | Logs transitions and rollbacks to MLflow (experiment `agent_sessions`, one run per session) |
| `KVStore` | `src/agent_session/infrastructure/kv_store.py` | Redis access: state snapshots (`state:{session_id}`) and idempotency locks |
| `EventJournal` | `src/agent_session/infrastructure/event_journal.py` | Append-only `event_journal` table in PostgreSQL (schema auto-created on startup) |
| `AgentStateClient` | `src/agent_session/client.py` | Async Python SDK for the HTTP API |
| `APIStateCheckpointer` | `src/agent_session/langgraph_integration.py` | LangGraph `BaseCheckpointSaver` that delegates checkpoint storage to this service |

### The state model

State is a versioned key-value context per session:

```python
class AgentState:
    session_id: str
    version: int = 0          # incremented by every applied event; the OCC token
    context: dict = {}        # the actual agent state payload
    status: str = "active"    # active | completed | suspended
```

A transition submits an `AgentEvent` whose `payload` dict is **merged** into `context` (`context.update(payload)`) and bumps `version` by 1. The event's `previous_version` must equal the current `version`, or the transition is rejected.

## Getting started

### Option A — full stack with Docker Compose

```bash
docker-compose up --build
```

This starts:

| Service | Port | Purpose |
|---|---|---|
| `api` | 8000 | The state manager (FastAPI/uvicorn) |
| `redis` | 6379 | Snapshots + idempotency locks |
| `db` (PostgreSQL 15) | 5432 | Event journal + MLflow backend store |
| `mlflow` | 5000 | Telemetry UI |

Interactive API docs: http://localhost:8000/docs · MLflow UI: http://localhost:5000

### Option B — local development (API on host, infra in Docker)

On Windows, the setup script installs `uv`, syncs dependencies, and starts Redis + PostgreSQL:

```powershell
.\scripts\setup_env_windows.ps1
docker-compose up -d mlflow   # telemetry is required; the API connects to MLflow on every transition
uv run uvicorn src.agent_session.api.routes:app --reload
```

On any platform, the equivalent manual steps:

```bash
uv sync
docker-compose up -d redis db mlflow
uv run uvicorn src.agent_session.api.routes:app --reload
```

### Run the demos

With the API running:

```bash
# Minimal LangGraph graph checkpointed through the API (two turns, state resumes)
uv run python -m src.agent_session.demo

# Mock LLM agent that executes a consequential tool call (credit card charge)
uv run python -m src.agent_session.llm_worker
```

Each run creates/updates an MLflow run tagged with the session id — open http://localhost:5000 to see per-transition latency, state versions, and archived event payloads.

## HTTP API

### `POST /session/transition`

Apply one event to a session. The idempotency key is checked first; the OCC version second.

```json
{
  "idempotency_key": "charge-attempt-42",
  "event": {
    "event_id": "3f2a…",
    "session_id": "prod-session-alpha",
    "event_type": "TOOL_CALL",
    "payload": { "charged_amount": 2500 },
    "timestamp": "2026-07-08T12:00:00.000000Z",
    "idempotency_key": "charge-attempt-42",
    "previous_version": 3
  }
}
```

Response `200`:

```json
{
  "status": "success",
  "message": "State transition applied successfully.",
  "current_state": {
    "session_id": "prod-session-alpha",
    "version": 4,
    "context": { "charged_amount": 2500 },
    "status": "active"
  }
}
```

| Status | Meaning |
|---|---|
| `200` | Event applied; new state returned |
| `400` | OCC failure — `previous_version` doesn't match the current state version. Re-read the state and retry with fresh data |
| `409` | Duplicate — this idempotency key was already processed (lock TTL: 24 h). Do **not** retry; the action already happened |
| `500` | Persistence failure (journal or snapshot write failed) — requires intervention |

### `GET /session/{session_id}`

Returns the current `AgentState`. Unknown sessions return a fresh state at `version: 0` (sessions are created implicitly by their first transition).

### `POST /session/rollback`

```json
{ "session_id": "prod-session-alpha", "target_version": 2 }
```

Replays the session's journal from the beginning, stopping once `target_version` is reached, and overwrites the Redis snapshot with the rebuilt state. Returns the rolled-back `AgentState`. Note that rollback rewrites only the snapshot — the journal itself is never mutated, and subsequent transitions continue from the rolled-back version.

## Python client

```python
from src.agent_session.client import AgentStateClient

client = AgentStateClient(base_url="http://127.0.0.1:8000")

state = await client.get_state("my-session")

new_state = await client.transition_state(
    session_id="my-session",
    event_type="TOOL_CALL",
    payload={"result": "ok"},
    previous_version=state["version"],
    idempotency_key="tool-call-1",   # optional; defaults to a fresh UUID
)

await client.close()
```

`transition_state` raises `RuntimeError` on any non-200 response, including OCC conflicts (400) and idempotency rejections (409).

## LangGraph integration

`APIStateCheckpointer` implements LangGraph's `BaseCheckpointSaver` against this API — the graph's `thread_id` becomes the session id:

```python
from src.agent_session.client import AgentStateClient
from src.agent_session.langgraph_integration import APIStateCheckpointer

client = AgentStateClient(base_url="http://127.0.0.1:8000")
graph = builder.compile(checkpointer=APIStateCheckpointer(client=client))

config = {"configurable": {"thread_id": "my-session"}}
result = await graph.ainvoke(input_state, config=config)
```

Every superstep produces one `LANGGRAPH_CHECKPOINT` transition. The checkpoint's own id is used as the idempotency key, so a retried save of the same checkpoint is a no-op instead of a double-apply — this is what makes consequential tool calls in the graph safe against replays.

**Serialization:** LangGraph checkpoints contain rich Python objects (`HumanMessage`, `AIMessage`, …). They are serialized with LangGraph's `JsonPlusSerializer`, whose output is a binary blob; the blob is base64-encoded so it can travel inside the JSON event payload, and decoded on read.

**Limitations:** async-only (`ainvoke`/`astream`; the sync `invoke` raises `NotImplementedError`), no checkpoint history listing (`alist` yields nothing — only the latest checkpoint is restorable via `aget_tuple`), and pending writes are not persisted (`aput_writes` is a no-op).

## Configuration

All configuration is via environment variables:

| Variable | Default | Used by |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Snapshots and idempotency locks |
| `DB_URL` | `postgresql://user:pass@localhost:5432/agent_state` | Event journal |
| `MLFLOW_TRACKING_URI` | `http://localhost:5000` | Telemetry |

All three backing services must be reachable for the API to process transitions.

## Development

```bash
uv sync                      # install deps (incl. dev group)
uv run pytest tests/ -v      # unit tests (infrastructure is mocked; no services needed)
uv run ruff check .          # lint
uv run mypy src/             # type check (currently reports known pre-existing errors)
```

Tests cover the OCC and persistence behavior of `StateManager`, the idempotency guard, and journal-replay rollback (`tests/`).

### Project layout

```
src/agent_session/
├── api/               # FastAPI app: routes, DI wiring, exception handlers
├── core/              # Domain logic: state manager, exactly-once guard, rollback, telemetry
├── infrastructure/    # Redis KV store, PostgreSQL journal, DB pool lifecycle
├── models/            # Pydantic models: AgentState, AgentEvent, API contracts
├── utils/             # structlog JSON logging setup
├── client.py          # Async HTTP client SDK
├── langgraph_integration.py  # LangGraph checkpointer
├── demo.py            # Minimal checkpointed-graph demo
└── llm_worker.py      # Mock-LLM agent demo with a consequential tool call
```

## Deployment

- **Docker:** the [Dockerfile](Dockerfile) builds a slim Python 3.11 image with `uv`, running uvicorn on port 8000.
- **Kubernetes:** manifests in [deployment/k8s/](deployment/k8s/) — a 3-replica rolling-update Deployment with liveness/readiness probes, a Service, and a ConfigMap for the environment variables above.
- **CI:** [.github/workflows/ci.yml](.github/workflows/ci.yml) runs ruff, mypy, and pytest on every push/PR to `main`.
- **CD:** [.github/workflows/cd.yml](.github/workflows/cd.yml) builds and pushes the Docker image on `v*` tags (update the Docker Hub repo name in the workflow and k8s manifests before use).
- **Monitoring:** [deployment/monitoring/](deployment/monitoring/) contains a Prometheus scrape config and a Grafana dashboard as scaffolding — note the API does not yet expose a `/metrics` endpoint, so these require wiring up `prometheus-client` first. Runtime observability today comes from MLflow and structured JSON logs (structlog).

## Logging

The API emits structured JSON logs via structlog (ISO timestamps, log level, logger name), suitable for ingestion by any log aggregator. Key events: `processing_event`, `initiating_rollback`, `system_startup`/`system_shutdown`, and `value_error`/`runtime_error` from the exception handlers.
