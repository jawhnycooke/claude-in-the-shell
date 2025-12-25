"""Simulation daemon launcher for Reachy Agent.

Manages launching and stopping the Reachy Mini daemon in MuJoCo simulation mode.
This provides a physics-accurate simulation for testing without hardware.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import httpx

from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from asyncio import Task

log = get_logger(__name__)


class SimulationScene(str, Enum):
    """Available simulation scenes."""

    EMPTY = "empty"
    MINIMAL = "minimal"  # Includes table with objects (apple, croissant, duck)


@dataclass
class SimulationConfig:
    """Configuration for the simulation daemon."""

    scene: SimulationScene = SimulationScene.EMPTY
    headless: bool = False  # Set True for CI/testing without display
    host: str = "127.0.0.1"
    port: int = 8000
    startup_timeout: float = 30.0  # seconds to wait for daemon startup
    health_check_interval: float = 0.5  # seconds between health checks


@dataclass
class SimulationDaemon:
    """Manages the Reachy Mini daemon running in MuJoCo simulation mode.

    This class launches the official reachy-mini-daemon with --sim flag,
    which uses MuJoCo for physics simulation instead of real hardware.

    Usage:
        async with SimulationDaemon() as daemon:
            # daemon.base_url contains the HTTP endpoint
            # Use with ReachyDaemonClient(base_url=daemon.base_url)

    Or manually:
        daemon = SimulationDaemon()
        await daemon.start()
        try:
            # ... use daemon ...
        finally:
            await daemon.stop()
    """

    config: SimulationConfig = field(default_factory=SimulationConfig)
    _process: subprocess.Popen | None = field(default=None, init=False, repr=False)
    _health_task: Task | None = field(default=None, init=False, repr=False)

    @property
    def base_url(self) -> str:
        """Get the base URL for the daemon API."""
        return f"http://{self.config.host}:{self.config.port}"

    @property
    def is_running(self) -> bool:
        """Check if the daemon process is running."""
        return self._process is not None and self._process.poll() is None

    async def start(self) -> None:
        """Start the simulation daemon.

        Launches reachy-mini-daemon in simulation mode and waits for it to be ready.

        Raises:
            RuntimeError: If daemon fails to start or become healthy.
        """
        if self.is_running:
            log.warning("Simulation daemon already running")
            return

        log.info(
            "Starting Reachy Mini simulation daemon",
            scene=self.config.scene.value,
            headless=self.config.headless,
            port=self.config.port,
        )

        # Build command and environment based on platform
        # macOS requires mjpython for GUI rendering with MuJoCo
        env = os.environ.copy()

        if sys.platform == "darwin" and not self.config.headless:
            # Find mjpython - check common locations
            mjpython_path = shutil.which("mjpython")
            if mjpython_path is None:
                # Try common Homebrew locations
                for path in ["/opt/homebrew/bin/mjpython", "/usr/local/bin/mjpython"]:
                    if os.path.exists(path):
                        mjpython_path = path
                        break

            if mjpython_path is None:
                raise RuntimeError(
                    "mjpython not found. Install with: brew install mujoco\n"
                    "Or run in headless mode with: --headless"
                )

            cmd = [
                mjpython_path,
                "-m",
                "reachy_mini.daemon.app.main",
                "--sim",
                "--scene",
                self.config.scene.value,
                "--fastapi-port",
                str(self.config.port),
            ]

            # Set PYTHONPATH to include current venv's site-packages
            # so mjpython can find installed packages like reachy_mini
            import site
            venv_site_packages = site.getsitepackages()
            current_pythonpath = env.get("PYTHONPATH", "")
            new_pythonpath = os.pathsep.join(venv_site_packages)
            if current_pythonpath:
                new_pythonpath = f"{new_pythonpath}{os.pathsep}{current_pythonpath}"
            env["PYTHONPATH"] = new_pythonpath

            log.debug(
                "Using mjpython for GUI mode",
                mjpython_path=mjpython_path,
                pythonpath=new_pythonpath,
            )
        else:
            cmd = [
                sys.executable,
                "-m",
                "reachy_mini.daemon.app.main",
                "--sim",
                "--scene",
                self.config.scene.value,
                "--fastapi-port",
                str(self.config.port),
            ]

        if self.config.headless:
            cmd.append("--headless")

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"Failed to start simulation daemon. Command not found: {cmd[0]}. "
                "Ensure reachy-mini[mujoco] is installed."
            ) from e

        # Wait for daemon to become healthy
        await self._wait_for_healthy()

        log.info(
            "Simulation daemon started successfully",
            pid=self._process.pid,
            url=self.base_url,
        )

    async def _wait_for_healthy(self) -> None:
        """Wait for the daemon to become healthy.

        Raises:
            RuntimeError: If daemon doesn't become healthy within timeout.
        """
        start_time = time.time()
        last_error = None

        async with httpx.AsyncClient() as client:
            while time.time() - start_time < self.config.startup_timeout:
                # Check if process died
                if self._process is not None and self._process.poll() is not None:
                    stdout, stderr = self._process.communicate()
                    raise RuntimeError(
                        f"Simulation daemon exited unexpectedly.\n"
                        f"Exit code: {self._process.returncode}\n"
                        f"Stdout: {stdout}\n"
                        f"Stderr: {stderr}"
                    )

                try:
                    response = await client.get(
                        f"{self.base_url}/api/daemon/status",
                        timeout=2.0,
                    )
                    if response.status_code == 200:
                        status = response.json()
                        # Reachy daemon uses "READY" or just a valid status object
                        if status.get("state") in ("READY", "RUNNING") or "robot_name" in status:
                            return
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    last_error = e

                await asyncio.sleep(self.config.health_check_interval)

        raise RuntimeError(
            f"Simulation daemon did not become healthy within "
            f"{self.config.startup_timeout}s. Last error: {last_error}"
        )

    async def stop(self) -> None:
        """Stop the simulation daemon gracefully."""
        if not self.is_running:
            log.debug("Simulation daemon not running, nothing to stop")
            return

        log.info("Stopping simulation daemon", pid=self._process.pid if self._process else None)

        if self._process is not None:
            # Try graceful shutdown first
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                log.warning("Daemon didn't terminate gracefully, killing")
                self._process.kill()
                self._process.wait()

            self._process = None

        log.info("Simulation daemon stopped")

    async def restart(self) -> None:
        """Restart the simulation daemon."""
        await self.stop()
        await self.start()

    async def health_check(self) -> dict:
        """Check daemon health status.

        Returns:
            Status dictionary from daemon.
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/api/daemon/status",
                    timeout=2.0,
                )
                return response.json()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                return {"status": "error", "error": str(e)}

    async def __aenter__(self) -> SimulationDaemon:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
