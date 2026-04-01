# ADR-005: Session management — InMemorySessionService for MVP, Azure Storage Table for Phase 2

- **Status**: Accepted
- **Date**: 2026-03-30

## Context

The Orchestrator must maintain multi-turn conversation history so that users can ask follow-up questions ("How does that compare to last week?") and receive contextually aware responses.

Requirements:

1. Each conversation is identified by a `session_id` (UUID) provided by the client
2. The Orchestrator must be able to retrieve, append to, and delete sessions
3. In Phase 2, the Orchestrator will run as multiple instances on Azure App Service, so session state must be shared across instances

Google ADK provides a `BaseSessionService` interface and a built-in `InMemorySessionService` implementation.

## Decision

**MVP (Phase 1)**: Use `InMemorySessionService` from `google.adk.sessions`

- Zero configuration; no external dependencies
- Sufficient for single-instance local development and initial production deployment
- Known limitation: state is lost on process restart and not shared across instances

**Phase 2**: Replace with a custom `StorageTableSessionService(BaseSessionService)`

- Extends `BaseSessionService` and overrides `create_session`, `get_session`, `update_session`, `delete_session`
- Stores sessions in **Azure Storage Table** with the following schema:
  - `PartitionKey`: `{app_name}_{user_id}` — enables efficient per-user history scans
  - `RowKey`: `session_id` (UUID)
  - `events`: JSON-serialised list of ADK `Event` objects (`model_dump` / `model_validate`)
  - `state`: JSON-serialised session state dict
  - `updated_at`: ISO 8601 timestamp

The swap is a one-line change in `orchestrator/runner.py` — only the `SessionService` constructor changes; all call sites remain identical.

## Alternatives Considered

| Option | Reason rejected |
|--------|----------------|
| Redis | Requires additional managed service; higher cost and operational overhead for MVP |
| Azure Cosmos DB | More powerful than needed for simple key-value session storage; higher cost |
| PostgreSQL / Azure SQL | Relational model adds unnecessary complexity for document-style session events |
| Sticky sessions (App Service ARR affinity) | Fragile; breaks on scale-in or instance restart; not a real persistence solution |

## Consequences

**Positive**
- MVP ships with zero infrastructure dependencies for session storage
- The `BaseSessionService` interface enforces a clean contract; Phase 2 migration is isolated to one file
- Azure Storage Table is low-cost, serverless, and natively integrated with Azure Managed Identity

**Negative**
- MVP sessions are ephemeral — a process restart (e.g., App Service deployment) loses all active conversations
- Serialising ADK `Event` objects via `model_dump` creates a coupling to ADK's internal Pydantic schema; ADK upgrades may require a migration
- Storage Table has a 1 MB entity size limit; very long conversations may hit this ceiling (mitigated by truncating old events if needed)
