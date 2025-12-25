"""REST API routes for Reachy Agent dashboard.

Provides endpoints for:
- Sending prompts to the agent
- Getting robot and agent status
- Viewing conversation history
- Managing audit logs
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["api"])


class PromptRequest(BaseModel):
    """Request model for sending a prompt."""

    message: str
    """The message to send to the agent."""


class PromptResponse(BaseModel):
    """Response model for prompt results."""

    response: str
    """The agent's response."""

    turn_number: int
    """The conversation turn number."""

    timestamp: str
    """ISO timestamp of the response."""


class StatusResponse(BaseModel):
    """Response model for status endpoint."""

    agent_connected: bool
    """Whether an agent loop is connected."""

    robot_connected: bool
    """Whether the robot daemon is reachable."""

    daemon_url: str
    """URL of the robot daemon."""

    turn_count: int
    """Number of conversation turns."""

    history_count: int
    """Number of messages in history."""

    robot_status: dict[str, Any] | None
    """Robot status from daemon, if available."""


@router.post("/prompt", response_model=PromptResponse)
async def send_prompt(request: Request, body: PromptRequest) -> PromptResponse:
    """Send a prompt to the agent.

    Args:
        request: FastAPI request with app state.
        body: The prompt request body.

    Returns:
        The agent's response.

    Raises:
        HTTPException: If no agent is configured.
    """
    state = request.app.state.dashboard

    # Increment turn count
    state.turn_count += 1
    timestamp = datetime.now().isoformat()

    # Add to history
    state.conversation_history.append({
        "role": "user",
        "content": body.message,
        "timestamp": timestamp,
    })

    # Process prompt
    try:
        if state.agent_loop is not None:
            # Use agent loop
            result = await state.agent_loop.process_input(body.message)
            response_text = result.text if result.success else f"Error: {result.error}"
        else:
            # Demo mode - echo back
            response_text = (
                f"[Demo Mode] Received your message: '{body.message}'\n\n"
                "No agent is connected. To use full functionality, "
                "start with an agent loop configured."
            )

    except Exception as e:
        log.exception("Error processing prompt")
        response_text = f"Error processing prompt: {e}"

    # Add response to history
    response_timestamp = datetime.now().isoformat()
    state.conversation_history.append({
        "role": "assistant",
        "content": response_text,
        "timestamp": response_timestamp,
    })

    # Broadcast response via WebSocket
    await state.permission_handler.broadcast_agent_response(
        text=response_text,
        turn_number=state.turn_count,
    )

    return PromptResponse(
        response=response_text,
        turn_number=state.turn_count,
        timestamp=response_timestamp,
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(request: Request) -> StatusResponse:
    """Get current agent and robot status.

    Args:
        request: FastAPI request with app state.

    Returns:
        Current status information.
    """
    state = request.app.state.dashboard

    # Check robot daemon status
    robot_status = None
    robot_connected = False

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{state.daemon_url}/api/daemon/status",
                timeout=2.0,
            )
            if response.status_code == 200:
                robot_status = response.json()
                robot_connected = True
    except Exception as e:
        log.debug("Failed to get robot status", error=str(e))

    return StatusResponse(
        agent_connected=state.agent_loop is not None,
        robot_connected=robot_connected,
        daemon_url=state.daemon_url,
        turn_count=state.turn_count,
        history_count=len(state.conversation_history),
        robot_status=robot_status,
    )


@router.get("/history")
async def get_history(
    request: Request,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Get conversation history.

    Args:
        request: FastAPI request with app state.
        limit: Maximum number of messages to return.
        offset: Number of messages to skip.

    Returns:
        Conversation history with pagination info.
    """
    state = request.app.state.dashboard

    total = len(state.conversation_history)
    messages = state.conversation_history[offset : offset + limit]

    return {
        "messages": messages,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/history")
async def clear_history(request: Request) -> dict[str, str]:
    """Clear conversation history.

    Args:
        request: FastAPI request with app state.

    Returns:
        Success message.
    """
    state = request.app.state.dashboard

    old_count = len(state.conversation_history)
    state.conversation_history.clear()
    state.turn_count = 0

    log.info("Cleared conversation history", message_count=old_count)

    return {"message": f"Cleared {old_count} messages"}


@router.get("/audit")
async def get_audit_logs(
    request: Request,
    limit: int = 100,
    tool_name: str | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    """Get audit logs.

    Args:
        request: FastAPI request with app state.
        limit: Maximum number of records to return.
        tool_name: Optional filter by tool name.
        decision: Optional filter by decision.

    Returns:
        Audit records with filters applied.
    """
    state = request.app.state.dashboard

    records = await state.audit_storage.get_recent(
        limit=limit,
        tool_name=tool_name,
        decision=decision,
    )

    return {
        "records": [r.to_dict() for r in records],
        "count": len(records),
    }


@router.get("/camera/frame")
async def get_camera_frame(request: Request) -> dict[str, str]:
    """Get camera frame URL for proxying.

    This endpoint returns the URL to fetch camera frames from.
    The frontend can use this to poll for video frames.

    Args:
        request: FastAPI request with app state.

    Returns:
        URL info for camera access.
    """
    state = request.app.state.dashboard

    return {
        "frame_url": f"{state.daemon_url}/camera/capture",
        "stream_url": f"{state.daemon_url}/camera/stream",
        "daemon_url": state.daemon_url,
    }
