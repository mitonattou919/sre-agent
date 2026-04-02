"""ADK Runner with InMemorySessionService.

Single instance only for MVP. Replace InMemorySessionService with
StorageTableSessionService in Phase 2 before scaling to multiple instances.
"""

import uuid

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

from orchestrator.agent import build_agent

_APP_NAME = "sre-agent"

_session_service = InMemorySessionService()
_agent = build_agent()
_runner = Runner(
    agent=_agent,
    app_name=_APP_NAME,
    session_service=_session_service,
)


async def run(message: str, session_id: str, user_id: str) -> tuple[str, list[str]]:
    """Run the agent for a single turn.

    Args:
        message: User's input text.
        session_id: Session UUID string.
        user_id: User identifier (from JWT oid claim, or "local" in dev).

    Returns:
        Tuple of (reply_markdown, tool_calls) where tool_calls is an ordered
        list of MCP tool names called during this turn.
    """
    session = await _session_service.get_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
    if session is None:
        await _session_service.create_session(
            app_name=_APP_NAME, user_id=user_id, session_id=session_id
        )

    content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=message)],
    )

    reply_parts: list[str] = []
    tool_calls: list[str] = []

    async for event in _runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=content,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts or []:
                if part.text:
                    reply_parts.append(part.text)
        if event.get_function_calls():
            for fc in event.get_function_calls():
                tool_calls.append(fc.name)

    reply = "".join(reply_parts)
    return reply, tool_calls


async def create_session(user_id: str) -> str:
    """Create a new session and return its UUID string."""
    session_id = str(uuid.uuid4())
    await _session_service.create_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
    return session_id


async def get_session_messages(session_id: str, user_id: str) -> list[dict] | None:
    """Return serialised message history for a session, or None if not found."""
    session = await _session_service.get_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
    if session is None:
        return None

    messages: list[dict] = []
    for event in session.events or []:
        if not (event.content and event.content.parts):
            continue
        text = "".join(p.text for p in event.content.parts if p.text)
        if not text:
            continue
        tool_names = [fc.name for fc in (event.get_function_calls() or [])]
        messages.append(
            {
                "role": event.content.role,
                "content": text,
                "timestamp": event.timestamp.isoformat() if event.timestamp else "",
                "tool_calls": tool_names,
            }
        )
    return messages


async def delete_session(session_id: str, user_id: str) -> None:
    """Delete a session. No-op if the session does not exist."""
    await _session_service.delete_session(
        app_name=_APP_NAME, user_id=user_id, session_id=session_id
    )
