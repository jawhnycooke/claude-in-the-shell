"""Motion blend controller - orchestrates all motion sources.

The MotionBlendController manages multiple motion sources and composes
their contributions into a final pose sent to the daemon.

Key concepts:
- Runs at 100Hz internal tick rate
- Sends commands to daemon at 20Hz (configurable)
- Composes primary (exclusive) + secondary (additive) motions
- Applies smoothing and safety limits

Based on MovementManager pattern from Pollen Robotics' Conversation App.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from reachy_agent.behaviors.motion_types import (
    HeadPose,
    MotionPriority,
    MotionSource,
    PoseLimits,
    PoseOffset,
)
from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class BlendControllerConfig:
    """Configuration for the motion blend controller.

    Attributes:
        tick_rate_hz: Internal control loop rate (default 100Hz).
        command_rate_hz: Rate to send commands to daemon (default 20Hz).
        smoothing_factor: Pose interpolation factor (0.0-1.0).
        enabled: Whether blending is active.
        pose_limits: Safety limits for poses.
    """

    tick_rate_hz: float = 100.0
    command_rate_hz: float = 20.0
    smoothing_factor: float = 0.3
    enabled: bool = True
    pose_limits: PoseLimits = field(default_factory=PoseLimits)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlendControllerConfig:
        """Create from dictionary."""
        pose_limits_data = data.get("pose_limits")
        # Filter out pose_limits when creating config to avoid passing it twice
        filtered_data = {k: v for k, v in data.items() if hasattr(cls, k) and k != "pose_limits"}
        config = cls(**filtered_data)
        if pose_limits_data:
            config.pose_limits = PoseLimits.from_dict(pose_limits_data)
        return config


class MotionBlendController:
    """Orchestrates motion sources and sends composed poses to the daemon.

    The controller maintains:
    - A registry of motion sources (primary and secondary)
    - The currently active primary source
    - A 100Hz control loop that composes poses
    - A 20Hz rate limiter for daemon commands

    Example:
        config = BlendControllerConfig()
        controller = MotionBlendController(
            config,
            send_pose_callback=daemon_client.send_pose
        )

        # Register motion sources
        controller.register_source("breathing", breathing_motion)
        controller.register_source("wobble", wobble_motion)

        # Activate primary source
        controller.set_primary("breathing")

        # Start the control loop
        await controller.start()

        # Later, during speech
        controller.enable_secondary("wobble")
    """

    def __init__(
        self,
        config: BlendControllerConfig | None = None,
        send_pose_callback: Callable[[HeadPose], Any] | None = None,
    ) -> None:
        """Initialize the blend controller.

        Args:
            config: Controller configuration. Uses defaults if not provided.
            send_pose_callback: Async callback to send poses to the daemon.
                                Receives a HeadPose and should send to hardware.
        """
        self.config = config or BlendControllerConfig()
        self._send_pose = send_pose_callback

        # Motion source registry
        self._sources: dict[str, MotionSource] = {}
        self._active_primary: str | None = None
        self._active_secondaries: set[str] = set()

        # Control loop state
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._current_pose = HeadPose.neutral()
        self._target_pose = HeadPose.neutral()
        self._last_command_time: datetime | None = None

        # Listening state (freezes antennas during user speech)
        self._listening = False
        self._frozen_antenna_left: float = 45.0
        self._frozen_antenna_right: float = 45.0

    @property
    def is_running(self) -> bool:
        """Check if the control loop is running."""
        return self._running

    @property
    def current_pose(self) -> HeadPose:
        """Get the current smoothed pose."""
        return self._current_pose

    @property
    def active_primary(self) -> str | None:
        """Get the name of the active primary motion source."""
        return self._active_primary

    @property
    def active_secondaries(self) -> set[str]:
        """Get names of active secondary motion sources."""
        return self._active_secondaries.copy()

    def register_source(self, name: str, source: MotionSource) -> None:
        """Register a motion source.

        Args:
            name: Unique identifier for the source.
            source: Motion source implementing the MotionSource protocol.
        """
        self._sources[name] = source
        log.debug("Registered motion source", name=name, priority=source.priority)

    def unregister_source(self, name: str) -> None:
        """Unregister a motion source.

        Args:
            name: Name of the source to remove.
        """
        if name in self._sources:
            # Deactivate if active
            if name == self._active_primary:
                self._active_primary = None
            self._active_secondaries.discard(name)
            del self._sources[name]
            log.debug("Unregistered motion source", name=name)

    async def set_primary(self, name: str | None) -> None:
        """Set the active primary motion source.

        Only one primary source can be active at a time.
        Setting to None deactivates all primary sources.

        Args:
            name: Name of the primary source to activate, or None.
        """
        # Stop current primary if different
        if self._active_primary and self._active_primary != name:
            source = self._sources.get(self._active_primary)
            if source:
                await source.stop()
                log.info("Stopped primary motion", name=self._active_primary)

        # Start new primary
        if name:
            source = self._sources.get(name)
            if source and source.priority == MotionPriority.PRIMARY:
                await source.start()
                self._active_primary = name
                log.info("Started primary motion", name=name)
            elif source:
                log.warning("Source is not PRIMARY priority", name=name)
            else:
                log.warning("Unknown motion source", name=name)
        else:
            self._active_primary = None

    async def enable_secondary(self, name: str) -> None:
        """Enable a secondary (additive) motion source.

        Multiple secondary sources can be active simultaneously.

        Args:
            name: Name of the secondary source to enable.
        """
        source = self._sources.get(name)
        if source and source.priority == MotionPriority.SECONDARY:
            await source.start()
            self._active_secondaries.add(name)
            log.info("Enabled secondary motion", name=name)
        elif source:
            log.warning("Source is not SECONDARY priority", name=name)
        else:
            log.warning("Unknown motion source", name=name)

    async def disable_secondary(self, name: str) -> None:
        """Disable a secondary motion source.

        Args:
            name: Name of the secondary source to disable.
        """
        source = self._sources.get(name)
        if source:
            await source.stop()
            self._active_secondaries.discard(name)
            log.info("Disabled secondary motion", name=name)

    def set_listening(self, listening: bool) -> None:
        """Set listening state (freezes antennas during user speech).

        When listening is True, antenna positions are frozen to avoid
        distracting movements while the user speaks.

        Args:
            listening: Whether the robot is listening to the user.
        """
        if listening and not self._listening:
            # Entering listening state - capture current antenna positions
            self._frozen_antenna_left = self._current_pose.left_antenna
            self._frozen_antenna_right = self._current_pose.right_antenna
            log.debug("Entering listening state - antennas frozen")
        elif not listening and self._listening:
            log.debug("Exiting listening state - antennas unfrozen")

        self._listening = listening

    async def start(self) -> None:
        """Start the motion blend control loop."""
        if self._running:
            log.warning("Blend controller already running")
            return

        if not self.config.enabled:
            log.info("Motion blending is disabled in config")
            return

        self._running = True
        self._task = asyncio.create_task(self._control_loop())
        log.info(
            "Motion blend controller started",
            tick_rate_hz=self.config.tick_rate_hz,
            command_rate_hz=self.config.command_rate_hz,
        )

    async def stop(self) -> None:
        """Stop the motion blend control loop."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Stop all active sources
        if self._active_primary:
            source = self._sources.get(self._active_primary)
            if source:
                await source.stop()

        for name in list(self._active_secondaries):
            source = self._sources.get(name)
            if source:
                await source.stop()

        self._active_secondaries.clear()
        log.info("Motion blend controller stopped")

    async def _control_loop(self) -> None:
        """Main control loop - runs at tick_rate_hz."""
        tick_interval = 1.0 / self.config.tick_rate_hz
        command_interval = 1.0 / self.config.command_rate_hz

        while self._running:
            loop_start = datetime.now()

            try:
                # Compose the target pose from all active sources
                self._target_pose = await self._compose_pose()

                # Smooth toward target
                self._current_pose = self._smooth_pose(
                    self._current_pose,
                    self._target_pose,
                    self.config.smoothing_factor,
                )

                # Apply safety limits
                self._current_pose = self._current_pose.clamp(self.config.pose_limits)

                # Apply listening state (freeze antennas)
                if self._listening:
                    self._current_pose = HeadPose(
                        pitch=self._current_pose.pitch,
                        yaw=self._current_pose.yaw,
                        roll=self._current_pose.roll,
                        z=self._current_pose.z,
                        left_antenna=self._frozen_antenna_left,
                        right_antenna=self._frozen_antenna_right,
                    )

                # Rate-limit commands to daemon
                should_send = False
                if self._last_command_time is None:
                    should_send = True
                else:
                    elapsed = (datetime.now() - self._last_command_time).total_seconds()
                    if elapsed >= command_interval:
                        should_send = True

                if should_send and self._send_pose:
                    await self._send_pose_to_daemon(self._current_pose)
                    self._last_command_time = datetime.now()

            except Exception as e:
                log.exception("Error in blend control loop", error=str(e))

            # Maintain tick rate
            elapsed = (datetime.now() - loop_start).total_seconds()
            sleep_time = max(0.0, tick_interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _compose_pose(self) -> HeadPose:
        """Compose the final pose from active motion sources.

        Returns:
            HeadPose composed from primary + secondary sources.
        """
        # Start with neutral or current pose
        base_pose = HeadPose.neutral()

        # Get primary contribution (replaces base)
        if self._active_primary:
            source = self._sources.get(self._active_primary)
            if source and source.is_active:
                contribution = await source.get_contribution(base_pose)
                if isinstance(contribution, HeadPose):
                    base_pose = contribution

        # Add secondary contributions (additive)
        total_offset = PoseOffset()
        for name in self._active_secondaries:
            source = self._sources.get(name)
            if source and source.is_active:
                contribution = await source.get_contribution(base_pose)
                if isinstance(contribution, PoseOffset):
                    total_offset = total_offset + contribution

        # Compose final pose
        return base_pose + total_offset

    def _smooth_pose(
        self,
        current: HeadPose,
        target: HeadPose,
        factor: float,
    ) -> HeadPose:
        """Smooth transition from current to target pose.

        Args:
            current: Current pose.
            target: Target pose to move toward.
            factor: Interpolation factor (0.0 = no movement, 1.0 = instant).

        Returns:
            Smoothed pose between current and target.
        """
        return current.lerp(target, factor)

    async def _send_pose_to_daemon(self, pose: HeadPose) -> None:
        """Send pose to the daemon via callback.

        Args:
            pose: Pose to send to the daemon.
        """
        if self._send_pose:
            try:
                result = self._send_pose(pose)
                # Handle both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log.exception("Error sending pose to daemon", error=str(e))

    def get_status(self) -> dict[str, Any]:
        """Get current controller status for debugging.

        Returns:
            Dictionary with controller state information.
        """
        return {
            "running": self._running,
            "enabled": self.config.enabled,
            "active_primary": self._active_primary,
            "active_secondaries": list(self._active_secondaries),
            "registered_sources": list(self._sources.keys()),
            "listening": self._listening,
            "current_pose": {
                "pitch": self._current_pose.pitch,
                "yaw": self._current_pose.yaw,
                "roll": self._current_pose.roll,
                "z": self._current_pose.z,
                "left_antenna": self._current_pose.left_antenna,
                "right_antenna": self._current_pose.right_antenna,
            },
        }
