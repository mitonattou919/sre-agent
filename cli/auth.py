"""CLI authentication via Entra ID Device Code Flow.

Tokens are cached at ~/.sre-agent/token_cache and reused until expiry.
Bypassed when SKIP_AUTH=true.
"""

from cli.config import config


class TokenExpiredError(Exception):
    pass


def get_token() -> str | None:
    """Return a valid access token, or None when SKIP_AUTH=true."""
    if config.skip_auth:
        return None

    from azure.identity import DeviceCodeCredential
    from azure.identity._exceptions import CredentialUnavailableError

    cache_path = config.token_cache_path.expanduser()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from azure.identity.broker import TokenCachePersistenceOptions
        cache_opts = TokenCachePersistenceOptions(name="sre-agent")
    except ImportError:
        cache_opts = None  # type: ignore[assignment]

    kwargs: dict = dict(
        tenant_id=config.entra_tenant_id,
        client_id=config.entra_app_client_id,
    )
    if cache_opts is not None:
        kwargs["cache_persistence_options"] = cache_opts

    credential = DeviceCodeCredential(**kwargs)
    scope = f"api://{config.entra_app_client_id}/.default"

    try:
        token = credential.get_token(scope)
        return token.token
    except CredentialUnavailableError as e:
        raise TokenExpiredError(str(e)) from e


def login() -> None:
    """Authenticate interactively via Device Code Flow."""
    if config.skip_auth:
        print("Auth skipped (SKIP_AUTH=true)")
        return

    from azure.identity import DeviceCodeCredential

    cache_path = config.token_cache_path.expanduser()
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from azure.identity.broker import TokenCachePersistenceOptions
        cache_opts = TokenCachePersistenceOptions(name="sre-agent")
    except ImportError:
        cache_opts = None  # type: ignore[assignment]

    kwargs: dict = dict(
        tenant_id=config.entra_tenant_id,
        client_id=config.entra_app_client_id,
    )
    if cache_opts is not None:
        kwargs["cache_persistence_options"] = cache_opts

    credential = DeviceCodeCredential(**kwargs)
    scope = f"api://{config.entra_app_client_id}/.default"
    credential.get_token(scope)
    print(f"Authentication successful. Token cached at {cache_path}")
