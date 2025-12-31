"""Reachy SDK Client - Direct Python SDK wrapper for motion control.

Uses the reachy_mini Python SDK for high-frequency motion control (blend controller)
while the HTTP daemon client handles MCP tools and features not in SDK.

The SDK uses Zenoh pub/sub for low-latency communication (1-5ms) compared to
HTTP REST API (10-50ms), making it ideal for the 15Hz blend controller loop.
"""

from __future__ import annotations

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_mini import ReachyMini

    from reachy_agent.behaviors.motion_types import HeadPose

log = get_logger(__name__)


@dataclass
class SDKClientConfig:
    """Configuration for the SDK client.

    Attributes:
        enabled: Whether to use SDK for motion (vs HTTP fallback).
        robot_name: Robot name for Zenoh connection (default: "reachy_mini").
        max_workers: Thread pool size for blocking SDK calls.
        connect_timeout_seconds: Timeout for initial connection.
        fallback_to_http: Fall back to HTTP if SDK fails.
        localhost_only: Only connect to localhost daemons (default: True).
    """

    enabled: bool = True
    robot_name: str = "reachy_mini"
    max_workers: int = 1
    connect_timeout_seconds: float = 10.0
    fallback_to_http: bool = True
    localhost_only: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SDKClientConfig:
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            robot_name=data.get("robot_name", "reachy_mini"),
            max_workers=data.get("max_workers", 1),
            connect_timeout_seconds=data.get("connect_timeout_seconds", 10.0),
            fallback_to_http=data.get("fallback_to_http", True),
            localhost_only=data.get("localhost_only", True),
        )


