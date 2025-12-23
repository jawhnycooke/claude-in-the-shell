"""Simulation adapter bridging MCP tools to MuJoCo simulation.

This module provides the SimulationAdapter that translates our MCP tool calls
to the Reachy Mini daemon API, whether running in simulation or on real hardware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from reachy_agent.utils.logging import get_logger

from .daemon_launcher import SimulationConfig, SimulationDaemon, SimulationScene
from .reachy_client import ReachyMiniClient

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


@dataclass
class SimulationAdapter:
    """Adapter bridging Reachy Agent MCP tools to MuJoCo simulation.

    This adapter manages the simulation daemon lifecycle and provides
    a client that connects to the simulated robot using the real
    Reachy Mini daemon API.

    Usage:
        async with SimulationAdapter() as adapter:
            client = adapter.client
            await client.move_head("left")
            await client.nod(times=2)

    The adapter:
    1. Starts the Reachy Mini daemon in MuJoCo simulation mode
    2. Provides a ReachyMiniClient connected to the simulation
    3. Cleans up on exit
    """

    config: SimulationConfig = field(default_factory=SimulationConfig)
    _daemon: SimulationDaemon = field(init=False, repr=False)
    _client: ReachyMiniClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the daemon wrapper."""
        self._daemon = SimulationDaemon(config=self.config)

    @property
    def client(self) -> ReachyMiniClient:
        """Get the client for making API calls.

        Returns:
            ReachyMiniClient connected to the simulation.

        Raises:
            RuntimeError: If adapter hasn't been started.
        """
        if self._client is None:
            raise RuntimeError(
                "SimulationAdapter not started. Use 'async with' or call start() first."
            )
        return self._client

    @property
    def is_running(self) -> bool:
        """Check if the simulation is running."""
        return self._daemon.is_running

    @property
    def base_url(self) -> str:
        """Get the simulation daemon base URL."""
        return self._daemon.base_url

    async def start(self) -> None:
        """Start the simulation.

        This launches the MuJoCo simulation daemon and creates a client.
        """
        log.info("Starting simulation adapter")
        await self._daemon.start()
        self._client = ReachyMiniClient(base_url=self._daemon.base_url)
        log.info("Simulation adapter ready", url=self.base_url)

    async def stop(self) -> None:
        """Stop the simulation and clean up."""
        log.info("Stopping simulation adapter")

        if self._client is not None:
            await self._client.close()
            self._client = None

        await self._daemon.stop()
        log.info("Simulation adapter stopped")

    async def restart(self) -> None:
        """Restart the simulation."""
        await self.stop()
        await self.start()

    async def health_check(self) -> dict[str, Any]:
        """Check simulation health.

        Returns:
            Health status dictionary.
        """
        return await self._daemon.health_check()

    async def __aenter__(self) -> SimulationAdapter:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()


def create_simulation_adapter(
    scene: str = "empty",
    headless: bool = False,
    port: int = 8000,
) -> SimulationAdapter:
    """Factory function to create a simulation adapter.

    Args:
        scene: Simulation scene ('empty' or 'minimal').
        headless: Run without GUI window (for CI/testing).
        port: Port for daemon API.

    Returns:
        Configured SimulationAdapter instance.

    Example:
        adapter = create_simulation_adapter(scene="minimal", headless=True)
        async with adapter:
            await adapter.client.move_head("left")
    """
    config = SimulationConfig(
        scene=SimulationScene(scene),
        headless=headless,
        port=port,
    )
    return SimulationAdapter(config=config)
