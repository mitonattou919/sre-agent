# ADR-006: Entra ID JWT for API auth, Device Code Flow for CLI

- **Status**: Accepted
- **Date**: 2026-03-30

## Context

The system has two authentication boundaries:

1. **CLI / Web UI → Orchestrator (FastAPI)**: Requests must be authenticated so that `user_id` can be derived server-side without trusting client-supplied values
2. **CLI → Entra ID**: The CLI runs in terminal environments (servers, CI) without a browser; the auth flow must work headlessly

Additionally, the MCP Server must access Azure APIs. This is handled separately via Managed Identity (see ADR-004) and is out of scope here.

The organisation already uses Microsoft Entra ID (Azure AD) as its identity provider.

## Decision

### API Authentication — Entra ID Bearer JWT

The FastAPI Orchestrator validates `Authorization: Bearer <token>` on every request using `python-jose` and the Entra ID JWKS endpoint:

```
JWKS URL: https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys
Algorithm: RS256
Audience:  api://{ENTRA_APP_CLIENT_ID}
```

- `user_id` is extracted from the `oid` (object ID) claim in the validated JWT — clients never send `user_id` explicitly
- A single **App Registration** is used for both CLI token issuance and API audience validation
- Auth can be bypassed in local development by setting `SKIP_AUTH=true`

### CLI Authentication — Device Code Flow

```python
from azure.identity import DeviceCodeCredential

credential = DeviceCodeCredential(
    tenant_id=settings.ENTRA_TENANT_ID,
    client_id=settings.ENTRA_APP_CLIENT_ID,
    cache_persistence_options=TokenCachePersistenceOptions(),
)
token = credential.get_token(f"api://{settings.ENTRA_APP_CLIENT_ID}/.default")
```

- Tokens are cached at `~/.sre-agent/token_cache` and reused until expiry
- The user authenticates once and subsequent CLI invocations use the cached token silently

## Alternatives Considered

| Option | Reason rejected |
|--------|----------------|
| API key (shared secret) | No per-user identity; key rotation is manual and error-prone |
| OAuth Authorization Code Flow | Requires a redirect URI and browser; does not work on headless servers |
| Client Credentials Flow | Issues tokens for an application identity, not a user identity; `user_id` per person would not be available |
| msal directly (instead of `azure-identity`) | `azure-identity` wraps msal with a simpler API and built-in token cache persistence |

## Consequences

**Positive**
- `user_id` is derived from a cryptographically verified JWT — no spoofing risk
- Device Code Flow works on headless machines and CI environments
- Token caching means users only authenticate interactively once per token lifetime (~1 hour for access tokens)
- `SKIP_AUTH=true` removes the need for any Entra setup during local development

**Negative**
- JWT validation requires fetching JWKS on startup (or caching it); network failure at startup could break the Orchestrator
- Device Code Flow has a 15-minute window to complete; automated pipelines must handle token expiry
- `python-jose` must be kept up to date; CVEs in JWT libraries are high-severity
- App Registration setup (audience, scope, redirect URIs) must be documented for new environments
