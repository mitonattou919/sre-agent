"""Entra ID JWT validation for FastAPI.

Validates Authorization: Bearer <token> on every request using python-jose
and the Entra ID JWKS endpoint. Bypassed when SKIP_AUTH=true.
"""

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from orchestrator.config import config

_bearer = HTTPBearer(auto_error=False)

_JWKS_URL = (
    f"https://login.microsoftonline.com/{config.entra_tenant_id}"
    "/discovery/v2.0/keys"
)

# Simple in-process JWKS cache (refreshed on first use per process lifetime)
_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is None:
        response = httpx.get(_JWKS_URL, timeout=10)
        response.raise_for_status()
        _jwks_cache = response.json()
    return _jwks_cache


def _validate_token(token: str) -> str:
    """Validate JWT and return user_id (oid claim)."""
    try:
        jwks = _get_jwks()
        audience = f"api://{config.entra_app_client_id}"
        claims = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=audience,
        )
    except JWTError as e:
        msg = str(e).lower()
        if "expired" in msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "AUTH_TOKEN_EXPIRED",
                    "message": "The access token has expired. Please run 'sre-agent login' to re-authenticate.",
                },
            )
        if "audience" in msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error_code": "AUTH_TOKEN_WRONG_AUDIENCE",
                    "message": "Token audience does not match this API.",
                },
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_TOKEN_INVALID",
                "message": "JWT signature verification failed.",
                "detail": str(e),
            },
        )

    user_id: str = claims.get("oid", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_TOKEN_INVALID",
                "message": "Token is missing the 'oid' claim.",
            },
        )
    return user_id


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency that returns user_id from the Bearer token.

    Returns "local" when SKIP_AUTH=true (local development only).
    """
    if config.skip_auth:
        return "local"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "AUTH_TOKEN_MISSING",
                "message": "Authorization header is missing.",
            },
        )

    return _validate_token(credentials.credentials)
