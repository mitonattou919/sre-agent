from google.adk.agents import LlmAgent

from orchestrator.mcp_client import build_mcp_toolset

_SYSTEM_PROMPT = """\
You are an SRE assistant for Azure environments.
Always format your responses in Markdown.
Adapt your response language to match the user's language.
When tool calls fail, relay the error message to the user in natural language.
"""


def build_agent() -> LlmAgent:
    """Create the LlmAgent with Gemini 2.5 Flash and MCP tools."""
    return LlmAgent(
        model="gemini-2.5-flash",
        name="sre-agent",
        description="SRE agent for Azure environments",
        instruction=_SYSTEM_PROMPT,
        tools=[build_mcp_toolset()],
    )
