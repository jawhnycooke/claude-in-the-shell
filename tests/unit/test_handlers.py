"""Tests for permission handlers."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reachy_agent.permissions.handlers import (
    CLIPermissionHandler,
    PermissionHandler,
    WebSocketPermissionHandler,
)


class TestPermissionHandlerBase:
    """Tests for the base PermissionHandler interface."""

    def test_is_abstract(self) -> None:
        """Test that PermissionHandler cannot be instantiated directly."""
        with pytest.raises(TypeError):
            PermissionHandler()  # type: ignore

    def test_subclass_must_implement_methods(self) -> None:
        """Test that subclasses must implement abstract methods."""

        class IncompleteHandler(PermissionHandler):
            pass

        with pytest.raises(TypeError):
            IncompleteHandler()  # type: ignore


class TestCLIPermissionHandler:
    """Tests for CLIPermissionHandler."""

    def test_init(self) -> None:
        """Test handler initialization."""
        handler = CLIPermissionHandler()
        assert handler.console is not None

    def test_tier_colors(self) -> None:
        """Test tier color mapping."""
        assert CLIPermissionHandler.TIER_COLORS[1] == "green"
        assert CLIPermissionHandler.TIER_COLORS[2] == "blue"
        assert CLIPermissionHandler.TIER_COLORS[3] == "yellow"
        assert CLIPermissionHandler.TIER_COLORS[4] == "red"

    def test_tier_names(self) -> None:
        """Test tier name mapping."""
        assert CLIPermissionHandler.TIER_NAMES[1] == "Autonomous"
        assert CLIPermissionHandler.TIER_NAMES[2] == "Notify"
        assert CLIPermissionHandler.TIER_NAMES[3] == "Confirm"
        assert CLIPermissionHandler.TIER_NAMES[4] == "Forbidden"

    @pytest.mark.asyncio
    async def test_notify(self) -> None:
        """Test notification display."""
        mock_console = MagicMock()
        handler = CLIPermissionHandler(console=mock_console)

        await handler.notify(
            tool_name="mcp__test__action",
            message="Test notification",
            tier=2,
        )

        # Verify console.print was called
        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_display_error(self) -> None:
        """Test error display."""
        mock_console = MagicMock()
        handler = CLIPermissionHandler(console=mock_console)

        await handler.display_error(
            tool_name="mcp__test__action",
            error="Something went wrong",
            code="TEST_ERROR",
        )

        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_tool_start(self) -> None:
        """Test tool start notification."""
        mock_console = MagicMock()
        handler = CLIPermissionHandler(console=mock_console)

        await handler.on_tool_start(
            tool_name="mcp__test__action",
            tool_input={"key": "value"},
        )

        mock_console.print.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_tool_complete(self) -> None:
        """Test tool completion notification."""
        mock_console = MagicMock()
        handler = CLIPermissionHandler(console=mock_console)

        await handler.on_tool_complete(
            tool_name="mcp__test__action",
            result={"status": "success"},
            duration_ms=150,
        )

        mock_console.print.assert_called_once()


class TestWebSocketPermissionHandler:
    """Tests for WebSocketPermissionHandler."""

    def test_init(self) -> None:
        """Test handler initialization."""
        handler = WebSocketPermissionHandler()
        assert handler.connected_client_count == 0
        assert len(handler._pending_confirmations) == 0

    def test_register_client(self) -> None:
        """Test client registration."""
        handler = WebSocketPermissionHandler()
        mock_ws = MagicMock()

        handler.register_client(mock_ws)
        assert handler.connected_client_count == 1

        # Registering same client again should not duplicate
        handler.register_client(mock_ws)
        assert handler.connected_client_count == 1

    def test_unregister_client(self) -> None:
        """Test client unregistration."""
        handler = WebSocketPermissionHandler()
        mock_ws = MagicMock()

        handler.register_client(mock_ws)
        assert handler.connected_client_count == 1

        handler.unregister_client(mock_ws)
        assert handler.connected_client_count == 0

        # Unregistering non-existent client should not error
        handler.unregister_client(mock_ws)
        assert handler.connected_client_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_with_callback(self) -> None:
        """Test broadcast with callback."""
        callback = AsyncMock()
        handler = WebSocketPermissionHandler(on_broadcast=callback)

        await handler._broadcast({"type": "test", "data": "value"})

        callback.assert_called_once_with({"type": "test", "data": "value"})

    @pytest.mark.asyncio
    async def test_broadcast_to_clients(self) -> None:
        """Test broadcast to connected clients."""
        handler = WebSocketPermissionHandler()

        mock_ws = AsyncMock()
        handler.register_client(mock_ws)

        await handler._broadcast({"type": "test"})

        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_removes_disconnected_clients(self) -> None:
        """Test that disconnected clients are removed."""
        handler = WebSocketPermissionHandler()

        # Create a mock that raises on send
        mock_ws = AsyncMock()
        mock_ws.send_text.side_effect = Exception("Disconnected")
        handler.register_client(mock_ws)

        assert handler.connected_client_count == 1

        await handler._broadcast({"type": "test"})

        # Client should be removed after failed send
        assert handler.connected_client_count == 0

    @pytest.mark.asyncio
    async def test_handle_confirmation_response(self) -> None:
        """Test confirmation response handling."""
        handler = WebSocketPermissionHandler()

        # Create a pending confirmation
        request_id = "test-request-123"
        future: asyncio.Future[bool] = asyncio.Future()
        handler._pending_confirmations[request_id] = future

        # Handle the response
        result = await handler.handle_confirmation_response(request_id, approved=True)

        assert result is True
        assert future.result() is True

    @pytest.mark.asyncio
    async def test_handle_unknown_confirmation(self) -> None:
        """Test handling response for unknown request."""
        handler = WebSocketPermissionHandler()

        result = await handler.handle_confirmation_response(
            "unknown-request",
            approved=True,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_notify(self) -> None:
        """Test notification broadcast."""
        handler = WebSocketPermissionHandler()
        mock_ws = AsyncMock()
        handler.register_client(mock_ws)

        await handler.notify(
            tool_name="mcp__test__action",
            message="Test message",
            tier=2,
        )

        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_display_error(self) -> None:
        """Test error broadcast."""
        handler = WebSocketPermissionHandler()
        mock_ws = AsyncMock()
        handler.register_client(mock_ws)

        await handler.display_error(
            tool_name="mcp__test__action",
            error="Test error",
            code="ERR_001",
        )

        mock_ws.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_agent_response(self) -> None:
        """Test agent response broadcast."""
        handler = WebSocketPermissionHandler()
        mock_ws = AsyncMock()
        handler.register_client(mock_ws)

        await handler.broadcast_agent_response(
            text="Hello, world!",
            turn_number=1,
        )

        mock_ws.send_text.assert_called_once()
