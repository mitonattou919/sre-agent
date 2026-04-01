# SRE Agent Requirements

> Azure-focused SRE Agent — Requirements Definition
> Last updated: 2026-03-28

---

## 1. Overview

An SRE agent for Azure environments that allows teams to check alerts and costs using natural language via CLI. The agent uses Google ADK (LlmAgent) with Gemini 2.5 Flash and exposes Azure monitoring capabilities through MCP tools.

**Goals:**
- Reduce operational toil by enabling natural language queries for Azure alerts and cost data
- Support interactive, context-aware conversations (multi-turn chat)
- Work in both local development (mock data) and production (real Azure APIs)

---

## 2. Phase Plan

| Phase | Scope | Status |
|---|---|---|
| **MVP** | MCP Server + Orchestrator + CLI (interactive) | **Current target** |
| Phase 2 | Azure Storage Table session persistence | Future |
| Phase 3 | Web UI (dashboard + chat) | Future |

---

## 3. MVP Requirements

### 3.1 MCP Server

Exposes Azure resource data as MCP tools via FastMCP.

#### Tools

| Tool | Description |
|---|---|
| `get_alerts` | Fetch active alerts from Azure Monitor |
| `get_cost_summary` | Fetch cost summary from Cost Management API |

#### Tool Parameters

**`get_alerts`**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `resource_group` | str | No | Filter by resource group |
| `severity` | int | No | Filter by severity (0–4) |

> `subscription_id` is NOT a parameter — it is read from the `AZURE_SUBSCRIPTION_ID` environment variable automatically.

**`get_cost_summary`**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `period` | str | No | `today` / `7d` / `30d` (default: `7d`) |

> `subscription_id` is NOT a parameter — same as above.

#### Runtime Environments

The MCP Server must support **both** of the following:
- **Local process**: Run directly with FastMCP (`python -m mcp_server.function_app`)
- **Azure Functions**: Mount FastMCP app as an HTTP trigger on `/mcp`

Mock mode is enabled by setting `USE_MOCK=true`. In mock mode, tools return static JSON data from `mcp_server/mock/`.

#### Error Handling

When Azure API calls fail:
- Return structured error information from the tool
- The agent must relay the error content to the user in natural language (e.g., "Failed to fetch alerts: Insufficient permissions on subscription xxx")

---

### 3.2 Orchestrator (FastAPI + Google ADK)

#### API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/chat` | Send message, get agent response |
| `GET` | `/chat/history/{session_id}` | Get conversation history |
| `DELETE` | `/chat/session/{session_id}` | Delete session |
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
  "reply": "## Active Alerts (2)\n...",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "tool_calls": ["get_alerts"]
}
```

#### Agent Configuration

- **Framework**: Google ADK (`LlmAgent`)
- **LLM**: Gemini 2.5 Flash (fixed for MVP)
- **Session**: `InMemorySessionService` (MVP) — replaced by Storage Table in Phase 2
  > **Constraint**: Sessions are stored in-process only. **Single-instance deployment is required.** Scaling to 2+ App Service instances will cause session loss. Migrate to Phase 2 (Storage Table) before any multi-instance scaling.
- **System prompt**: Instructs the agent to adapt its response language to the user's language, and always format output in Markdown
- **Tools**: Connected via `MCPToolset` (Streamable HTTP)

#### Authentication

| Environment | Behavior |
|---|---|
| Production | Entra ID JWT validation (`Authorization: Bearer <token>`) |
| Local dev | Auth skipped when `SKIP_AUTH=true` |

`user_id` is extracted automatically from the JWT `oid` claim — never passed by the client.

#### Deployment Target

Azure App Service (Python 3.13, `uvicorn orchestrator.main:app`)

---

### 3.3 CLI

#### Commands

```
sre-agent                # Start interactive mode (default)
sre-agent login          # Authenticate via Device Code Flow
sre-agent chat           # Start interactive mode (alias for default)
sre-agent alerts         # One-shot: list active alerts
sre-agent cost           # One-shot: cost summary
```

Running `sre-agent` with no subcommand launches interactive mode directly. `sre-agent chat` is kept as an alias.

#### Interactive Mode Requirements

- Maintains `session_id` across turns to enable multi-turn conversation
- Displays tool calls as they happen: `🔧 get_alerts`
- Renders agent responses with `rich` (Markdown formatting)
- User prompt is `>` only — no label prefix on either side
- In-session control commands use slash-command syntax: `/exit`, `/help`, `/session`

Example:

```
$ sre-agent
Session: abc-123
SRE Agent ready.

