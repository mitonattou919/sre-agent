# ADR-002: Agent orchestration with Google ADK and Gemini 2.5 Flash

- **Status**: Accepted
- **Date**: 2026-03-30

## Context

The Orchestrator needs an LLM agent framework that can:

1. Invoke external tools (Azure Monitor, Cost Management) and incorporate their results into the response
2. Maintain multi-turn conversation history across requests
3. Support MCP as the tool transport protocol natively
4. Run inside a FastAPI process on Azure App Service (Python 3.13)

We also need to choose an LLM model. The key requirements are fast response time, low cost for operational queries, and sufficient reasoning ability for SRE tasks.

## Decision

**Framework**: Google ADK (`google-adk`) with `LlmAgent`

- ADK provides `MCPToolset` with first-class Streamable HTTP support, matching our MCP Server transport
- `InMemorySessionService` and the planned `BaseSessionService` extension point fit our phased session strategy (ADR-005)
- ADK's `Runner` handles the agent loop, session append, and tool dispatch without custom plumbing

**Model**: Gemini 2.5 Flash (fixed for MVP)

- Low latency for short operational queries
- Cost-effective for high-frequency CLI use
- Sufficient reasoning for alert triage and cost interpretation

The system prompt instructs the agent to:
- Adapt response language to the user's language
- Format all output in Markdown

## Alternatives Considered

| Option | Reason rejected |
|--------|----------------|
| LangChain | No native MCP toolset; heavier dependency footprint |
| LlamaIndex | Primary focus on RAG; MCP support is community-maintained |
| Direct Gemini API (no framework) | Would require hand-rolling tool dispatch, session management, and the agent loop |
| OpenAI GPT-4o | Google ADK is optimised for Gemini; cross-provider use adds complexity |
| Gemini 2.0 Flash | 2.5 Flash was available and offers improved reasoning at similar cost |

## Consequences

**Positive**
- `MCPToolset` and `StreamableHTTPConnectionParams` directly match our MCP Server design
- `BaseSessionService` extension point makes Phase 2 session migration straightforward
- Reduced boilerplate: ADK handles the agent loop, event logging, and tool result injection

**Negative**
- Locked into Google ADK's API surface and release cadence
- Gemini model is fixed for MVP — swapping to another model requires revisiting framework compatibility
- ADK is a relatively young SDK; breaking changes are possible between minor versions
