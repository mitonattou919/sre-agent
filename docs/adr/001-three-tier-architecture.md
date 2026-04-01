# ADR-001: Three-tier architecture — MCP Server / Orchestrator / CLI

- **Status**: Accepted
- **Date**: 2026-03-30

## Context

We need to build an SRE tool that lets teams query Azure alerts and cost data in natural language via CLI. Several concerns must be separated:

1. **Azure API access** — credentials, subscription scope, and Azure SDK dependencies should be isolated
2. **Agent orchestration** — LLM invocation, session state, and tool routing are distinct from Azure API logic
3. **User interface** — the CLI (and future Web UI) should be thin clients that communicate over HTTP

A monolithic design would couple Azure SDK dependencies directly to the LLM framework and the CLI, making independent testing, deployment, and replacement difficult.

## Decision

We adopt a three-tier architecture with clear HTTP boundaries between layers:

```
CLI (local)
  │  Bearer token (Entra ID)
  ▼
Orchestrator — FastAPI + Google ADK (Azure App Service)
  │  Streamable HTTP (MCP)
  ▼
MCP Server — FastMCP (Azure Functions)
  │  Azure SDK (Managed Identity)
  ▼
Azure Monitor / Cost Management
```

Each tier is a separate deployable unit with its own dependency set and environment variables.

## Alternatives Considered

| Option | Reason rejected |
|--------|----------------|
| Monolith (single process) | Couples Azure SDK, LLM framework, and CLI; hard to test and deploy independently |
| CLI calls Azure APIs directly | Embeds Azure credentials on every workstation; no central session history |
| Orchestrator calls Azure APIs directly (no MCP) | Bypasses the tool protocol; harder to add new Azure tools or swap the transport |

## Consequences

**Positive**
- Each tier can be deployed, scaled, and replaced independently
- Azure credentials stay server-side (MCP Server uses Managed Identity)
- Future Web UI can reuse the same Orchestrator API without changes
- MCP Server can be replaced with a different transport (e.g., stdio) without touching the Orchestrator

**Negative**
- Two extra network hops per request (CLI → Orchestrator → MCP Server)
- Local development requires running two processes (`mcp_server` + `orchestrator`)
- More moving parts to configure and monitor
