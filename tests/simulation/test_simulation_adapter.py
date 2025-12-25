"""Tests for the simulation adapter.

These tests verify that the simulation adapter correctly manages
the MuJoCo-based daemon and provides working MCP tool functionality.

Note: These tests require the reachy-mini[mujoco] package and may
take several seconds to run due to daemon startup time.
"""

from __future__ import annotations

import pytest

from reachy_agent.simulation import SimulationAdapter
from reachy_agent.simulation.adapter import create_simulation_adapter
from reachy_agent.simulation.daemon_launcher import SimulationConfig, SimulationScene


class TestSimulationConfig:
    """Test simulation configuration."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = SimulationConfig()

        assert config.scene == SimulationScene.EMPTY
        assert config.headless is False
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.startup_timeout == 30.0

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = SimulationConfig(
            scene=SimulationScene.MINIMAL,
            headless=True,
            port=9000,
        )

        assert config.scene == SimulationScene.MINIMAL
        assert config.headless is True
        assert config.port == 9000


class TestSimulationAdapterUnit:
    """Unit tests for SimulationAdapter (no daemon required)."""

    def test_adapter_creation(self) -> None:
        """Test adapter can be created."""
        adapter = SimulationAdapter()
        assert adapter.config.scene == SimulationScene.EMPTY
        assert not adapter.is_running

    def test_factory_function(self) -> None:
        """Test create_simulation_adapter factory."""
        adapter = create_simulation_adapter(
            scene="minimal",
            headless=True,
            port=9001,
        )

        assert adapter.config.scene == SimulationScene.MINIMAL
        assert adapter.config.headless is True
        assert adapter.config.port == 9001

    def test_base_url(self) -> None:
        """Test base URL generation."""
        config = SimulationConfig(host="localhost", port=8080)
        adapter = SimulationAdapter(config=config)

        assert adapter.base_url == "http://localhost:8080"

    def test_client_not_started_raises(self) -> None:
        """Test accessing client before start raises error."""
        adapter = SimulationAdapter()

        with pytest.raises(RuntimeError, match="not started"):
            _ = adapter.client


# Mark integration tests that require MuJoCo daemon
@pytest.mark.simulation
@pytest.mark.slow
class TestSimulationAdapterIntegration:
    """Integration tests that actually run the simulation.

    These tests are marked with @pytest.mark.simulation and @pytest.mark.slow.
    Skip with: pytest -m "not simulation" or pytest -m "not slow"

    Note: On macOS, these tests require running with 'mjpython' for GUI mode,
    or use headless=True for testing.
    """

    @pytest.fixture
    async def adapter(self):
        """Create and start a headless simulation adapter."""
        adapter = create_simulation_adapter(
            scene="empty",
            headless=True,
            port=8765,  # Use non-default port to avoid conflicts
        )
        async with adapter:
            yield adapter

    @pytest.mark.asyncio
    async def test_adapter_lifecycle(self) -> None:
        """Test adapter start and stop."""
        adapter = create_simulation_adapter(headless=True, port=8766)

        assert not adapter.is_running

        await adapter.start()
        try:
            assert adapter.is_running
            assert adapter.client is not None

            # Health check should return valid status
            health = await adapter.health_check()
            assert "state" in health or "status" in health
        finally:
            await adapter.stop()

        assert not adapter.is_running

    @pytest.mark.asyncio
    async def test_head_movement(self, adapter) -> None:
        """Test head movement through simulation."""
        client = adapter.client

        # Wake up first
        result = await client.wake_up()
        assert "status" in result or "uuid" in result

        # Move head
        result = await client.move_head("left", speed="normal")
        assert "status" in result or "message" in result or "uuid" in result

    @pytest.mark.asyncio
    async def test_antenna_control(self, adapter) -> None:
        """Test antenna control through simulation."""
        client = adapter.client

        result = await client.set_antenna_state(
            left_angle=45.0,
            right_angle=45.0,
        )
        # Daemon returns uuid on success, or error on failure
        assert "uuid" in result or "error" not in result

    @pytest.mark.asyncio
    async def test_gesture_nod(self, adapter) -> None:
        """Test nodding gesture."""
        client = adapter.client

        result = await client.nod(times=2, speed="normal")
        assert "status" in result or "message" in result or "uuid" in result

    @pytest.mark.asyncio
    async def test_gesture_shake(self, adapter) -> None:
        """Test head shake gesture."""
        client = adapter.client

        result = await client.shake(times=2, speed="normal")
        assert "status" in result or "message" in result or "uuid" in result

    @pytest.mark.asyncio
    async def test_look_at(self, adapter) -> None:
        """Test precise head positioning."""
        client = adapter.client

        result = await client.look_at(
            roll=10.0,
            pitch=-5.0,
            yaw=15.0,
        )
        assert "status" in result or "message" in result or "uuid" in result

    @pytest.mark.asyncio
    async def test_sleep_wake_cycle(self, adapter) -> None:
        """Test sleep/wake cycle."""
        client = adapter.client

        # Sleep
        result = await client.sleep()
        assert "status" in result or "uuid" in result

        # Wake up
        result = await client.wake_up()
        assert "status" in result or "uuid" in result
