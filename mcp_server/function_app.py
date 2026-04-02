"""MCP Server entry point.

Works as both a local FastMCP process and an Azure Functions HTTP trigger.

Local usage:
    USE_MOCK=true uv run python -m mcp_server.function_app

Azure Functions:
    The `azure_app` object is picked up automatically by the Functions runtime.
    Tools are exposed at the /mcp path via Streamable HTTP transport.
"""

import azure.functions as func
from fastmcp import FastMCP

from mcp_server.tools.alerts import get_alerts as _get_alerts
from mcp_server.tools.cost import get_cost_summary as _get_cost_summary

# ---------------------------------------------------------------------------
# FastMCP app
# ---------------------------------------------------------------------------

mcp = FastMCP("sre-agent-mcp")


@mcp.tool
def get_alerts(
    resource_group: str | None = None,
    severity: int | None = None,
) -> list[dict]:
    """Fetch active alerts from Azure Monitor.

    Args:
        resource_group: Filter by resource group name.
        severity: Filter by severity level (0=Critical, 1=Error, 2=Warning,
                  3=Informational, 4=Verbose).
    """
    return _get_alerts(resource_group=resource_group, severity=severity)


@mcp.tool
def get_cost_summary(period: str = "7d") -> dict:
    """Fetch cost summary from Azure Cost Management.

    Args:
        period: Aggregation period — "today", "7d", or "30d". Defaults to "7d".
    """
    return _get_cost_summary(period=period)


# ---------------------------------------------------------------------------
# Azure Functions HTTP trigger
# ---------------------------------------------------------------------------

azure_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@azure_app.route(route="mcp/{*route}")
async def mcp_trigger(
    req: func.HttpRequest, context: func.Context
) -> func.HttpResponse:
    asgi_app = mcp.http_app(path="/")
    return await func.AsgiMiddleware(asgi_app).handle_async(req, context)


# ---------------------------------------------------------------------------
# Local execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=7071)
