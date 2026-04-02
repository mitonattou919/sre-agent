from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StreamableHTTPConnectionParams

from orchestrator.config import config


def build_mcp_toolset() -> MCPToolset:
    """Create an MCPToolset connected to the MCP Server via Streamable HTTP."""
    headers: dict[str, str] = {}
    if config.mcp_function_key:
        headers["x-functions-key"] = config.mcp_function_key

    return MCPToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=config.mcp_server_url,
            headers=headers,
        )
    )
