"""WebSocket routes for Reachy Agent dashboard.

Handles real-time communication for:
- Permission confirmation requests/responses
- Tool execution notifications
- Status updates
- Agent responses
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time dashboard communication.

    Handles bidirectional communication for:
    - Confirmation responses from the client
    - Broadcasts from the permission handler
    - Status updates

    Message Protocol:
    - Client → Server:
        - confirmation_response: {type, request_id, approved}
        - ping: {type: "ping"}

    - Server → Client:
        - confirmation_request: {type, request_id, tool_name, reason, tool_input}
        - confirmation_timeout: {type, request_id, tool_name}
        - notification: {type, tool_name, message, tier}
        - error: {type, tool_name, error, code}
        - tool_start: {type, tool_name, tool_input}
        - tool_complete: {type, tool_name, result, duration_ms}
        - agent_response: {type, text, turn_number}
        - status_update: {type, status}
        - pong: {type: "pong"}

    Args:
        websocket: The WebSocket connection.
    """
    await websocket.accept()

    # Get dashboard state
    state = websocket.app.state.dashboard
    handler = state.permission_handler

    # Register this client for broadcasts
    handler.register_client(websocket)

    client_id = id(websocket)
    log.info(
        "WebSocket client connected",
        client_id=client_id,
        total_clients=handler.connected_client_count,
    )

    try:
        # Send initial status
        await _send_initial_status(websocket, state)

        # Message loop
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await _handle_message(websocket, message, handler)

            except json.JSONDecodeError:
                log.warning("Invalid JSON received", data=data[:100])
                await websocket.send_json({
                    "type": "error",
                    "error": "Invalid JSON",
                })

    except WebSocketDisconnect:
        log.info(
            "WebSocket client disconnected",
            client_id=client_id,
        )

    except Exception as e:
        log.exception("WebSocket error", client_id=client_id)

    finally:
        # Unregister client
        handler.unregister_client(websocket)


async def _send_initial_status(websocket: WebSocket, state: Any) -> None:
    """Send initial status to newly connected client.

    Args:
        websocket: The WebSocket connection.
        state: Dashboard state.
    """
    import httpx

    # Get robot status
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
    except Exception:
        pass

    await websocket.send_json({
        "type": "status_update",
        "status": {
            "agent_connected": state.agent_loop is not None,
            "robot_connected": robot_connected,
            "turn_count": state.turn_count,
            "history_count": len(state.conversation_history),
            "robot_status": robot_status,
        },
    })

    # Send recent history
    if state.conversation_history:
        await websocket.send_json({
            "type": "history",
            "messages": state.conversation_history[-20:],
        })


async def _handle_message(
    websocket: WebSocket,
    message: dict[str, Any],
    handler: Any,
) -> None:
    """Handle incoming WebSocket message.

    Args:
        websocket: The WebSocket connection.
        message: The parsed message.
        handler: The permission handler.
    """
    msg_type = message.get("type")

    if msg_type == "ping":
        await websocket.send_json({"type": "pong"})

    elif msg_type == "confirmation_response":
        # Handle confirmation response
        request_id = message.get("request_id")
        approved = message.get("approved", False)

        if request_id:
            handled = await handler.handle_confirmation_response(
                request_id=request_id,
                approved=approved,
            )

            if handled:
                log.info(
                    "Processed confirmation response",
                    request_id=request_id,
                    approved=approved,
                )
            else:
                log.warning(
                    "Unknown confirmation request",
                    request_id=request_id,
                )

    elif msg_type == "prompt":
        # Handle prompt from WebSocket (alternative to REST)
        prompt_text = message.get("text", "")
        if prompt_text:
            # Forward to state for processing
            state = websocket.app.state.dashboard
            await _process_prompt(websocket, state, prompt_text)

    else:
        log.debug("Unknown message type", type=msg_type)


async def _process_prompt(
    websocket: WebSocket,
    state: Any,
    prompt: str,
) -> None:
    """Process a prompt received via WebSocket.

    Args:
        websocket: The WebSocket connection.
        state: Dashboard state.
        prompt: The prompt text.
    """
    from datetime import datetime

    # Increment turn count
    state.turn_count += 1
    timestamp = datetime.now().isoformat()

    # Add to history
    state.conversation_history.append({
        "role": "user",
        "content": prompt,
        "timestamp": timestamp,
    })

    # Broadcast that we received the prompt
    await websocket.send_json({
        "type": "prompt_received",
        "turn_number": state.turn_count,
    })

    # Process prompt
    try:
        if state.agent_loop is not None:
            result = await state.agent_loop.process_input(prompt)
            response_text = result.text if result.success else f"Error: {result.error}"
        else:
            response_text = (
                f"[Demo Mode] Received: '{prompt}'\n\n"
                "No agent configured."
            )

    except Exception as e:
        log.exception("Error processing WebSocket prompt")
        response_text = f"Error: {e}"

    # Add response to history
    response_timestamp = datetime.now().isoformat()
    state.conversation_history.append({
        "role": "assistant",
        "content": response_text,
        "timestamp": response_timestamp,
    })

    # Broadcast response to all clients
    await state.permission_handler.broadcast_agent_response(
        text=response_text,
        turn_number=state.turn_count,
    )
