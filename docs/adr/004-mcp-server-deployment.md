# ADR-004: Deploy MCP Server on Azure Functions

- **Status**: Accepted
- **Date**: 2026-03-30

## Context

The MCP Server is an HTTP endpoint that:

1. Handles sporadic, short-lived requests from the Orchestrator (tool invocations during a chat turn)
2. Requires access to Azure Monitor and Cost Management APIs via Managed Identity
3. Must scale to zero when idle to minimise cost for an internal tool with low and bursty traffic

We need a deployment target that satisfies these constraints.

## Decision

Deploy the MCP Server as an **Azure Functions HTTP trigger** on the **Consumption plan**.

- The `FastMCP` app is mounted at the `/mcp` path of an HTTP trigger function in `mcp_server/function_app.py`
- **System-assigned Managed Identity** is enabled on the Function App; no secrets are stored in code or environment variables
- Required Azure RBAC roles assigned to the Managed Identity:
  - `Monitoring Reader` — Azure Monitor alerts
  - `Cost Management Reader` — Cost Management API
- The function is secured with a **Function Key** passed via the `x-functions-key` header

## Alternatives Considered

| Option | Reason rejected |
|--------|----------------|
| Azure App Service (always-on) | Higher base cost for a tool with bursty, low-frequency usage |
| Azure Container Apps | Adds container build/push pipeline; more operational overhead for an MVP |
| Co-locate MCP Server in the Orchestrator process | Couples deployment lifecycles; loses the ability to scale or replace independently |
| Azure Container Instances | No native event-driven scaling; manual management |

## Consequences

**Positive**
- Scale-to-zero means near-zero cost when the tool is not actively used
- Managed Identity eliminates long-lived secrets for Azure API access
- Function Key provides a simple, low-friction access control layer between the Orchestrator and MCP Server
- Independent deployment: MCP Server can be updated without redeploying the Orchestrator

**Negative**
- Consumption plan has a cold-start penalty (~200–500 ms) after periods of inactivity
- Python 3.13 support on Azure Functions should be verified at deploy time (Functions runtime may lag behind latest Python)
- Function Key rotation requires updating the Orchestrator's environment variable (`MCP_FUNCTION_KEY`)
