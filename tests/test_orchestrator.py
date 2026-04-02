"""Unit tests for Orchestrator FastAPI endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch runner and config before importing app
_MOCK_SESSION_ID = str(uuid.uuid4())
_MOCK_REPLY = "## Active Alerts\nNo active alerts."
_MOCK_TOOL_CALLS = ["get_alerts"]


@pytest.fixture()
def skip_auth(monkeypatch):
    monkeypatch.setenv("SKIP_AUTH", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:7071/mcp")


@pytest.fixture()
def client(skip_auth):
    with patch("orchestrator.runner.build_agent"), \
         patch("orchestrator.runner._runner"), \
         patch("orchestrator.config.OrchestratorConfig", autospec=True):
        from orchestrator.main import app
        return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def mock_run():
    with patch(
        "orchestrator.runner.run",
        new_callable=AsyncMock,
        return_value=(_MOCK_REPLY, _MOCK_TOOL_CALLS),
    ) as m:
        yield m


@pytest.fixture()
def mock_create_session():
    with patch(
        "orchestrator.runner.create_session",
        new_callable=AsyncMock,
        return_value=_MOCK_SESSION_ID,
    ) as m:
        yield m


@pytest.fixture()
def mock_get_session_messages():
    with patch(
        "orchestrator.runner.get_session_messages",
        new_callable=AsyncMock,
        return_value=[
            {
                "role": "user",
                "content": "hello",
                "timestamp": "2026-04-01T09:00:00+00:00",
                "tool_calls": [],
            }
        ],
    ) as m:
        yield m


@pytest.fixture()
def mock_delete_session():
    with patch(
        "orchestrator.runner.delete_session",
        new_callable=AsyncMock,
    ) as m:
        yield m


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


class TestChat:
    def test_returns_200_with_reply(self, client, mock_run, mock_create_session):
        resp = client.post("/chat", json={"message": "Show active alerts"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == _MOCK_REPLY
        assert body["tool_calls"] == _MOCK_TOOL_CALLS
        assert "session_id" in body

    def test_uses_provided_session_id(self, client, mock_run):
        sid = str(uuid.uuid4())
        with patch("orchestrator.runner.get_session_messages", new_callable=AsyncMock, return_value=[]):
            resp = client.post("/chat", json={"message": "hello", "session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

    def test_400_on_empty_message(self, client):
        resp = client.post("/chat", json={"message": "   "})
        assert resp.status_code == 422  # Pydantic validation

    def test_400_on_missing_message(self, client):
        resp = client.post("/chat", json={})
        assert resp.status_code == 422

    def test_401_without_token(self, monkeypatch):
        monkeypatch.setenv("SKIP_AUTH", "false")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setenv("MCP_SERVER_URL", "http://localhost:7071/mcp")
        monkeypatch.setenv("ENTRA_TENANT_ID", "fake-tenant")
        monkeypatch.setenv("ENTRA_APP_CLIENT_ID", "fake-client")
        with patch("orchestrator.runner.build_agent"), \
             patch("orchestrator.runner._runner"):
            from orchestrator.main import app
            c = TestClient(app, raise_server_exceptions=False)
        resp = c.post("/chat", json={"message": "hello"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /chat/history/{session_id}
# ---------------------------------------------------------------------------


class TestGetHistory:
    def test_200_with_existing_session(self, client, mock_get_session_messages):
        sid = str(uuid.uuid4())
        resp = client.get(f"/chat/history/{sid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == sid
        assert isinstance(body["messages"], list)

    def test_404_with_unknown_session(self, client):
        with patch("orchestrator.runner.get_session_messages", new_callable=AsyncMock, return_value=None):
            resp = client.get(f"/chat/history/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_code"] == "SESSION_NOT_FOUND"


# ---------------------------------------------------------------------------
# DELETE /chat/session/{session_id}
# ---------------------------------------------------------------------------


class TestDeleteSession:
    def test_204_for_existing_session(self, client, mock_delete_session):
        resp = client.delete(f"/chat/session/{uuid.uuid4()}")
        assert resp.status_code == 204

    def test_204_for_nonexistent_session(self, client, mock_delete_session):
        # delete_session is a no-op for missing sessions — still 204
        resp = client.delete(f"/chat/session/{uuid.uuid4()}")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_200_ok_when_mcp_reachable(self, client):
        import httpx as _httpx

        async def _mock_get(*args, **kwargs):
            return _httpx.Response(200)

        with patch("orchestrator.main.httpx.AsyncClient") as mock_cls:
            mock_async_client = AsyncMock()
            mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_async_client.__aexit__ = AsyncMock(return_value=False)
            mock_async_client.get = AsyncMock(return_value=_httpx.Response(200))
            mock_cls.return_value = mock_async_client

            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["mcp_server"] == "reachable"
        assert body["version"] == "0.1.0"

    def test_200_degraded_when_mcp_unreachable(self, client):
        import httpx as _httpx

        with patch("orchestrator.main.httpx.AsyncClient") as mock_cls:
            mock_async_client = AsyncMock()
            mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
            mock_async_client.__aexit__ = AsyncMock(return_value=False)
            mock_async_client.get = AsyncMock(side_effect=_httpx.ConnectError("refused"))
            mock_cls.return_value = mock_async_client

            resp = client.get("/health")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["mcp_server"] == "unreachable"
