"""Reachy Daemon Client - HTTP client for Reachy hardware control.

Communicates with the Reachy Daemon (FastAPI server on localhost:8000)
provided by Pollen Robotics to control the physical robot.
"""

from __future__ import annotations

from typing import Any

import httpx

from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


class ReachyDaemonError(Exception):
    """Exception raised when daemon communication fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ReachyDaemonClient:
    """HTTP client for communicating with the Reachy Daemon.

    The Reachy Daemon is a FastAPI server provided by Pollen Robotics
    that controls the physical robot hardware.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 10.0,
    ) -> None:
        """Initialize the daemon client.

        Args:
            base_url: Base URL of the Reachy daemon API.
            timeout: Request timeout in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

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
    ) -> dict[str, Any]:
        """Make an HTTP request to the daemon.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: API path.
            json_data: Optional JSON body.

        Returns:
            Response data as dictionary.

        Raises:
            ReachyDaemonError: If the request fails.
        """
        client = await self._get_client()

        try:
            response = await client.request(method, path, json=json_data)
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError as e:
            log.error("Failed to connect to Reachy daemon", error=str(e))
            raise ReachyDaemonError(
                f"Cannot connect to Reachy daemon at {self.base_url}. "
                "Is the daemon running?"
            ) from e
        except httpx.TimeoutException as e:
            log.error("Reachy daemon request timed out", error=str(e))
            raise ReachyDaemonError("Request to Reachy daemon timed out") from e
        except httpx.HTTPStatusError as e:
            log.error(
                "Reachy daemon returned error",
                status_code=e.response.status_code,
                error=str(e),
            )
            raise ReachyDaemonError(
                f"Reachy daemon error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e

    async def health_check(self) -> dict[str, str]:
        """Check if the daemon is healthy.

        Returns:
            Health status dictionary.
        """
        try:
            return await self._request("GET", "/health")
        except ReachyDaemonError:
            return {"status": "unhealthy", "error": "Cannot reach daemon"}

    async def move_head(
        self,
        direction: str,
        speed: str = "normal",
        degrees: float | None = None,
    ) -> dict[str, str]:
        """Move the robot's head.

        Args:
            direction: Direction to look (left, right, up, down, front).
            speed: Movement speed (slow, normal, fast).
            degrees: Optional specific angle.

        Returns:
            Operation status.
        """
        data = {
            "direction": direction,
            "speed": speed,
        }
        if degrees is not None:
            data["degrees"] = degrees

        try:
            return await self._request("POST", "/head/move", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def play_emotion(
        self,
        emotion: str,
        intensity: float = 0.7,
    ) -> dict[str, str]:
        """Play an emotional expression.

        Args:
            emotion: Emotion to express.
            intensity: Expression intensity.

        Returns:
            Operation status.
        """
        data = {
            "emotion": emotion,
            "intensity": intensity,
        }

        try:
            return await self._request("POST", "/expression/emotion", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def speak(
        self,
        text: str,
        voice: str = "default",
        speed: float = 1.0,
    ) -> dict[str, str]:
        """Speak text through the robot's speaker.

        Args:
            text: Text to speak.
            voice: Voice profile.
            speed: Speech speed.

        Returns:
            Operation status.
        """
        data = {
            "text": text,
            "voice": voice,
            "speed": speed,
        }

        try:
            return await self._request("POST", "/audio/speak", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def capture_image(
        self,
        analyze: bool = False,
        save: bool = False,
    ) -> dict[str, str]:
        """Capture an image from the camera.

        Args:
            analyze: Whether to analyze the image.
            save: Whether to save to disk.

        Returns:
            Capture result.
        """
        data = {
            "analyze": analyze,
            "save": save,
        }

        try:
            return await self._request("POST", "/camera/capture", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def set_antenna_state(
        self,
        left_angle: float | None = None,
        right_angle: float | None = None,
        wiggle: bool = False,
        duration_ms: int = 500,
    ) -> dict[str, str]:
        """Set antenna positions.

        Args:
            left_angle: Left antenna angle.
            right_angle: Right antenna angle.
            wiggle: Whether to wiggle.
            duration_ms: Motion duration.

        Returns:
            Operation status.
        """
        data: dict[str, Any] = {
            "wiggle": wiggle,
            "duration_ms": duration_ms,
        }
        if left_angle is not None:
            data["left_angle"] = left_angle
        if right_angle is not None:
            data["right_angle"] = right_angle

        try:
            return await self._request("POST", "/antenna/state", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def get_sensor_data(
        self,
        sensors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get sensor readings.

        Args:
            sensors: List of sensors to read.

        Returns:
            Sensor data dictionary.
        """
        if sensors is None:
            sensors = ["all"]

        params = {"sensors": ",".join(sensors)}

        try:
            client = await self._get_client()
            response = await client.get("/sensors", params=params)
            response.raise_for_status()
            return response.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
            return {"status": "error", "message": str(e)}

    async def look_at_sound(
        self,
        timeout_ms: int = 2000,
    ) -> dict[str, str]:
        """Turn toward detected sound.

        Args:
            timeout_ms: Detection timeout.

        Returns:
            Operation status and direction.
        """
        data = {"timeout_ms": timeout_ms}

        try:
            return await self._request("POST", "/audio/look_at_sound", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def dance(
        self,
        routine: str,
        duration_seconds: float = 5.0,
    ) -> dict[str, str]:
        """Execute a dance routine.

        Args:
            routine: Dance routine name.
            duration_seconds: Dance duration.

        Returns:
            Operation status.
        """
        data = {
            "routine": routine,
            "duration_seconds": duration_seconds,
        }

        try:
            return await self._request("POST", "/expression/dance", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    # ========== NEW TOOLS FOR FULL SDK SUPPORT ==========

    async def rotate(
        self,
        direction: str,
        degrees: float = 90.0,
        speed: str = "normal",
    ) -> dict[str, str]:
        """Rotate the robot's body.

        Args:
            direction: Rotation direction (left, right).
            degrees: Rotation angle in degrees (0-360).
            speed: Rotation speed (slow, normal, fast).

        Returns:
            Operation status.
        """
        data = {
            "direction": direction,
            "degrees": degrees,
            "speed": speed,
        }

        try:
            return await self._request("POST", "/body/rotate", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def look_at(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        z: float = 0.0,
        duration: float = 1.0,
    ) -> dict[str, str]:
        """Position head with precise angles.

        Args:
            roll: Roll angle in degrees (-45 to 45).
            pitch: Pitch angle in degrees (-45 to 45).
            yaw: Yaw angle in degrees (-45 to 45).
            z: Vertical offset in mm (-50 to 50).
            duration: Movement duration in seconds.

        Returns:
            Operation status.
        """
        data = {
            "roll": roll,
            "pitch": pitch,
            "yaw": yaw,
            "z": z,
            "duration": duration,
        }

        try:
            return await self._request("POST", "/head/look_at", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def listen(
        self,
        duration_seconds: float = 3.0,
    ) -> dict[str, Any]:
        """Capture audio from microphones.

        Args:
            duration_seconds: Recording duration in seconds.

        Returns:
            Audio data as base64 encoded string.
        """
        data = {"duration_seconds": duration_seconds}

        try:
            return await self._request("POST", "/audio/listen", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def wake_up(self) -> dict[str, str]:
        """Initialize robot motors and prepare for operation.

        Returns:
            Operation status.
        """
        try:
            return await self._request("POST", "/lifecycle/wake_up")
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def sleep(self) -> dict[str, str]:
        """Power down motors and enter sleep mode.

        Returns:
            Operation status.
        """
        try:
            return await self._request("POST", "/lifecycle/sleep")
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def nod(
        self,
        times: int = 2,
        speed: str = "normal",
    ) -> dict[str, str]:
        """Perform nodding gesture (agreement).

        Args:
            times: Number of nods.
            speed: Nod speed (slow, normal, fast).

        Returns:
            Operation status.
        """
        data = {"times": times, "speed": speed}

        try:
            return await self._request("POST", "/gesture/nod", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def shake(
        self,
        times: int = 2,
        speed: str = "normal",
    ) -> dict[str, str]:
        """Perform head shake gesture (disagreement).

        Args:
            times: Number of shakes.
            speed: Shake speed (slow, normal, fast).

        Returns:
            Operation status.
        """
        data = {"times": times, "speed": speed}

        try:
            return await self._request("POST", "/gesture/shake", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def rest(self) -> dict[str, str]:
        """Return to neutral resting pose.

        Returns:
            Operation status.
        """
        try:
            return await self._request("POST", "/gesture/rest")
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}
