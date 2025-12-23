"""Unit tests for the Reachy MCP server."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reachy_agent.mcp_servers.reachy.daemon_client import (
    ReachyDaemonClient,
    ReachyDaemonError,
)
from reachy_agent.mcp_servers.reachy.server import create_reachy_mcp_server


class TestReachyDaemonClient:
    """Tests for ReachyDaemonClient."""

    @pytest.fixture
    def client(self) -> ReachyDaemonClient:
        """Create a daemon client for testing."""
        return ReachyDaemonClient(base_url="http://localhost:8000")

    @pytest.mark.asyncio
    async def test_health_check_success(self, client: ReachyDaemonClient) -> None:
        """Test successful health check."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "healthy"}

            result = await client.health_check()

            assert result["status"] == "healthy"
            mock_request.assert_called_once_with("GET", "/health")

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client: ReachyDaemonClient) -> None:
        """Test health check when daemon is unreachable."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = ReachyDaemonError("Connection failed")

            result = await client.health_check()

            assert result["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_move_head(self, client: ReachyDaemonClient) -> None:
        """Test head movement command."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success"}

            result = await client.move_head(direction="left", speed="normal")

            assert result["status"] == "success"
            mock_request.assert_called_once_with(
                "POST",
                "/head/move",
                json_data={"direction": "left", "speed": "normal"},
            )

    @pytest.mark.asyncio
    async def test_move_head_with_degrees(self, client: ReachyDaemonClient) -> None:
        """Test head movement with specific angle."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success"}

            result = await client.move_head(
                direction="left", speed="slow", degrees=30.0
            )

            assert result["status"] == "success"
            mock_request.assert_called_once_with(
                "POST",
                "/head/move",
                json_data={"direction": "left", "speed": "slow", "degrees": 30.0},
            )

    @pytest.mark.asyncio
    async def test_speak(self, client: ReachyDaemonClient) -> None:
        """Test speech command."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success"}

            result = await client.speak(text="Hello world", speed=1.2)

            assert result["status"] == "success"
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_play_emotion(self, client: ReachyDaemonClient) -> None:
        """Test emotion expression."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success", "emotion": "happy"}

            result = await client.play_emotion(emotion="happy", intensity=0.8)

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_capture_image(self, client: ReachyDaemonClient) -> None:
        """Test image capture."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {
                "status": "success",
                "width": 640,
                "height": 480,
            }

            result = await client.capture_image(analyze=False)

            assert result["status"] == "success"
            assert result["width"] == 640

    @pytest.mark.asyncio
    async def test_set_antenna_state(self, client: ReachyDaemonClient) -> None:
        """Test antenna control."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success"}

            result = await client.set_antenna_state(
                left_angle=45.0, right_angle=60.0, wiggle=True
            )

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_dance(self, client: ReachyDaemonClient) -> None:
        """Test dance routine."""
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "success", "routine": "celebrate"}

            result = await client.dance(routine="celebrate", duration_seconds=5.0)

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_close_client(self, client: ReachyDaemonClient) -> None:
        """Test closing the HTTP client."""
        # Get the client first
        await client._get_client()
        assert client._client is not None

        # Close it
        await client.close()
        assert client._client is None


class TestReachyMCPServer:
    """Tests for the Reachy MCP server."""

    def test_server_creation(self) -> None:
        """Test creating the MCP server."""
        server = create_reachy_mcp_server()

        assert server is not None
        assert server.name == "Reachy Body Control"

    def test_server_with_custom_daemon_url(self) -> None:
        """Test creating server with custom daemon URL."""
        server = create_reachy_mcp_server(daemon_url="http://custom:9000")

        assert server is not None


class TestMCPToolValidation:
    """Tests for MCP tool input validation."""

    @pytest.fixture
    def server(self):
        """Create MCP server for testing."""
        return create_reachy_mcp_server()

    def _get_tool_func(self, server, tool_name: str):
        """Get a tool function from the server by name."""
        tools = server._tool_manager._tools
        if tool_name in tools:
            return tools[tool_name].fn
        return None

    @pytest.mark.asyncio
    async def test_move_head_invalid_direction(self, server) -> None:
        """Test move_head rejects invalid directions."""
        move_head = self._get_tool_func(server, "move_head")

        if move_head:
            result = await move_head(direction="invalid", speed="normal")
            assert "error" in result

    @pytest.mark.asyncio
    async def test_speak_text_length_limit(self, server) -> None:
        """Test speak rejects text over 500 characters."""
        speak = self._get_tool_func(server, "speak")

        if speak:
            long_text = "x" * 501
            result = await speak(text=long_text)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_antenna_angle_bounds(self, server) -> None:
        """Test antenna angles must be 0-90."""
        set_antenna = self._get_tool_func(server, "set_antenna_state")

        if set_antenna:
            result = await set_antenna(left_angle=100.0)
            assert "error" in result

    @pytest.mark.asyncio
    async def test_emotion_intensity_bounds(self, server) -> None:
        """Test emotion intensity must be 0.1-1.0."""
        play_emotion = self._get_tool_func(server, "play_emotion")

        if play_emotion:
            result = await play_emotion(emotion="happy", intensity=0.05)
            assert "error" in result
