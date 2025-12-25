"""Client for the real Reachy Mini daemon API.

This client maps to the actual Reachy Mini daemon endpoints,
which differ from our mock daemon API used for unit testing.

The Reachy Mini daemon uses:
- /api/move/goto - for head/antenna/body positioning
- /api/move/play/wake_up - for waking up
- /api/move/play/goto_sleep - for sleeping
- /api/state/* - for reading robot state
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import httpx

from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class ReachyMiniClient:
    """HTTP client for the real Reachy Mini daemon API.

    This client uses the actual Reachy Mini SDK daemon endpoints,
    not our mock daemon endpoints used for unit testing.
    """

    base_url: str = "http://localhost:8000"
    timeout: float = 10.0
    _client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request."""
        client = await self._get_client()
        try:
            response = await client.request(method, path, json=json_data, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            log.error("Request failed", path=path, status=e.response.status_code)
            return {"error": str(e), "status_code": e.response.status_code}
        except httpx.RequestError as e:
            log.error("Request error", path=path, error=str(e))
            return {"error": str(e)}

    # ========== Status ==========

    async def get_status(self) -> dict[str, Any]:
        """Get daemon status."""
        return await self._request("GET", "/api/daemon/status")

    async def get_full_state(self) -> dict[str, Any]:
        """Get full robot state."""
        return await self._request("GET", "/api/state/full")

    # ========== Lifecycle ==========

    async def wake_up(self) -> dict[str, Any]:
        """Wake up the robot."""
        return await self._request("POST", "/api/move/play/wake_up")

    async def sleep(self) -> dict[str, Any]:
        """Put robot to sleep."""
        return await self._request("POST", "/api/move/play/goto_sleep")

    # ========== Movement ==========

    async def goto(
        self,
        head_pose: dict[str, float] | None = None,
        antennas: tuple[float, float] | None = None,
        body_yaw: float | None = None,
        duration: float = 1.0,
        interpolation: str = "minjerk",
    ) -> dict[str, Any]:
        """Move to target positions.

        Args:
            head_pose: Head pose dict with x, y, z, roll, pitch, yaw (in radians).
            antennas: Tuple of (left, right) antenna positions in radians.
            body_yaw: Body yaw angle in radians.
            duration: Movement duration in seconds.
            interpolation: Interpolation mode (linear, minjerk, ease, cartoon).

        Returns:
            Response with move UUID.
        """
        data: dict[str, Any] = {
            "duration": duration,
            "interpolation": interpolation,
        }

        if head_pose is not None:
            data["head_pose"] = head_pose
        if antennas is not None:
            data["antennas"] = list(antennas)
        if body_yaw is not None:
            data["body_yaw"] = body_yaw

        return await self._request("POST", "/api/move/goto", json_data=data)

    # ========== Convenience methods matching our MCP tools ==========

    async def move_head(
        self,
        direction: str,
        speed: str = "normal",
        degrees: float | None = None,
    ) -> dict[str, Any]:
        """Move head in a direction (maps to goto).

        Args:
            direction: left, right, up, down, or front.
            speed: slow, normal, or fast.
            degrees: Optional angle override.
        """
        # Map speed to duration
        duration_map = {"slow": 2.0, "normal": 1.0, "fast": 0.5}
        duration = duration_map.get(speed, 1.0)

        # Map direction to head pose (angles in radians)
        angle = math.radians(degrees if degrees is not None else 30)

        pose_map: dict[str, dict[str, float]] = {
            "left": {"yaw": angle},
            "right": {"yaw": -angle},
            "up": {"pitch": -angle},
            "down": {"pitch": angle},
            "front": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
        }

        head_pose: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0, "roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        head_pose.update(pose_map.get(direction, {}))

        return await self.goto(head_pose=head_pose, duration=duration)

    async def look_at(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        _z: float = 0.0,
        duration: float = 1.0,
    ) -> dict[str, Any]:
        """Position head with precise angles.

        Args:
            roll: Roll angle in degrees.
            pitch: Pitch angle in degrees.
            yaw: Yaw angle in degrees.
            _z: Vertical offset (not used in real daemon).
            duration: Movement duration.
        """
        head_pose = {
            "x": 0,
            "y": 0,
            "z": 0,
            "roll": math.radians(roll),
            "pitch": math.radians(pitch),
            "yaw": math.radians(yaw),
        }
        return await self.goto(head_pose=head_pose, duration=duration)

    async def set_antenna_state(
        self,
        left_angle: float | None = None,
        right_angle: float | None = None,
        duration_ms: int = 500,
    ) -> dict[str, Any]:
        """Set antenna positions.

        Args:
            left_angle: Left antenna angle in degrees (0-90).
            right_angle: Right antenna angle in degrees (0-90).
            duration_ms: Duration in milliseconds.
        """
        # Convert degrees to radians and clamp
        left_rad = math.radians(left_angle if left_angle is not None else 45)
        right_rad = math.radians(right_angle if right_angle is not None else 45)

        return await self.goto(
            antennas=(left_rad, right_rad),
            duration=duration_ms / 1000.0,
        )

    async def rotate(
        self,
        direction: str,
        degrees: float = 90.0,
        speed: str = "normal",
    ) -> dict[str, Any]:
        """Rotate the robot body.

        Args:
            direction: left or right.
            degrees: Rotation amount.
            speed: slow, normal, or fast.
        """
        duration_map = {"slow": 3.0, "normal": 2.0, "fast": 1.0}
        duration = duration_map.get(speed, 2.0)

        angle_rad = math.radians(degrees)
        if direction == "right":
            angle_rad = -angle_rad

        return await self.goto(body_yaw=angle_rad, duration=duration)

    async def nod(
        self,
        times: int = 2,
        speed: str = "normal",
    ) -> dict[str, Any]:
        """Perform nodding gesture.

        This is a simplified implementation using goto.
        """
        duration = 0.3 if speed == "fast" else 0.5 if speed == "normal" else 0.7
        results = []

        for _ in range(times):
            # Nod down
            result = await self.goto(
                head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0.3, "yaw": 0},
                duration=duration / 2,
            )
            results.append(result)

            # Nod up
            result = await self.goto(
                head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": -0.1, "yaw": 0},
                duration=duration / 2,
            )
            results.append(result)

        # Return to neutral
        await self.goto(
            head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
            duration=duration / 2,
        )

        return {"status": "ok", "moves": len(results)}

    async def shake(
        self,
        times: int = 2,
        speed: str = "normal",
    ) -> dict[str, Any]:
        """Perform head shake gesture."""
        duration = 0.3 if speed == "fast" else 0.5 if speed == "normal" else 0.7
        results = []

        for _ in range(times):
            # Shake left
            result = await self.goto(
                head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0.3},
                duration=duration / 2,
            )
            results.append(result)

            # Shake right
            result = await self.goto(
                head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": -0.3},
                duration=duration / 2,
            )
            results.append(result)

        # Return to neutral
        await self.goto(
            head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
            duration=duration / 2,
        )

        return {"status": "ok", "moves": len(results)}

    async def rest(self) -> dict[str, Any]:
        """Return to neutral resting pose."""
        return await self.goto(
            head_pose={"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0},
            antennas=(math.radians(45), math.radians(45)),
            body_yaw=0,
            duration=1.0,
        )

    async def get_sensor_data(
        self,
        _sensors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get sensor data (from state endpoint)."""
        state = await self.get_full_state()
        return {
            "status": "ok",
            "head_pose": state.get("head_pose"),
            "antennas": state.get("antennas_position"),
            "body_yaw": state.get("body_yaw"),
        }
