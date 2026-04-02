"""FastAPI application for the SRE Agent Orchestrator."""

import uuid
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import Response
from pydantic import UUID4, BaseModel, field_validator

from orchestrator import runner
from orchestrator.auth import get_current_user
from orchestrator.config import config

app = FastAPI(title="SRE Agent Orchestrator", version="0.1.0")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    session_id: UUID4 | None = None

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty or whitespace only")
        return v


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID4
    tool_calls: list[str] = []


class Message(BaseModel):
    role: str
    content: str
    timestamp: str
    tool_calls: list[str] = []


class HistoryResponse(BaseModel):
    session_id: UUID4
    messages: list[Message]
    created_at: datetime
    updated_at: datetime


class HealthResponse(BaseModel):
    status: str
    mcp_server: str
    version: str
    timestamp: datetime


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: str | None = None
    request_id: UUID4 | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user),
) -> ChatResponse:
    session_id_str: str
    if req.session_id is None:
        session_id_str = await runner.create_session(user_id)
    else:
        session_id_str = str(req.session_id)

    try:
        reply, tool_calls = await runner.run(
            message=req.message,
            session_id=session_id_str,
            user_id=user_id,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "INTERNAL_UNEXPECTED_ERROR",
                "message": "An unexpected error occurred.",
                "detail": str(e),
            },
        )

    return ChatResponse(
        reply=reply,
        session_id=uuid.UUID(session_id_str),
        tool_calls=tool_calls,
    )


@app.get("/chat/history/{session_id}", response_model=HistoryResponse)
async def get_history(
    session_id: UUID4,
    user_id: str = Depends(get_current_user),
) -> HistoryResponse:
    messages = await runner.get_session_messages(str(session_id), user_id)
    if messages is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Session {session_id} not found.",
            },
        )

    now = datetime.now(timezone.utc)
    return HistoryResponse(
        session_id=session_id,
        messages=[Message(**m) for m in messages],
        created_at=now,
        updated_at=now,
    )


@app.delete("/chat/session/{session_id}", status_code=204)
async def delete_session(
    session_id: UUID4,
    user_id: str = Depends(get_current_user),
) -> Response:
    await runner.delete_session(str(session_id), user_id)
    return Response(status_code=204)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    mcp_status = "reachable"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(config.mcp_server_url)
    except Exception:
        mcp_status = "unreachable"

    overall = "ok" if mcp_status == "reachable" else "degraded"
    return HealthResponse(
        status=overall,
        mcp_server=mcp_status,
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
    )
