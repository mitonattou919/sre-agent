# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for the SRE Agent project.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](001-three-tier-architecture.md) | Three-tier architecture: MCP Server / Orchestrator / CLI | Accepted |
| [ADR-002](002-google-adk-gemini.md) | Agent orchestration with Google ADK and Gemini 2.5 Flash | Accepted |
| [ADR-003](003-fastmcp-streamable-http.md) | MCP Server implementation with FastMCP and Streamable HTTP | Accepted |
| [ADR-004](004-mcp-server-deployment.md) | Deploy MCP Server on Azure Functions | Accepted |
| [ADR-005](005-session-management.md) | Session management: InMemorySessionService for MVP, Storage Table for Phase 2 | Accepted |
| [ADR-006](006-authentication.md) | Entra ID JWT for API auth, Device Code Flow for CLI | Accepted |

## Format

Each ADR follows this structure:

- **Status**: Proposed / Accepted / Deprecated / Superseded
- **Context**: Background and constraints that drove the decision
- **Decision**: The approach we chose
- **Alternatives considered**: Options we evaluated but did not adopt
- **Consequences**: Trade-offs and impact of this decision
