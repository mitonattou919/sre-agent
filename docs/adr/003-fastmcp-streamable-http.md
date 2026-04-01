# ADR-003: MCP Server implementation with FastMCP and Streamable HTTP

- **Status**: Accepted
- **Date**: 2026-03-30

## Context

The MCP Server must:

1. Expose Azure tools (`get_alerts`, `get_cost_summary`) in a way that Google ADK's `MCPToolset` can consume
2. Run as a local process during development and as an Azure Functions HTTP trigger in production — without changing tool code
3. Support mock mode (`USE_MOCK=true`) that returns static JSON for local development without real Azure credentials

We need to choose an MCP server framework and transport type.

## Decision

**Framework**: [FastMCP](https://github.com/jlowin/fastmcp)

FastMCP provides a decorator-based API (`@mcp.tool`) that registers Python functions as MCP tools. The same `FastMCP` app object can be:
- Run directly as a local process via `fastmcp run`
- Mounted as an ASGI app inside an Azure Functions HTTP trigger

**Transport**: Streamable HTTP

- Stateless, firewall-friendly, and compatible with Azure Functions' consumption plan
- `MCPToolset(StreamableHTTPConnectionParams(url=...))` in ADK connects to it directly
- Works over HTTPS with a standard function key header (`x-functions-key`)

**Mock mode**: Controlled by `USE_MOCK=true` environment variable. When enabled, tools return static JSON from `mcp_server/mock/` instead of calling Azure APIs.

## Alternatives Considered

| Option | Reason rejected |
|--------|----------------|
| stdio transport | Requires in-process or subprocess execution; incompatible with Azure Functions HTTP trigger |
| SSE transport | Requires persistent connection; doesn't fit Azure Functions' stateless model |
| Raw MCP SDK (no FastMCP) | More boilerplate; FastMCP handles protocol framing and tool schema generation |
| Custom REST endpoints (no MCP) | Would not benefit from `MCPToolset` auto-discovery and schema injection into the LLM |

## Consequences

**Positive**
- Tool definitions are plain Python functions — easy to unit-test in isolation
- The same `function_app.py` runs locally and on Azure Functions without modification
- `USE_MOCK=true` enables full local development without Azure credentials
- New tools can be added by decorating a function — no protocol boilerplate

**Negative**
- Streamable HTTP requires the Orchestrator to open a new HTTP connection per agent invocation (no persistent channel)
- FastMCP is an open-source library with a small maintenance team; long-term support is uncertain
- Azure Functions cold-start latency may add a few hundred milliseconds to the first tool call in a session
