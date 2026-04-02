"""httpx client wrapping all Orchestrator API calls."""

import sys
from uuid import UUID

import httpx

from cli.auth import TokenExpiredError, get_token
from cli.config import config


def _headers() -> dict[str, str]:
    token = get_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _handle_error(response: httpx.Response) -> None:
    if response.status_code == 401:
        try:
            code = response.json().get("detail", {}).get("error_code", "")
        except Exception:
            code = ""
        if code == "AUTH_TOKEN_EXPIRED":
            print("Error: Token expired. Run 'sre-agent login' to re-authenticate.", file=sys.stderr)
        else:
            print("Error: Authentication required. Run 'sre-agent login' to authenticate.", file=sys.stderr)
        sys.exit(1)

    if response.status_code == 502:
        print("Error: Azure tools are currently unavailable. (MCP_SERVER_UNREACHABLE)", file=sys.stderr)
        sys.exit(1)

    if response.status_code >= 500:
        try:
            code = response.json().get("detail", {}).get("error_code", "INTERNAL_UNEXPECTED_ERROR")
        except Exception:
            code = "INTERNAL_UNEXPECTED_ERROR"
        print(f"Error: Internal server error. ({code})", file=sys.stderr)
        sys.exit(1)

    response.raise_for_status()


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=config.orchestrator_url,
        headers=_headers(),
        timeout=60,
    )


def chat(message: str, session_id: str | None = None) -> dict:
    """POST /chat and return the response dict."""
    try:
        with _client() as client:
            payload: dict = {"message": message}
            if session_id:
                payload["session_id"] = session_id
            response = client.post("/chat", json=payload)
            _handle_error(response)
            return response.json()
    except TokenExpiredError:
        print("Error: Token expired. Run 'sre-agent login' to re-authenticate.", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print(
            f"Error: Cannot reach orchestrator at {config.orchestrator_url}. Check connection.",
            file=sys.stderr,
        )
        sys.exit(1)


def delete_session(session_id: str) -> None:
    """DELETE /chat/session/{session_id}."""
    try:
        with _client() as client:
            client.delete(f"/chat/session/{session_id}")
    except Exception:
        pass  # Best-effort cleanup on exit
