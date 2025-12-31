"""Motion blend controller - orchestrates all motion sources.

The MotionBlendController manages multiple motion sources and composes
their contributions into a final pose sent to the daemon.

Key concepts:
- Configurable tick rate (code default: 30Hz, config may override to 100Hz)
- Configurable command rate (code default: 15Hz, config may override to 20Hz)
- Composes primary (exclusive) + secondary (additive) motions
- Applies smoothing and safety limits
- Prefers SDK for motion commands (1-5ms latency), falls back to HTTP (10-50ms)

Based on MovementManager pattern from Pollen Robotics' Conversation App.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from reachy_agent.behaviors.motion_types import (
    HeadPose,
    MotionPriority,
    MotionSource,
    PoseLimits,
    PoseOffset,
)
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.mcp_servers.reachy.sdk_client import ReachySDKClient

log = get_logger(__name__)


@dataclass
class BlendControllerConfig:
    """Configuration for the motion blend controller.

    Attributes:
        tick_rate_hz: Internal control loop rate (default 30Hz, config: 100Hz).
        command_rate_hz: Rate to send commands to daemon (default 15Hz, config: 20Hz).
        smoothing_factor: Pose interpolation factor (0.0-1.0).
        enabled: Whether blending is active.
        pose_limits: Safety limits for poses.
    """

    tick_rate_hz: float = 30.0  # Default for CPU efficiency; config/default.yaml uses 100Hz
    command_rate_hz: float = 15.0  # Balances smooth motion and USB bus load; config uses 20Hz
    smoothing_factor: float = 0.35  # Tuned for 15Hz command rate
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
    - A configurable control loop (default 30Hz, config may set 100Hz)
    - A configurable rate limiter for daemon commands (default 15Hz, config: 20Hz)

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
        sdk_client: ReachySDKClient | None = None,
    ) -> None:
        """Initialize the blend controller.

        Args:
            config: Controller configuration. Uses defaults if not provided.
            send_pose_callback: Async callback to send poses via HTTP daemon.
                                Used as fallback if SDK is unavailable.
            sdk_client: Optional SDK client for direct motion control.
                        Preferred over HTTP callback when available.
        """
        self.config = config or BlendControllerConfig()
        self._send_pose = send_pose_callback
        self._sdk_client = sdk_client

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

        # SDK fallback tracking
        self._sdk_failures: int = 0
        self._sdk_fallback_active: bool = False

        # Motion health tracking (detects when both SDK and HTTP are failing)
        self._consecutive_total_failures: int = 0
        self._motion_healthy: bool = True
        self._UNHEALTHY_THRESHOLD: int = 10  # After 10 consecutive total failures

        # HTTP fallback failure tracking
        self._http_failures: int = 0

        # Listening state (freezes antennas during user speech)
        self._listening = False
        self._frozen_antenna_left: float = 90.0  # Vertical (straight up)
        self._frozen_antenna_right: float = 90.0

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

    @property
    def is_motion_healthy(self) -> bool:
        """Check if motion control is healthy (at least one method working)."""
        return self._motion_healthy

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
        """Send pose to daemon - prefer SDK (lower latency), fall back to HTTP.

        The SDK uses Zenoh pub/sub (1-5ms latency) vs HTTP REST (10-50ms),
        making it ideal for the 15Hz blend controller loop.

        Args:
            pose: Pose to send to the daemon.
        """
        sdk_success = False
        http_success = False

        # Try SDK first (lower latency via Zenoh)
        if self._sdk_client and not self._sdk_fallback_active:
            try:
                sdk_success = await self._sdk_client.set_pose(pose)
                if sdk_success:
                    # Reset failure count on success
                    if self._sdk_failures > 0:
                        self._sdk_failures = 0
                        log.info("SDK connection recovered")
                else:
                    self._sdk_failures += 1
            except asyncio.CancelledError:
                # Don't count cancellation as SDK failure
                raise
            except (RuntimeError, OSError, ConnectionError) as e:
                self._sdk_failures += 1
                log.debug("sdk_set_pose_exception", error=str(e), error_type=type(e).__name__)
            except Exception as e:
                # Unexpected errors - log at warning level
                self._sdk_failures += 1
                log.warning("sdk_set_pose_unexpected", error=str(e), error_type=type(e).__name__)

            # After 5 consecutive failures, fall back to HTTP
            if self._sdk_failures >= 5 and not self._sdk_fallback_active:
                log.warning(
                    "SDK failing consistently, switching to HTTP fallback",
                    failures=self._sdk_failures,
                )
                self._sdk_fallback_active = True

        # If SDK succeeded, we're done
        if sdk_success:
            self._reset_motion_health_on_success()
            return

        # Fall back to HTTP callback
        if self._send_pose:
            try:
                result = self._send_pose(pose)
                # Handle both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
                http_success = True
                self._http_failures = 0  # Reset on success
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._http_failures += 1
                log.warning(
                    "http_pose_send_failed",
                    error=str(e),
                    consecutive_failures=self._http_failures,
                )

        # Track overall motion health
        if http_success:
            self._reset_motion_health_on_success()
        elif not sdk_success and not http_success:
            self._consecutive_total_failures += 1
            if self._consecutive_total_failures >= self._UNHEALTHY_THRESHOLD:
                if self._motion_healthy:
                    log.error(
                        "motion_control_unhealthy",
                        consecutive_failures=self._consecutive_total_failures,
                        sdk_failures=self._sdk_failures,
                        http_failures=self._http_failures,
                    )
                    self._motion_healthy = False

    def _reset_motion_health_on_success(self) -> None:
        """Reset motion health tracking after successful pose send."""
        if self._consecutive_total_failures > 0:
            self._consecutive_total_failures = 0
            if not self._motion_healthy:
                log.info("motion_control_recovered")
                self._motion_healthy = True

    def reset_sdk_fallback(self) -> None:
        """Reset SDK fallback state to retry SDK connection.

        Call this after fixing SDK issues to re-enable SDK motion control.
        """
        if self._sdk_fallback_active:
            log.info("Resetting SDK fallback state, will retry SDK")
            self._sdk_fallback_active = False
            self._sdk_failures = 0

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
            "sdk_connected": self._sdk_client.is_connected if self._sdk_client else False,
            "sdk_fallback_active": self._sdk_fallback_active,
            "sdk_failures": self._sdk_failures,
            "http_failures": self._http_failures,
            "motion_healthy": self._motion_healthy,
            "consecutive_total_failures": self._consecutive_total_failures,
            "current_pose": {
                "pitch": self._current_pose.pitch,
                "yaw": self._current_pose.yaw,
                "roll": self._current_pose.roll,
                "z": self._current_pose.z,
                "left_antenna": self._current_pose.left_antenna,
                "right_antenna": self._current_pose.right_antenna,
            },
        }