class ReachySDKClient:
    """Direct Python SDK client for Reachy Mini motion control.

    Uses asyncio.run_in_executor() to wrap blocking SDK calls for
    compatibility with our async architecture.

    Coordinate conversions:
    - Our HeadPose uses degrees; SDK uses radians
    - Our antennas: 0°=flat/back, 90°=vertical
    - SDK antennas: 0 rad=vertical, π/2 rad=flat/back
    - SDK set_target() wants 4x4 pose matrix for head

    Example:
        config = SDKClientConfig(enabled=True)
        client = ReachySDKClient(config)

        if await client.connect():
            await client.set_pose(HeadPose(yaw=10, pitch=5, left_antenna=80))
        else:
            # Fall back to HTTP
            pass
    """

    def __init__(self, config: SDKClientConfig | None = None) -> None:
        """Initialize the SDK client.

        Args:
            config: Client configuration. Uses defaults if not provided.
        """
        self.config = config or SDKClientConfig()
        self._robot: ReachyMini | None = None
        self._executor: ThreadPoolExecutor | None = None
        self._connected = False
        self._last_error: str | None = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to robot via SDK."""
        return self._connected and self._robot is not None

    @property
    def last_error(self) -> str | None:
        """Get the last error message if any."""
        return self._last_error

    async def connect(self) -> bool:
        """Connect to the robot via SDK.

        Returns:
            True if connection successful, False otherwise.
        """
        if not self.config.enabled:
            log.info("SDK client disabled in config")
            return False

        try:
            # Import here to avoid import error if SDK not installed
            from reachy_mini import ReachyMini

            # Create executor for blocking SDK calls
            self._executor = ThreadPoolExecutor(
                max_workers=self.config.max_workers,
                thread_name_prefix="reachy_sdk",
            )

            # SDK connection is blocking, run in executor with timeout
            loop = asyncio.get_event_loop()

            # Capture config for closure
            robot_name = self.config.robot_name
            localhost_only = self.config.localhost_only
            timeout = self.config.connect_timeout_seconds

            def _connect() -> ReachyMini:
                return ReachyMini(
                    robot_name=robot_name,
                    localhost_only=localhost_only,
                    # Don't try to spawn a new daemon - we use existing one
                    spawn_daemon=False,
                    # Disable media - we only need motion control
                    media_backend="no_media",
                    # Reduce log noise
                    log_level="WARNING",
                )

            self._robot = await asyncio.wait_for(
                loop.run_in_executor(self._executor, _connect),
                timeout=self.config.connect_timeout_seconds + 5.0,  # Extra buffer
            )

            self._connected = True
            self._last_error = None
            log.info(
                "SDK client connected",
                robot_name=robot_name,
            )
            return True

        except ImportError as e:
            self._last_error = f"reachy_mini SDK not installed: {e}"
            log.warning("SDK import failed", error=self._last_error)
            return False

        except asyncio.TimeoutError:
            self._last_error = f"Connection timeout after {self.config.connect_timeout_seconds}s"
            log.warning("SDK connection timeout", timeout=self.config.connect_timeout_seconds)
            return False

        except Exception as e:
            self._last_error = str(e)
            log.error("SDK connection failed", error=self._last_error)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the robot and cleanup resources."""
        self._connected = False
        self._robot = None

        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None

        log.info("SDK client disconnected")

    def _head_pose_to_matrix(self, pose: HeadPose) -> np.ndarray:
        """Convert HeadPose (degrees) to 4x4 transformation matrix.

        The SDK expects a 4x4 homogeneous transformation matrix for head pose.
        We use ZYX Euler angle convention (yaw-pitch-roll).

        Args:
            pose: HeadPose with roll, pitch, yaw in degrees.

        Returns:
            4x4 numpy array representing the head transformation.
        """
        # Convert degrees to radians
        # Note: Invert pitch because our positive=up, SDK negative=up
        roll = math.radians(pose.roll)
        pitch = math.radians(-pose.pitch)
        yaw = math.radians(pose.yaw)

        # Precompute sin/cos values
        cr, sr = math.cos(roll), math.sin(roll)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)

        # Build rotation matrix using ZYX Euler angles
        # R = Rz(yaw) * Ry(pitch) * Rx(roll)
        matrix = np.eye(4)
        matrix[0, 0] = cy * cp
        matrix[0, 1] = cy * sp * sr - sy * cr
        matrix[0, 2] = cy * sp * cr + sy * sr
        matrix[1, 0] = sy * cp
        matrix[1, 1] = sy * sp * sr + cy * cr
        matrix[1, 2] = sy * sp * cr - cy * sr
        matrix[2, 0] = -sp
        matrix[2, 1] = cp * sr
        matrix[2, 2] = cp * cr

        return matrix

    def _antennas_to_radians(
        self, left_deg: float, right_deg: float
    ) -> tuple[float, float]:
        """Convert antenna degrees to SDK radians.

        Coordinate convention conversion:
        - Our convention: 0° = flat/back, 90° = vertical (straight up)
        - SDK convention: 0 rad = vertical, π/2 rad = flat/back

        Args:
            left_deg: Left antenna angle in our degrees convention.
            right_deg: Right antenna angle in our degrees convention.

        Returns:
            Tuple of (left_rad, right_rad) in SDK convention.
        """
        left_rad = math.radians(90.0 - left_deg)
        right_rad = math.radians(90.0 - right_deg)
        return (left_rad, right_rad)

    async def set_pose(self, pose: HeadPose) -> bool:
        """Send pose to robot via SDK set_target().

        This is the primary method called by the blend controller.
        Converts from our HeadPose format to SDK's matrix format.

        Args:
            pose: HeadPose with roll, pitch, yaw, left_antenna, right_antenna.

        Returns:
            True if successful, False otherwise.
        """
        if not self.is_connected or self._robot is None:
            return False

        if self._executor is None:
            return False

        try:
            head_matrix = self._head_pose_to_matrix(pose)
            antennas = self._antennas_to_radians(
                pose.left_antenna, pose.right_antenna
            )

            # Capture robot reference for the closure
            robot = self._robot

            # SDK call is blocking, run in executor
            def _set_target() -> None:
                robot.set_target(
                    head=head_matrix,
                    antennas=antennas,
                    body_yaw=0.0,  # Not using body rotation from blend controller
                )

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self._executor, _set_target)
            return True

        except Exception as e:
            # Rate-limit error logging to avoid spam at 15Hz
            log.debug("SDK set_pose failed", error=str(e))
            return False

    def get_status(self) -> dict[str, Any]:
        """Get SDK client status for debugging.

        Returns:
            Dictionary with connection state and configuration.
        """
        return {
            "connected": self._connected,
            "enabled": self.config.enabled,
            "robot_name": self.config.robot_name,
            "last_error": self._last_error,
            "fallback_to_http": self.config.fallback_to_http,
        }
