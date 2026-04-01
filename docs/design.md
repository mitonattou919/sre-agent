# SRE Agent — Design Document

> Azure-focused SRE Agent
> Last updated: 2026-03-30

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Component Design](#3-component-design)
   - 3.1 [MCP Server](#31-mcp-server)
   - 3.2 [Orchestrator](#32-orchestrator)
   - 3.3 [CLI](#33-cli)
4. [Data Flow](#4-data-flow)
5. [Authentication & Authorization](#5-authentication--authorization)
6. [Session Management](#6-session-management)
7. [Error Handling](#7-error-handling)
8. [Configuration & Environment Variables](#8-configuration--environment-variables)
9. [Directory Structure](#9-directory-structure)
10. [Deployment](#10-deployment)
11. [Testing Strategy](#11-testing-strategy)
12. [Phase Plan & Future Work](#12-phase-plan--future-work)

---

## 1. Overview

SRE Agent is a natural language interface for Azure operational data. Teams query active alerts and cost summaries through a CLI (and eventually a Web UI) without needing to navigate the Azure Portal or write API calls by hand.

**Goals**
- Reduce operational toil by enabling natural language queries for Azure Monitor alerts and Cost Management data
- Support interactive, context-aware multi-turn conversations
- Run in both local development (mock data) and production (real Azure APIs) with minimal configuration change

**Out of scope (MVP)**
- Web UI dashboard
- Azure Storage Table session persistence
- Streaming responses (SSE)

---

## 2. Architecture

### 2.1 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│  CLI (local)  /  Web UI (future)                            │
│                │  Bearer token (Entra ID)                   │
│                ▼                                            │
│  Orchestrator  ── FastAPI + Google ADK  (Azure App Service) │
│   ├─ ADK Runner (session management)                        │
│   │   └─ LlmAgent (Gemini 2.5 Flash)                        │
│   │       └─ MCPToolset                                     │
│   │           │  Streamable HTTP                            │
│   │           ▼                                             │
│   │   MCP Server  ── FastMCP  (Azure Functions)             │
│   │    ├─ get_alerts      → Azure Monitor                   │
│   │    └─ get_cost_summary → Cost Management API            │
│   └─ InMemorySessionService (MVP)                           │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Architecture Decisions

Key decisions and their rationale are recorded as ADRs:

| ADR | Decision |
|-----|----------|
| [ADR-001](adr/001-three-tier-architecture.md) | Three-tier split (MCP Server / Orchestrator / CLI) — isolates Azure credentials server-side and allows independent deployment |
| [ADR-002](adr/002-google-adk-gemini.md) | Google ADK (`LlmAgent`) + Gemini 2.5 Flash — first-class `MCPToolset` support and built-in session service interface |
| [ADR-003](adr/003-fastmcp-streamable-http.md) | FastMCP + Streamable HTTP transport — stateless, Azure Functions compatible, natively consumed by ADK |
| [ADR-004](adr/004-mcp-server-deployment.md) | MCP Server on Azure Functions (Consumption plan) — scale-to-zero cost model, Managed Identity for Azure API access |
| [ADR-005](adr/005-session-management.md) | `InMemorySessionService` for MVP; `StorageTableSessionService` in Phase 2 |
| [ADR-006](adr/006-authentication.md) | Entra ID JWT validation on the API; Device Code Flow for CLI token acquisition |

---

## 3. Component Design

### 3.1 MCP Server

**Role**: Exposes Azure resource data as MCP tools over Streamable HTTP.

**Entry point**: `mcp_server/function_app.py`
**Framework**: FastMCP mounted as an Azure Functions HTTP trigger on `/mcp`

#### Tools

| Tool | Description |
|------|-------------|
| `get_alerts` | Fetch active alerts from Azure Monitor |
| `get_cost_summary` | Fetch cost summary from Cost Management API |

#### `get_alerts`

```python
@mcp.tool
async def get_alerts(
    resource_group: str | None = None,
    severity: int | None = None,
) -> list[dict]:
    ...
```

- `subscription_id` is read from `AZURE_SUBSCRIPTION_ID` env var — never a parameter
- Filters: `resource_group` (optional), `severity` 0–4 (optional)
- Azure SDK: `azure-mgmt-monitor` via `MonitorManagementClient`

#### `get_cost_summary`

```python
@mcp.tool
async def get_cost_summary(period: str) -> dict:
    ...
```

- `period`: `today` | `7d` | `30d`
- Azure SDK: `azure-mgmt-costmanagement` via `CostManagementClient`

#### Mock Mode

When `USE_MOCK=true`, tools return static JSON from:
- `mcp_server/mock/alerts.json`
- `mcp_server/mock/cost.json`

No Azure credentials are required in mock mode.

#### Azure Identity

In production, the Function App uses a **Managed Identity** (`DefaultAzureCredential`). For user-assigned identity, `AZURE_CLIENT_ID` must be set.

---

### 3.2 Orchestrator

**Role**: Receives chat messages from clients, runs the LLM agent with MCP tools, and returns natural language responses.

**Entry point**: `orchestrator/main.py`
**Framework**: FastAPI
**Deployment**: Azure App Service (`uvicorn orchestrator.main:app`)

#### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat` | Send a message, receive agent response |
| `GET` | `/chat/history/{session_id}` | Retrieve conversation history |
| `DELETE` | `/chat/session/{session_id}` | Delete a session |
| `GET` | `/health` | Health check |

#### `/chat` Request / Response

```json
// Request
{
  "message": "Are there any active alerts?",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}

// Response
{
  "reply": "## Active Alerts (2)\n- **Critical** `func-app-prod` — CPU > 95%\n...",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "tool_calls": ["get_alerts"]
}
```

- `session_id` is optional on the first request; a new UUID is generated if omitted
- `user_id` is extracted from the JWT `oid` claim — never supplied by the client

#### Agent Configuration (`orchestrator/agent.py`)

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StreamableHTTPConnectionParams

sre_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="sre_agent",
    instruction=(
        "You are an Azure SRE agent. "
        "Check alerts and costs, and report findings with root cause and recommended actions. "
        "Adapt your response language to the user's language. "
        "Always format output in Markdown."
    ),
    tools=[
        MCPToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=settings.MCP_SERVER_URL,
                headers={"x-functions-key": settings.MCP_FUNCTION_KEY},
            )
        )
    ],
)
```

#### Runner (`orchestrator/runner.py`)

- Wraps `google.adk.runners.Runner` with `InMemorySessionService` (MVP)
- Accepts `(message, session_id, user_id)` and returns `(reply, tool_calls)`
- Session is created on first call; subsequent calls with the same `session_id` continue the conversation

---

### 3.3 CLI

**Role**: Interactive and one-shot natural language interface to the Orchestrator.

**Entry point**: `cli/main.py`
**Framework**: Click + httpx + rich

#### Commands

```
sre-agent            # Start interactive mode (default)
sre-agent login      # Authenticate via Device Code Flow; cache token
sre-agent chat       # Start interactive mode (alias for default)
sre-agent alerts     # One-shot: list active alerts
sre-agent cost       # One-shot: cost summary (--period today|7d|30d)
```

Running `sre-agent` with no subcommand launches interactive mode directly. `sre-agent chat` is kept as an alias for the same behaviour.

#### Interactive Mode

```
$ sre-agent
Session: abc-123
SRE Agent ready.

> Are there any active alerts?
🔧 get_alerts
## Active Alerts (2)
- **Critical** `func-app-prod` — CPU usage > 95%
- **Warning** `storage-account-01` — Throttling detected

> /exit
```

- Running `sre-agent` (no args) or `sre-agent chat` both start interactive mode
- User prompt is `>` only — no label prefix
- Agent responses are printed directly below with no prefix
- Tool calls are displayed inline as `🔧 <tool_name>`
- Responses are rendered with `rich` Markdown
- In-session control commands use slash-command syntax:

| Command | Action |
|---------|--------|
| `/exit` | Exit interactive mode |
| `/help` | Show available slash commands |
| `/session` | Show current session ID |

#### HTTP Client (`cli/client.py`)

- `httpx.AsyncClient` with `Authorization: Bearer <token>` header
- Base URL configured via `ORCHESTRATOR_URL`

---

## 4. Data Flow

### Interactive Chat Turn

```
User input
  │
  ▼ (1) CLI sends POST /chat {message, session_id}
Orchestrator (FastAPI)
  │ validate JWT → extract user_id
  │
  ▼ (2) Runner.run(message, session_id, user_id)
ADK LlmAgent
  │ LLM decides to call get_alerts
  │
  ▼ (3) MCPToolset → POST /mcp (Streamable HTTP)
MCP Server (Azure Functions)
  │ calls Azure Monitor API
  │ returns tool result JSON
  │
  ▼ (4) Tool result injected into LLM context
ADK LlmAgent
  │ generates natural language response
  │
  ▼ (5) Orchestrator returns {reply, session_id, tool_calls}
CLI
  │ renders Markdown with rich
  ▼
User sees response
```

---

## 5. Authentication & Authorization

See [ADR-006](adr/006-authentication.md) for the full rationale.

### API Layer (Orchestrator)

| Environment | Behaviour |
|-------------|-----------|
| Production | `Authorization: Bearer <Entra ID JWT>` required on all endpoints |
| Local dev | Auth skipped when `SKIP_AUTH=true` |

JWT validation:
- JWKS fetched from `https://login.microsoftonline.com/{ENTRA_TENANT_ID}/discovery/v2.0/keys`
- Algorithm: RS256
- Audience: `api://{ENTRA_APP_CLIENT_ID}`
- `user_id` = `payload["oid"]`

### CLI Layer

| Environment | Behaviour |
|-------------|-----------|
| Production | Device Code Flow via `azure-identity`; token cached at `~/.sre-agent/token_cache` |
| Local dev | Auth skipped when `SKIP_AUTH=true` in `.env` |

### MCP Server Layer

Accessed only from the Orchestrator using a **Function Key** (`x-functions-key` header). The Function App itself authenticates to Azure APIs via **Managed Identity** — no secrets stored.

---

## 6. Session Management

See [ADR-005](adr/005-session-management.md) for the full rationale.

### MVP: `InMemorySessionService`

- Built-in to Google ADK; zero configuration
- State is lost on process restart
- Suitable for single-instance deployment

### Phase 2: `StorageTableSessionService`

Custom implementation extending `google.adk.sessions.BaseSessionService`.

**Table schema (Azure Storage Table)**

| Column | Value | Notes |
|--------|-------|-------|
| `PartitionKey` | `{app_name}_{user_id}` | Enables efficient per-user scans |
| `RowKey` | `session_id` (UUID) | Unique session identifier |
| `events` | JSON string | `[Event.model_dump(), ...]` |
| `state` | JSON string | Session state dict |
| `updated_at` | ISO 8601 | Last updated timestamp |

**Serialisation**

```python
# Save
"events": json.dumps([e.model_dump() for e in session.events])

# Restore
events = [Event.model_validate(e) for e in json.loads(entity["events"])]
```

The swap from MVP to Phase 2 is a one-line change in `orchestrator/runner.py`.

---

## 7. Error Handling

### MCP Server

When an Azure API call fails, the tool returns structured error information:

```json
{
  "error": true,
  "message": "Failed to fetch alerts: Insufficient permissions on subscription xxxxxxxx"
}
```

### Orchestrator

- The LLM agent is instructed to relay tool errors to the user in natural language
- FastAPI returns standard HTTP error responses (4xx/5xx) for request validation and auth failures

### CLI

- HTTP errors from the Orchestrator are displayed with the status code and message
- Auth errors prompt the user to run `sre-agent login`

---

## 8. Configuration & Environment Variables

### MCP Server

| Variable | Description | Example |
|----------|-------------|---------|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `USE_MOCK` | Enable mock mode | `true` |
| `AZURE_CLIENT_ID` | User-assigned Managed Identity client ID | `xxxxxxxx-...` |

### Orchestrator

| Variable | Description | Example |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Gemini API key | `AIza...` |
| `MCP_SERVER_URL` | MCP Server base URL | `http://localhost:7071/mcp` |
| `MCP_FUNCTION_KEY` | Azure Functions access key | `xxxxxxxx...` |
| `ENTRA_TENANT_ID` | Entra tenant ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ENTRA_APP_CLIENT_ID` | App Registration client ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `SKIP_AUTH` | Skip JWT validation (local dev only) | `true` |

### CLI

| Variable | Description | Example |
|----------|-------------|---------|
| `ORCHESTRATOR_URL` | Orchestrator base URL | `http://localhost:8000` |
| `ENTRA_TENANT_ID` | Entra tenant ID | same as orchestrator |
| `ENTRA_APP_CLIENT_ID` | App Registration client ID | same as orchestrator |
| `SKIP_AUTH` | Skip authentication (local dev only) | `true` |

---

## 9. Directory Structure

```
sre-agent/
├── mcp_server/
│   ├── function_app.py        # FastMCP app — runs locally and as Azure Functions HTTP trigger
│   ├── tools/
│   │   ├── alerts.py          # get_alerts implementation
│   │   └── cost.py            # get_cost_summary implementation
│   └── mock/
│       ├── alerts.json        # Mock alert data
│       └── cost.json          # Mock cost data
│
├── orchestrator/
│   ├── main.py                # FastAPI endpoint definitions
│   ├── agent.py               # LlmAgent definition
│   ├── runner.py              # ADK Runner + session management
│   ├── auth.py                # Entra ID JWT validation
│   ├── mcp_client.py          # MCPToolset connection config
│   └── config.py              # pydantic-settings
│
├── cli/
│   ├── main.py                # Click entry point
│   ├── auth.py                # Device Code Flow / token cache
│   ├── client.py              # httpx client for Orchestrator
│   └── config.py              # pydantic-settings
│
├── tests/
│   ├── test_mcp_tools.py
│   ├── test_orchestrator.py
│   └── test_cli.py
│
├── docs/
│   ├── pre-research.md
│   ├── requirements.md
│   ├── design.md              # This document
│   └── adr/                   # Architecture Decision Records
│
├── pyproject.toml
└── .env.example
```

---

## 10. Deployment

### MCP Server — Azure Functions

| Setting | Value |
|---------|-------|
| Plan | Consumption (pay-per-use) |
| Runtime | Python 3.13 |
| Trigger | HTTP trigger at `/mcp` |
| Identity | System-assigned Managed Identity |
| RBAC roles | `Monitoring Reader`, `Cost Management Reader` |
| Access control | Function Key via `x-functions-key` header |

### Orchestrator — Azure App Service

| Setting | Value |
|---------|-------|
| Plan | B1 or higher (Basic) |
| Runtime | Python 3.13 |
| Startup command | `uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000` |
| Config | App Service "Configuration" blade |

### Local Development

```bash
# 1. MCP Server (mock mode)
USE_MOCK=true uv run python -m mcp_server.function_app

# 2. Orchestrator (auth skipped)
SKIP_AUTH=true GEMINI_API_KEY=xxx MCP_SERVER_URL=http://localhost:7071/mcp \
  uv run uvicorn orchestrator.main:app --reload

# 3. CLI (interactive)
SKIP_AUTH=true ORCHESTRATOR_URL=http://localhost:8000 \
  uv run sre-agent chat
```

---

## 11. Testing Strategy

**Framework**: pytest + pytest-mock

| Test file | Scope |
|-----------|-------|
| `tests/test_mcp_tools.py` | MCP tools in mock mode; verifies tool output schema and filter logic |
| `tests/test_orchestrator.py` | FastAPI endpoints; mocks ADK Runner to isolate HTTP layer |
| `tests/test_cli.py` | CLI commands; mocks httpx client to isolate Click layer |

All tests run without Azure credentials by using mock mode and dependency injection.

```bash
uv run pytest tests/ -v
```

---

## 12. Phase Plan & Future Work

| Phase | Scope | Status |
|-------|-------|--------|
| **MVP** | MCP Server + Orchestrator + CLI (interactive) | Current target |
| Phase 2 | Azure Storage Table session persistence | Future |
| Phase 3 | Web UI (dashboard + chat) | Future |

### Backlog

| Priority | Item |
|----------|------|
| High | SSE streaming for `/chat` responses |
| Medium | Additional MCP tools: `metrics_query`, `waf_analyze` |
| Medium | Web UI dashboard |
| Low | Slack Bot interface |