> Are there any active alerts?
🔧 get_alerts
## Active Alerts (2)
- **Critical** `func-app-prod` — CPU usage > 95%
- **Warning** `storage-account-01` — Throttling detected

> How does that compare to last week's costs?
🔧 get_cost_summary
...

> /exit
```

#### Authentication

| Environment | Behavior |
|---|---|
| Production | Device Code Flow (`azure-identity`), token cached at `~/.sre-agent/token_cache` |
| Local dev | Auth skipped when `SKIP_AUTH=true` in `.env` |

---

## 4. Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Python version | 3.13 | |
| Package manager | **uv** | |
| MCP framework | FastMCP | Streamable HTTP transport |
| Orchestrator | FastAPI + Google ADK | |
| LLM | Gemini 2.5 Flash | Fixed for MVP |
| Session (MVP) | `InMemorySessionService` | Replaced by Storage Table in Phase 2 |
| CLI | Click + httpx + rich | |
| Azure SDK | `azure-mgmt-monitor`, `azure-mgmt-costmanagement`, `azure-identity` | |
| Auth (API) | Entra ID / Bearer token | JWT validated with `python-jose` |
| Auth (CLI) | Device Code Flow | `azure-identity` |
| Testing | **pytest + pytest-mock** | |
| CI | None (MVP period) | |

---

## 5. Directory Structure (MVP)

```
sre-agent/
├── mcp_server/
│   ├── function_app.py        # FastMCP app entry point (works locally + Azure Functions)
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
│   ├── auth.py                # Entra ID JWT validation / skip control
│   ├── mcp_client.py          # MCPToolset connection config
│   └── config.py              # pydantic-settings
│
├── cli/
│   ├── main.py                # Click entry point
│   ├── auth.py                # Device Code Flow / token cache
│   ├── client.py              # httpx client for FastAPI
│   └── config.py              # pydantic-settings
│
├── tests/
│   ├── test_mcp_tools.py
│   ├── test_orchestrator.py
│   └── test_cli.py
│
├── pyproject.toml             # uv dependency management (all components)
├── .env.example
└── docs/
    ├── pre-research.md
    └── requirements.md        # This file
```

---

## 6. Environment Variables

### mcp_server

| Variable | Description | Example |
|---|---|---|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID (fixed, single subscription) | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `USE_MOCK` | Use mock data instead of real Azure APIs | `true` |
| `AZURE_CLIENT_ID` | Managed Identity client ID (user-assigned) | `xxxxxxxx-...` |

### orchestrator

| Variable | Description | Example |
|---|---|---|
| `GEMINI_API_KEY` | Gemini API key | `AIza...` |
| `MCP_SERVER_URL` | MCP Server URL | `http://localhost:7071/mcp` |
| `ENTRA_TENANT_ID` | Entra tenant ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `ENTRA_APP_CLIENT_ID` | App Registration client ID | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` |
| `SKIP_AUTH` | Skip Entra ID validation (local dev only) | `true` |
| `MCP_FUNCTION_KEY` | Azure Functions access key (production only) | `xxxxxxxx...` |

### cli

| Variable | Description | Example |
|---|---|---|
| `ORCHESTRATOR_URL` | FastAPI base URL | `http://localhost:8000` |
| `ENTRA_TENANT_ID` | Entra tenant ID | same as orchestrator |
| `ENTRA_APP_CLIENT_ID` | App Registration client ID | same as orchestrator |
| `SKIP_AUTH` | Skip authentication (local dev only) | `true` |

---

## 7. Implementation Order (MVP)

1. `mcp_server/tools/` — `get_alerts` and `get_cost_summary` with mock support
2. `mcp_server/function_app.py` — Expose tools via FastMCP
3. `orchestrator/agent.py` + `runner.py` — LlmAgent + in-memory session
4. `orchestrator/main.py` + `auth.py` — FastAPI endpoints + auth
5. `cli/` — Click CLI (interactive + one-shot commands)
6. `tests/` — pytest unit tests for all components

---

## 8. Verification

```bash
# 1. Start MCP Server locally (mock mode)
USE_MOCK=true uv run python -m mcp_server.function_app

# 2. Start Orchestrator (auth skipped)
SKIP_AUTH=true GEMINI_API_KEY=xxx MCP_SERVER_URL=http://localhost:7071/mcp \
  uv run uvicorn orchestrator.main:app --reload

# 3. Interactive chat via CLI
SKIP_AUTH=true ORCHESTRATOR_URL=http://localhost:8000 \
  uv run sre-agent chat

# 4. One-shot commands
uv run sre-agent alerts
uv run sre-agent cost --period 7d

# 5. Run tests
uv run pytest tests/ -v
```
