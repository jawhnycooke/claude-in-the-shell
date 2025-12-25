"""WebSocket-based permission handler for web dashboard.

Provides confirmation prompts and notifications via WebSocket
for integration with browser-based interfaces.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable
from uuid import uuid4

from reachy_agent.permissions.handlers.base import PermissionHandler
from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


class WebSocketPermissionHandler(PermissionHandler):
    """WebSocket-based permission handler for web dashboard.

    Sends confirmation requests and notifications to connected
    WebSocket clients and handles their responses.

    Features:
    - Broadcasts to all connected clients
    - Tracks pending confirmations with asyncio.Future
    - Timeout handling with automatic denial
    - JSON message protocol for easy client integration

    Message Protocol:
    - confirmation_request: Ask user for approval
    - confirmation_timeout: Notify that confirmation timed out
    - notification: Inform user about action
    - error: Display error message
    - tool_start: Tool execution started
    - tool_complete: Tool execution finished

    Example:
        ```python
        handler = WebSocketPermissionHandler()

        # In WebSocket endpoint:
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            handler.register_client(websocket)

            try:
                while True:
                    data = await websocket.receive_json()
                    if data["type"] == "confirmation_response":
                        await handler.handle_confirmation_response(
                            data["request_id"],
                            data["approved"],
                        )
            finally:
                handler.unregister_client(websocket)
        ```

    Attributes:
        on_broadcast: Optional callback for outgoing messages.
    """

    def __init__(
        self,
        on_broadcast: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        """Initialize WebSocket permission handler.

        Args:
            on_broadcast: Optional callback for outgoing messages.
                         Called with message dict for each broadcast.
        """
        self._connected_clients: list[Any] = []
        self._pending_confirmations: dict[str, asyncio.Future[bool]] = {}
        self._on_broadcast = on_broadcast

    def register_client(self, websocket: Any) -> None:
        """Register a WebSocket client for broadcasts.

        Args:
            websocket: The WebSocket connection to register.
        """
        if websocket not in self._connected_clients:
            self._connected_clients.append(websocket)
            log.debug(
                "WebSocket client registered",
                total_clients=len(self._connected_clients),
            )

    def unregister_client(self, websocket: Any) -> None:
        """Unregister a WebSocket client.

        Args:
            websocket: The WebSocket connection to unregister.
        """
        if websocket in self._connected_clients:
            self._connected_clients.remove(websocket)
            log.debug(
                "WebSocket client unregistered",
                total_clients=len(self._connected_clients),
            )

    @property
    def connected_client_count(self) -> int:
        """Return number of connected clients."""
        return len(self._connected_clients)

    async def _broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast message to all connected clients.

        Args:
            message: Message dictionary to send.
        """
        data = json.dumps(message)

        # Call optional broadcast callback
        if self._on_broadcast:
            try:
                result = self._on_broadcast(message)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.warning("Broadcast callback failed", error=str(e))

        # Send to all connected WebSocket clients
        disconnected = []
        for client in self._connected_clients:
            try:
                await client.send_text(data)
            except Exception:
                disconnected.append(client)

        # Clean up disconnected clients
        for client in disconnected:
            self._connected_clients.remove(client)

        if disconnected:
            log.debug(
                "Removed disconnected clients",
                removed=len(disconnected),
                remaining=len(self._connected_clients),
            )

    async def request_confirmation(
        self,
        tool_name: str,
        reason: str,
        tool_input: dict[str, Any],
        timeout_seconds: float = 60.0,
    ) -> bool:
        """Request confirmation via WebSocket.

        Broadcasts a confirmation request to all connected clients
        and waits for a response.

        Args:
            tool_name: Name of the tool requiring confirmation.
            reason: Human-readable explanation.
            tool_input: Tool parameters to display.
            timeout_seconds: Maximum wait time.

        Returns:
            True if user confirmed, False if denied or timeout.
        """
        request_id = str(uuid4())

        # Create future for response
        future: asyncio.Future[bool] = asyncio.Future()
        self._pending_confirmations[request_id] = future

        # Broadcast confirmation request
        await self._broadcast({
            "type": "confirmation_request",
            "request_id": request_id,
            "tool_name": tool_name,
            "reason": reason,
            "tool_input": tool_input,
            "timeout_seconds": timeout_seconds,
        })

        log.debug(
            "Sent confirmation request",
            request_id=request_id,
            tool_name=tool_name,
        )

        try:
            result = await asyncio.wait_for(future, timeout=timeout_seconds)
            log.info(
                "Confirmation response received",
                request_id=request_id,
                approved=result,
            )
            return result

        except asyncio.TimeoutError:
            # Notify clients of timeout
            await self._broadcast({
                "type": "confirmation_timeout",
                "request_id": request_id,
                "tool_name": tool_name,
            })

            log.warning(
                "Confirmation timed out",
                request_id=request_id,
                tool_name=tool_name,
                timeout_seconds=timeout_seconds,
            )
            return False

        finally:
            # Clean up pending confirmation
            self._pending_confirmations.pop(request_id, None)

    async def handle_confirmation_response(
        self,
        request_id: str,
        approved: bool,
    ) -> bool:
        """Handle confirmation response from client.

        Called when a client sends a confirmation_response message.

        Args:
            request_id: ID of the confirmation request.
            approved: Whether the user approved the action.

        Returns:
            True if the request was found and handled.
        """
        future = self._pending_confirmations.get(request_id)

        if future and not future.done():
            future.set_result(approved)
            log.debug(
                "Handled confirmation response",
                request_id=request_id,
                approved=approved,
            )
            return True

        log.warning(
            "Confirmation response for unknown request",
            request_id=request_id,
        )
        return False

    async def notify(
        self,
        tool_name: str,
        message: str,
        tier: int = 2,
    ) -> None:
        """Send notification via WebSocket.

        Args:
            tool_name: Name of the tool that was executed.
            message: Notification message.
            tier: Permission tier for styling.
        """
        await self._broadcast({
            "type": "notification",
            "tool_name": tool_name,
            "message": message,
            "tier": tier,
        })

        log.debug(
            "Sent notification",
            tool_name=tool_name,
            tier=tier,
        )

    async def display_error(
        self,
        tool_name: str,
        error: str,
        code: str | None = None,
    ) -> None:
        """Send error message via WebSocket.

        Args:
            tool_name: Name of the tool that caused the error.
            error: Error message.
            code: Optional error code.
        """
        await self._broadcast({
            "type": "error",
            "tool_name": tool_name,
            "error": error,
            "code": code,
        })

        log.debug(
            "Sent error",
            tool_name=tool_name,
            error=error,
            code=code,
        )

    async def on_tool_start(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """Broadcast tool execution start.

        Args:
            tool_name: Name of the tool being executed.
            tool_input: The tool's input parameters.
        """
        await self._broadcast({
            "type": "tool_start",
            "tool_name": tool_name,
            "tool_input": tool_input,
        })

    async def on_tool_complete(
        self,
        tool_name: str,
        result: Any,
        duration_ms: int,
    ) -> None:
        """Broadcast tool execution completion.

        Args:
            tool_name: Name of the completed tool.
            result: The tool's return value (may be truncated).
            duration_ms: Execution time in milliseconds.
        """
        # Serialize result, truncating if too large
        try:
            result_str = json.dumps(result)
            if len(result_str) > 1000:
                result_str = result_str[:997] + "..."
            serialized_result = json.loads(result_str)
        except (TypeError, ValueError):
            serialized_result = str(result)[:1000]

        await self._broadcast({
            "type": "tool_complete",
            "tool_name": tool_name,
            "result": serialized_result,
            "duration_ms": duration_ms,
        })

    async def broadcast_agent_response(
        self,
        text: str,
        turn_number: int,
    ) -> None:
        """Broadcast an agent response to all clients.

        Utility method for sending agent responses through WebSocket.

        Args:
            text: The agent's response text.
            turn_number: The conversation turn number.
        """
        await self._broadcast({
            "type": "agent_response",
            "text": text,
            "turn_number": turn_number,
        })

    async def broadcast_status_update(
        self,
        status: dict[str, Any],
    ) -> None:
        """Broadcast a status update to all clients.

        Utility method for sending robot/agent status updates.

        Args:
            status: Status dictionary with agent state info.
        """
        await self._broadcast({
            "type": "status_update",
            "status": status,
        })
