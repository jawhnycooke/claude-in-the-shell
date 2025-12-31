"""Reachy Daemon Client - HTTP client for Reachy hardware control.

Communicates with the Reachy Daemon (FastAPI server on localhost:8000)
provided by Pollen Robotics to control the physical robot.

Supports two backend modes:
1. Real reachy-mini daemon API (official Pollen Robotics)
2. Mock daemon API (for development/testing without hardware)

The client auto-detects which backend is running and adapts accordingly.
"""

from __future__ import annotations

import asyncio
import math
from enum import Enum
from typing import Any

import httpx

from reachy_agent.emotions.loader import EmotionLoader, get_emotion_loader
from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


def deg_to_rad(degrees: float) -> float:
    """Convert degrees to radians for MuJoCo API."""
    return degrees * math.pi / 180.0


def rad_to_deg(radians: float) -> float:
    """Convert radians to degrees for human-readable output."""
    return radians * 180.0 / math.pi


class DaemonBackend(str, Enum):
    """Backend type for the daemon."""

    REAL = "real"  # Official reachy-mini daemon
    MOCK = "mock"  # Development mock daemon
    UNKNOWN = "unknown"


class ReachyDaemonError(Exception):
    """Exception raised when daemon communication fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ReachyDaemonClient:
    """HTTP client for communicating with the Reachy Daemon.

    The Reachy Daemon is a FastAPI server provided by Pollen Robotics
    that controls the physical robot hardware. This client supports both
    the official reachy-mini daemon and the mock daemon for development.

    The client auto-detects the backend type on first connection and adapts
    API calls accordingly.
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
        self._backend: DaemonBackend = DaemonBackend.UNKNOWN

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

    async def detect_backend(self) -> DaemonBackend:
        """Detect which backend (real or mock) is running.

        Checks for distinguishing characteristics in the status response
        to determine if this is the real reachy-mini daemon or our mock.

        Returns:
            The detected backend type.
        """
        if self._backend != DaemonBackend.UNKNOWN:
            return self._backend

        try:
            status = await self.get_status()

            # Check if get_status returned an error response (not a real status)
            # This can happen if the daemon isn't fully ready yet
            if status.get("status") == "error":
                log.warning(
                    "Backend detection deferred - daemon returned error",
                    message=status.get("message"),
                )
                # Don't cache - allow retry on next call
                return DaemonBackend.UNKNOWN

            # Mock daemon includes "connection_type": "simulator" or "mock"
            # Real daemon includes "robot_name" and different structure
            if status.get("connection_type") in ("simulator", "mock"):
                self._backend = DaemonBackend.MOCK
            elif "robot_name" in status or "state" in status:
                self._backend = DaemonBackend.REAL
            else:
                # Default to mock for development - but don't cache if unsure
                log.warning(
                    "Backend detection uncertain - defaulting to mock (not cached)",
                    status_keys=list(status.keys()),
                )
                return DaemonBackend.MOCK

            log.info("Detected daemon backend", backend=self._backend.value)
        except ReachyDaemonError:
            self._backend = DaemonBackend.UNKNOWN

        return self._backend

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

    async def set_target(
        self,
        head_pose: dict[str, float] | None = None,
        body_yaw: float | None = None,
        antennas: list[float] | None = None,
    ) -> dict[str, str]:
        """Set target pose using smooth direct control (no snapping).

        This is the preferred method for smooth movements on the real daemon.
        Unlike `goto`, this doesn't snap to default x/y/z=0 positions.

        Args:
            head_pose: Head orientation {roll, pitch, yaw} in radians.
            body_yaw: Body rotation in radians.
            antennas: Antenna positions [left, right] in radians.

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            data: dict[str, Any] = {}
            if head_pose is not None:
                data["target_head_pose"] = head_pose
            if body_yaw is not None:
                data["target_body_yaw"] = body_yaw
            if antennas is not None:
                data["target_antennas"] = antennas

            try:
                result = await self._request("POST", "/api/move/set_target", json_data=data)
                return {"status": result.get("status", "ok")}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon doesn't have set_target, use the existing endpoints
            return {"status": "error", "message": "set_target only available on real daemon"}

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
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon uses /api/move/set_target for smooth movements
            # Map direction to yaw/pitch angles (in degrees, will convert to radians)
            angle = degrees if degrees is not None else 20.0  # Default 20 degrees
            yaw_deg = 0.0
            pitch_deg = 0.0

            direction_lower = direction.lower()
            if direction_lower == "left":
                yaw_deg = angle
            elif direction_lower == "right":
                yaw_deg = -angle
            elif direction_lower == "up":
                # reachy-mini uses negative pitch for looking up
                pitch_deg = -angle
            elif direction_lower == "down":
                # reachy-mini uses positive pitch for looking down
                pitch_deg = angle
            elif direction_lower == "front":
                yaw_deg = 0.0
                pitch_deg = 0.0

            log.debug(
                "move_head: using set_target for smooth movement",
                direction=direction,
                yaw_deg=yaw_deg,
                pitch_deg=pitch_deg,
                yaw_rad=deg_to_rad(yaw_deg),
                pitch_rad=deg_to_rad(pitch_deg),
            )

            # Use set_target for smooth movements (no snapping to x/y/z=0)
            head_pose = {
                "roll": 0.0,
                "pitch": deg_to_rad(pitch_deg),
                "yaw": deg_to_rad(yaw_deg),
            }

            try:
                result = await self._request(
                    "POST", "/api/move/set_target", json_data={"target_head_pose": head_pose}
                )
                return {"status": "success", "result": str(result.get("status", "ok"))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /head/move
            data_mock: dict[str, str | float] = {
                "direction": direction,
                "speed": speed,
            }
            if degrees is not None:
                data_mock["degrees"] = degrees

            try:
                return await self._request("POST", "/head/move", json_data=data_mock)
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}

    # Emotion mappings from expressions.yaml (head angles in degrees, antennas in degrees)
    # These are used for the REAL daemon which doesn't have /expression/emotion endpoint
    EMOTION_MAPPINGS: dict[str, dict[str, Any]] = {
        "neutral": {
            "head": {"pitch": 0, "yaw": 0, "roll": 0},
            "antennas": {"left": 45, "right": 45},
            "duration_ms": 500,
        },
        "curious": {
            "head": {"pitch": 5, "yaw": 15, "roll": 10},
            "antennas": {"left": 55, "right": 70},
            "duration_ms": 800,
        },
        "uncertain": {
            "head": {"pitch": -5, "yaw": -10, "roll": -8},
            "antennas": {"left": 35, "right": 50},
            "duration_ms": 1000,
        },
        "recognition": {
            "head": {"pitch": 8, "yaw": 0, "roll": 0},
            "antennas": {"left": 70, "right": 70},
            "duration_ms": 600,
        },
        "joy": {
            "head": {"pitch": 10, "yaw": 0, "roll": 5},
            "antennas": {"left": 75, "right": 75},
            "duration_ms": 1200,
        },
        "happy": {  # Alias for joy
            "head": {"pitch": 10, "yaw": 0, "roll": 5},
            "antennas": {"left": 75, "right": 75},
            "duration_ms": 1200,
        },
        "thinking": {
            "head": {"pitch": 5, "yaw": 20, "roll": 5},
            "antennas": {"left": 50, "right": 40},
            "duration_ms": 2000,
        },
        "listening": {
            "head": {"pitch": 3, "yaw": 0, "roll": 0},
            "antennas": {"left": 60, "right": 60},
            "duration_ms": 500,
        },
        "agreeing": {
            "head": {"pitch": 10, "yaw": 0, "roll": 0},
            "antennas": {"left": 65, "right": 65},
            "duration_ms": 400,
        },
        "disagreeing": {
            "head": {"pitch": 0, "yaw": 0, "roll": 0},
            "antennas": {"left": 40, "right": 40},
            "duration_ms": 500,
        },
        "sleepy": {
            "head": {"pitch": -15, "yaw": 0, "roll": 0},
            "antennas": {"left": 20, "right": 25},
            "duration_ms": 2000,
        },
        "surprised": {
            "head": {"pitch": -5, "yaw": 0, "roll": 0},
            "antennas": {"left": 85, "right": 85},
            "duration_ms": 300,
        },
        "focused": {
            "head": {"pitch": 5, "yaw": 0, "roll": 0},
            "antennas": {"left": 50, "right": 50},
            "duration_ms": 500,
        },
        "sad": {
            "head": {"pitch": -20, "yaw": 0, "roll": -5},
            "antennas": {"left": 15, "right": 20},
            "duration_ms": 1500,
        },
        "angry": {
            "head": {"pitch": -8, "yaw": 0, "roll": 0},
            "antennas": {"left": 30, "right": 30},
            "duration_ms": 800,
        },
        "excited": {
            "head": {"pitch": 15, "yaw": 0, "roll": 0},
            "antennas": {"left": 80, "right": 80},
            "duration_ms": 1000,
        },
        "confused": {  # Alias for uncertain
            "head": {"pitch": -5, "yaw": -10, "roll": -8},
            "antennas": {"left": 35, "right": 50},
            "duration_ms": 1000,
        },
    }

    # Native SDK emotions from HuggingFace dataset: pollen-robotics/reachy-mini-emotions-library
    # These are professionally motion-captured animations with synchronized audio.
    # When available, we prefer native emotions over custom EMOTION_MAPPINGS compositions.
    EMOTIONS_DATASET = "pollen-robotics/reachy-mini-emotions-library"

    NATIVE_EMOTION_MAPPING: dict[str, str] = {
        # Direct matches
        "curious": "curious1",
        "confused": "confused1",
        "cheerful": "cheerful1",
        # Aliases mapping to native emotions
        "happy": "cheerful1",
        "joy": "cheerful1",
        "excited": "enthusiastic1",
        "sad": "downcast1",
        "surprised": "amazed1",
        "amazed": "amazed1",
        "sleepy": "exhausted1",
        "tired": "exhausted1",
        "exhausted": "exhausted1",
        "listening": "attentive1",
        "attentive": "attentive1",
        "focused": "attentive2",
        "angry": "contempt1",
        "contempt": "contempt1",
        "bored": "boredom1",
        "boredom": "boredom1",
        "fear": "fear1",
        "scared": "fear1",
        "anxious": "anxiety1",
        "anxiety": "anxiety1",
        "disgusted": "disgusted1",
        "displeased": "displeased1",
        "calming": "calming1",
        "calm": "calming1",
        "dying": "dying1",
        "electric": "electric1",
        "enthusiastic": "enthusiastic1",
        "come": "come1",
        "beckoning": "come1",
    }

    # Native dance routines from HuggingFace
    NATIVE_DANCE_MAPPING: dict[str, str] = {
        "celebrate": "dance1",
        "dance1": "dance1",
        "dance2": "dance2",
        "dance3": "dance3",
    }

    async def play_recorded_move(
        self,
        dataset: str,
        move_name: str,
    ) -> dict[str, str]:
        """Play a recorded move from a HuggingFace dataset.

        The Reachy Mini SDK supports pre-recorded moves stored on HuggingFace.
        This includes the official emotions library with 19+ emotion animations.

        Args:
            dataset: HuggingFace dataset name (e.g., "pollen-robotics/reachy-mini-emotions-library").
            move_name: Name of the move in the dataset (e.g., "curious1", "dance1").

        Returns:
            Operation status with move UUID.

        Example:
            await client.play_recorded_move(
                "pollen-robotics/reachy-mini-emotions-library",
                "curious1"
            )
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon: POST /api/move/play/recorded-move-dataset/{dataset}/{move_name}
            # URL-encode the dataset name as it contains slashes
            path = f"/api/move/play/recorded-move-dataset/{dataset}/{move_name}"
            log.info(
                "Playing recorded move from HuggingFace",
                dataset=dataset,
                move_name=move_name,
            )
            try:
                result = await self._request("POST", path)
                return {"status": "success", "uuid": str(result.get("uuid", ""))}
            except ReachyDaemonError as e:
                log.warning(
                    "Failed to play recorded move, falling back to custom",
                    dataset=dataset,
                    move_name=move_name,
                    error=str(e),
                )
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon doesn't support recorded moves
            return {
                "status": "error",
                "message": "Recorded moves only available on real daemon",
            }

    async def play_local_emotion(
        self,
        move_name: str,
        emotion_loader: EmotionLoader | None = None,
    ) -> dict[str, str]:
        """Play an emotion from local bundled data.

        Reads keyframe data from data/emotions/ and plays it via /api/move/goto.
        This enables offline emotion playback without HuggingFace downloads.

        Note:
            This method requires the REAL daemon backend. It uses /api/move/goto
            for keyframe playback because timing control is essential for animations.
            Unlike single-pose movements, keyframes specify all position values so
            the snapping issue doesn't apply here.

        Args:
            move_name: Name of the emotion move (e.g., "curious1", "cheerful1").
            emotion_loader: Optional EmotionLoader instance. If None, uses default.

        Returns:
            Operation status dict with "status" key.
        """
        # Check backend type - local playback only works with REAL daemon
        backend = await self.detect_backend()
        if backend != DaemonBackend.REAL:
            log.warning(
                "Local emotion playback requires real daemon",
                backend=backend.value,
                move_name=move_name,
            )
            return {
                "status": "error",
                "message": "Local emotion playback only available on real daemon",
            }

        loader = emotion_loader or get_emotion_loader()

        # Load emotion data
        emotion_data = loader.get_emotion(move_name)
        if emotion_data is None:
            log.warning("Local emotion not found", move_name=move_name)
            return {"status": "error", "message": f"Emotion '{move_name}' not found"}

        log.info(
            "Playing local emotion",
            move_name=move_name,
            duration_ms=emotion_data.duration_ms,
            keyframes=len(emotion_data.keyframes),
            has_audio=emotion_data.audio_file is not None,
        )

        # Play keyframes sequentially
        prev_time_ms = 0.0
        for i, kf in enumerate(emotion_data.keyframes):
            # Calculate wait time from previous keyframe
            wait_time_s = (kf.time_ms - prev_time_ms) / 1000.0
            prev_time_ms = kf.time_ms

            # Skip very short waits (under 5ms)
            if wait_time_s > 0.005:
                await asyncio.sleep(wait_time_s)

            # Build pose data - values are already in radians from the JSON
            # Use set_target for smooth keyframe playback (no snapping)
            data = {
                "target_head_pose": {
                    "roll": kf.head["roll"],
                    "pitch": kf.head["pitch"],
                    "yaw": kf.head["yaw"],
                },
                "target_antennas": kf.antennas,
            }

            try:
                await self._request("POST", "/api/move/set_target", json_data=data)
            except ReachyDaemonError as e:
                log.error(
                    "Local emotion keyframe failed",
                    move_name=move_name,
                    keyframe=i,
                    error=str(e),
                )
                return {"status": "error", "message": str(e)}

        return {"status": "success", "move_name": move_name, "source": "local"}

    async def play_emotion(
        self,
        emotion: str,
        intensity: float = 0.7,
    ) -> dict[str, str]:
        """Play an emotional expression.

        Priority order:
        1. Local bundled emotions (data/emotions/) - fastest, no network
        2. HuggingFace SDK emotions - fallback if local fails
        3. Custom EMOTION_MAPPINGS - for emotions not in the SDK

        Native emotions include synchronized audio + motion, providing
        higher quality animations tuned by Pollen Robotics.

        Args:
            emotion: Emotion to express (e.g., "curious", "happy", "thinking").
            intensity: Expression intensity (0.0 to 1.0). Note: intensity
                is only applied for custom emotions, not native SDK ones.

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()
        emotion_lower = emotion.lower()

        if backend == DaemonBackend.REAL:
            # Check for native SDK emotion mapping
            native_move = self.NATIVE_EMOTION_MAPPING.get(emotion_lower)
            if native_move:
                # Try local bundled emotion first (fastest)
                loader = get_emotion_loader()
                if loader.has_emotion(native_move):
                    log.info(
                        "Using local bundled emotion",
                        emotion=emotion,
                        native_move=native_move,
                    )
                    result = await self.play_local_emotion(native_move, loader)
                    if result.get("status") == "success":
                        return result
                    log.warning(
                        "Local emotion playback failed, trying HuggingFace",
                        emotion=emotion,
                        error=result.get("message"),
                    )

                # Fall back to HuggingFace SDK emotion
                log.info(
                    "Using HuggingFace SDK emotion",
                    emotion=emotion,
                    native_move=native_move,
                )
                result = await self.play_recorded_move(self.EMOTIONS_DATASET, native_move)
                if result.get("status") == "success":
                    return result
                # If HuggingFace also fails, fall back to custom composition
                log.warning(
                    "HuggingFace emotion failed, falling back to custom",
                    emotion=emotion,
                    error=result.get("message"),
                )

            # Fall back to custom EMOTION_MAPPINGS
            # These are used for emotions not in the SDK: thinking, neutral, agreeing, disagreeing, etc.
            emotion_data = self.EMOTION_MAPPINGS.get(emotion_lower)

            if emotion_data is None:
                log.warning(f"Unknown emotion '{emotion}', defaulting to neutral")
                emotion_data = self.EMOTION_MAPPINGS["neutral"]

            head = emotion_data["head"]
            antennas = emotion_data["antennas"]
            duration_ms = emotion_data.get("duration_ms", 1000)

            # Apply intensity scaling to head movements
            pitch_deg = head["pitch"] * intensity
            yaw_deg = head["yaw"] * intensity
            roll_deg = head["roll"] * intensity

            # Invert pitch: EMOTION_MAPPINGS uses positive = look up,
            # but reachy-mini uses negative = look up
            hardware_pitch_deg = -pitch_deg

            # Convert antenna angles from our convention to daemon convention
            # Our convention: 0° = flat/back, 90° = vertical (straight up)
            # Daemon convention: 0 rad = vertical, π/2 rad = flat/back
            def to_daemon_radians(deg: float) -> float:
                return deg_to_rad(90.0 - deg)

            left_antenna_rad = to_daemon_radians(antennas["left"])
            right_antenna_rad = to_daemon_radians(antennas["right"])

            # Use set_target for smooth custom emotion (no snapping)
            data = {
                "target_head_pose": {
                    "roll": deg_to_rad(roll_deg),
                    "pitch": deg_to_rad(hardware_pitch_deg),
                    "yaw": deg_to_rad(yaw_deg),
                },
                "target_antennas": [left_antenna_rad, right_antenna_rad],
            }
            log.debug(
                "play_emotion: using custom composition with set_target",
                emotion=emotion,
                user_pitch_deg=pitch_deg,
                hardware_pitch_deg=hardware_pitch_deg,
                yaw_deg=yaw_deg,
                roll_deg=roll_deg,
                left_antenna=antennas["left"],
                right_antenna=antennas["right"],
            )
            try:
                result = await self._request("POST", "/api/move/set_target", json_data=data)
                return {"status": "success", "result": str(result.get("status", "ok"))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /expression/emotion
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
            left_angle: Left antenna angle in degrees (0=flat/back, 90=vertical).
            right_angle: Right antenna angle in degrees (0=flat/back, 90=vertical).
            wiggle: Whether to wiggle (mock daemon only).
            duration_ms: Motion duration (mock daemon only, set_target uses smooth interpolation).

        Returns:
            Operation status.

        Note:
            The daemon API uses radians where 0=vertical and π/2=flat, which is
            inverted from our user-facing convention (0=flat, 90=vertical).
            This method handles the conversion automatically.
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon uses /api/move/set_target for smooth movements
            # Our convention: 0° = flat/back, 90° = vertical (straight up)
            # Daemon convention: 0 rad = vertical, π/2 rad = flat/back
            # Conversion: daemon_rad = (90 - our_deg) * π/180
            def to_daemon_radians(deg: float) -> float:
                """Convert our degrees (0=flat, 90=vertical) to daemon radians (0=vertical)."""
                return deg_to_rad(90.0 - deg)

            left_rad = to_daemon_radians(left_angle) if left_angle is not None else 0.0
            right_rad = to_daemon_radians(right_angle) if right_angle is not None else 0.0
            antennas = [left_rad, right_rad]
            log.debug(
                "set_antenna_state: using set_target for smooth movement",
                left_deg=left_angle,
                right_deg=right_angle,
                left_rad=left_rad,
                right_rad=right_rad,
            )
            try:
                result = await self._request(
                    "POST", "/api/move/set_target", json_data={"target_antennas": antennas}
                )
                return {"status": "success", "result": str(result.get("status", "ok"))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /antenna/state
            data_mock: dict[str, Any] = {
                "wiggle": wiggle,
                "duration_ms": duration_ms,
            }
            if left_angle is not None:
                data_mock["left_angle"] = left_angle
            if right_angle is not None:
                data_mock["right_angle"] = right_angle

            try:
                return await self._request("POST", "/antenna/state", json_data=data_mock)
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

    # Dance routine definitions: list of movement keyframes
    # Each keyframe: {head: {pitch, yaw, roll}, antennas: {left, right}, duration}
    # Note: pitch values use user convention (positive = look up)
    DANCE_ROUTINES: dict[str, list[dict[str, Any]]] = {
        "celebrate": [
            {"head": {"pitch": 15, "yaw": 0, "roll": 5}, "antennas": [80, 80], "duration": 0.4},
            {"head": {"pitch": 10, "yaw": -20, "roll": -5}, "antennas": [60, 85], "duration": 0.3},
            {"head": {"pitch": 15, "yaw": 20, "roll": 5}, "antennas": [85, 60], "duration": 0.3},
            {"head": {"pitch": 10, "yaw": -15, "roll": 0}, "antennas": [70, 90], "duration": 0.3},
            {"head": {"pitch": 15, "yaw": 15, "roll": 0}, "antennas": [90, 70], "duration": 0.3},
            {"head": {"pitch": 20, "yaw": 0, "roll": 0}, "antennas": [85, 85], "duration": 0.4},
        ],
        "greeting": [
            {"head": {"pitch": 5, "yaw": 0, "roll": 0}, "antennas": [70, 70], "duration": 0.5},
            {"head": {"pitch": 15, "yaw": 0, "roll": 5}, "antennas": [80, 80], "duration": 0.4},
            {"head": {"pitch": 10, "yaw": 0, "roll": -5}, "antennas": [75, 75], "duration": 0.4},
            {"head": {"pitch": 5, "yaw": 0, "roll": 0}, "antennas": [70, 70], "duration": 0.5},
        ],
        "thinking": [
            {"head": {"pitch": 10, "yaw": 25, "roll": 8}, "antennas": [50, 40], "duration": 0.8},
            {"head": {"pitch": 5, "yaw": -20, "roll": -5}, "antennas": [45, 55], "duration": 1.0},
            {"head": {"pitch": 8, "yaw": 15, "roll": 3}, "antennas": [55, 45], "duration": 0.8},
            {"head": {"pitch": 0, "yaw": 0, "roll": 0}, "antennas": [50, 50], "duration": 0.6},
        ],
        "custom": [
            {"head": {"pitch": 0, "yaw": -30, "roll": -10}, "antennas": [40, 80], "duration": 0.5},
            {"head": {"pitch": 10, "yaw": 30, "roll": 10}, "antennas": [80, 40], "duration": 0.5},
            {"head": {"pitch": -5, "yaw": -20, "roll": 0}, "antennas": [60, 70], "duration": 0.4},
            {"head": {"pitch": 15, "yaw": 20, "roll": 0}, "antennas": [70, 60], "duration": 0.4},
            {"head": {"pitch": 5, "yaw": 0, "roll": 0}, "antennas": [65, 65], "duration": 0.5},
        ],
    }

    async def dance(
        self,
        routine: str,
        duration_seconds: float = 5.0,
    ) -> dict[str, str]:
        """Execute a dance routine.

        Priority order:
        1. Local bundled dances (data/emotions/) - fastest, no network
        2. HuggingFace SDK dances - fallback if local fails
        3. Custom DANCE_ROUTINES - for routines not in the SDK

        Args:
            routine: Dance routine name (celebrate, dance1, dance2, dance3, greeting, thinking, custom).
            duration_seconds: Dance duration (used to scale/repeat for custom routines).

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()
        routine_lower = routine.lower()

        if backend == DaemonBackend.REAL:
            # Check for native SDK dance routine mapping
            native_dance = self.NATIVE_DANCE_MAPPING.get(routine_lower)
            if native_dance:
                # Try local bundled dance first (fastest)
                loader = get_emotion_loader()
                if loader.has_emotion(native_dance):
                    log.info(
                        "Using local bundled dance",
                        routine=routine,
                        native_dance=native_dance,
                    )
                    result = await self.play_local_emotion(native_dance, loader)
                    if result.get("status") == "success":
                        return {"status": "success", "routine": routine, "source": "local"}
                    log.warning(
                        "Local dance playback failed, trying HuggingFace",
                        routine=routine,
                        error=result.get("message"),
                    )

                # Fall back to HuggingFace SDK dance
                log.info(
                    "Using HuggingFace SDK dance routine",
                    routine=routine,
                    native_dance=native_dance,
                )
                result = await self.play_recorded_move(self.EMOTIONS_DATASET, native_dance)
                if result.get("status") == "success":
                    return {"status": "success", "routine": routine, "source": "huggingface"}
                # If HuggingFace also fails, fall back to custom composition
                log.warning(
                    "HuggingFace dance failed, falling back to custom",
                    routine=routine,
                    error=result.get("message"),
                )

            # Fall back to custom DANCE_ROUTINES
            keyframes = self.DANCE_ROUTINES.get(routine_lower)

            if keyframes is None:
                log.warning(f"Unknown dance routine '{routine}', using 'celebrate'")
                keyframes = self.DANCE_ROUTINES["celebrate"]

            # Calculate how many times to loop the routine to fill duration
            routine_duration = sum(kf["duration"] for kf in keyframes)
            loops = max(1, int(duration_seconds / routine_duration))

            log.info(
                "Executing dance routine",
                routine=routine,
                duration_seconds=duration_seconds,
                loops=loops,
            )

            for _ in range(loops):
                for kf in keyframes:
                    head = kf["head"]
                    antennas = kf["antennas"]
                    kf_duration = kf["duration"]

                    # Invert pitch for reachy-mini (positive = look up in user space)
                    hardware_pitch = -head["pitch"]

                    # Convert antenna angles from our convention to daemon convention
                    # Our convention: 0° = flat/back, 90° = vertical (straight up)
                    # Daemon convention: 0 rad = vertical, π/2 rad = flat/back
                    def to_daemon_radians(deg: float) -> float:
                        return deg_to_rad(90.0 - deg)

                    # Use set_target for smooth dance keyframe playback (no snapping)
                    data = {
                        "target_head_pose": {
                            "roll": deg_to_rad(head["roll"]),
                            "pitch": deg_to_rad(hardware_pitch),
                            "yaw": deg_to_rad(head["yaw"]),
                        },
                        "target_antennas": [to_daemon_radians(antennas[0]), to_daemon_radians(antennas[1])],
                    }

                    try:
                        await self._request("POST", "/api/move/set_target", json_data=data)
                        # Wait for the movement to complete before next keyframe
                        await asyncio.sleep(kf_duration)
                    except ReachyDaemonError as e:
                        log.error("Dance keyframe failed", error=str(e))
                        return {"status": "error", "message": str(e)}

            return {"status": "success", "routine": routine, "loops": str(loops)}
        else:
            # Mock daemon uses /expression/dance
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
            speed: Rotation speed (slow, normal, fast). Note: set_target uses smooth interpolation.

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon uses /api/move/set_target for smooth movements
            # Convert direction and degrees to body_yaw in radians
            # Positive yaw = rotate left, negative yaw = rotate right
            yaw_deg = degrees if direction.lower() == "left" else -degrees
            yaw_rad = deg_to_rad(yaw_deg)

            log.debug(
                "rotate: using set_target for smooth movement",
                direction=direction,
                degrees=degrees,
                yaw_rad=yaw_rad,
            )
            try:
                result = await self._request(
                    "POST", "/api/move/set_target", json_data={"target_body_yaw": yaw_rad}
                )
                return {"status": "success", "result": str(result.get("status", "ok"))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /body/rotate
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
            pitch: Pitch angle in degrees (-45 to 45). Positive = look up.
            yaw: Yaw angle in degrees (-45 to 45). Positive = look left.
            z: Vertical offset in mm (-50 to 50). Note: z is ignored with set_target.
            duration: Movement duration in seconds. Note: set_target uses smooth interpolation.

        Note:
            The user-facing convention is positive pitch = look UP.
            Internally, reachy-mini uses negative pitch = look UP,
            so we invert pitch when sending to the daemon.

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()

        # Convert user-facing pitch convention (positive = up) to
        # reachy-mini convention (negative = up)
        hardware_pitch = -pitch

        if backend == DaemonBackend.REAL:
            # Real daemon uses /api/move/set_target for smooth movements
            # MuJoCo expects angles in RADIANS, convert from degrees
            head_pose = {
                "roll": deg_to_rad(roll),
                "pitch": deg_to_rad(hardware_pitch),
                "yaw": deg_to_rad(yaw),
            }
            log.debug(
                "look_at: using set_target for smooth movement",
                roll_deg=roll,
                pitch_deg_user=pitch,
                pitch_deg_hardware=hardware_pitch,
                yaw_deg=yaw,
                roll_rad=deg_to_rad(roll),
                pitch_rad_hardware=deg_to_rad(hardware_pitch),
                yaw_rad=deg_to_rad(yaw),
            )
            try:
                result = await self._request(
                    "POST", "/api/move/set_target", json_data={"target_head_pose": head_pose}
                )
                return {"status": "success", "result": str(result.get("status", "ok"))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /head/look_at
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

    async def set_full_pose(
        self,
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        left_antenna: float = 90.0,
        right_antenna: float = 90.0,
    ) -> dict[str, str]:
        """Set head pose and antenna positions in a single API call.

        This is optimized for the blend controller to send complete poses
        atomically, avoiding issues where separate calls reset each other's
        targets.

        Args:
            roll: Roll angle in degrees (-45 to 45).
            pitch: Pitch angle in degrees (-45 to 45). Positive = look up.
            yaw: Yaw angle in degrees (-45 to 45). Positive = look left.
            left_antenna: Left antenna angle in degrees (0=flat/back, 90=vertical).
            right_antenna: Right antenna angle in degrees (0=flat/back, 90=vertical).

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()

        # Convert user-facing pitch convention (positive = up) to
        # reachy-mini convention (negative = up)
        hardware_pitch = -pitch

        if backend == DaemonBackend.REAL:
            # Convert head angles from degrees to radians
            head_pose = {
                "roll": deg_to_rad(roll),
                "pitch": deg_to_rad(hardware_pitch),
                "yaw": deg_to_rad(yaw),
            }

            # Convert antenna angles from our convention to daemon convention
            # Our convention: 0° = flat/back, 90° = vertical (straight up)
            # Daemon convention: 0 rad = vertical, π/2 rad = flat/back
            def to_daemon_radians(deg: float) -> float:
                return deg_to_rad(90.0 - deg)

            antennas = [to_daemon_radians(left_antenna), to_daemon_radians(right_antenna)]

            # Send both head pose and antennas in a single request
            data = {
                "target_head_pose": head_pose,
                "target_antennas": antennas,
            }

            try:
                result = await self._request("POST", "/api/move/set_target", json_data=data)
                return {"status": "success", "result": str(result.get("status", "ok"))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon: fall back to separate calls
            await self.look_at(roll=roll, pitch=pitch, yaw=yaw)
            return await self.set_antenna_state(
                left_angle=left_antenna, right_angle=right_antenna
            )

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
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon uses /api/move/play/wake_up
            try:
                result = await self._request("POST", "/api/move/play/wake_up")
                return {"status": "success", "uuid": str(result.get("uuid", ""))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /lifecycle/wake_up
            try:
                return await self._request("POST", "/lifecycle/wake_up")
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}

    async def sleep(self) -> dict[str, str]:
        """Power down motors and enter sleep mode.

        Returns:
            Operation status.
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon uses /api/move/play/goto_sleep
            try:
                result = await self._request("POST", "/api/move/play/goto_sleep")
                return {"status": "success", "uuid": str(result.get("uuid", ""))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /lifecycle/sleep
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
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon: implement nod using set_target for smooth movement
            # Nod = pitch up, then down, back to center
            speed_delays = {"slow": 0.4, "normal": 0.25, "fast": 0.15}
            delay = speed_delays.get(speed, 0.25)
            pitch_angle = 0.3  # ~17 degrees in radians

            log.debug("nod: using set_target for smooth gesture", times=times, speed=speed)
            try:
                for _ in range(times):
                    # Pitch down (look down = negative pitch for hardware)
                    await self._request(
                        "POST",
                        "/api/move/set_target",
                        json_data={"target_head_pose": {"pitch": pitch_angle}},
                    )
                    await asyncio.sleep(delay)
                    # Pitch up (look up)
                    await self._request(
                        "POST",
                        "/api/move/set_target",
                        json_data={"target_head_pose": {"pitch": -pitch_angle}},
                    )
                    await asyncio.sleep(delay)
                # Return to center
                await self._request(
                    "POST",
                    "/api/move/set_target",
                    json_data={"target_head_pose": {"pitch": 0}},
                )
                return {"status": "success", "gesture": "nod", "times": str(times)}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /gesture/nod
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
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon: implement shake using set_target for smooth movement
            # Shake = yaw left, then right, back to center
            speed_delays = {"slow": 0.35, "normal": 0.2, "fast": 0.12}
            delay = speed_delays.get(speed, 0.2)
            yaw_angle = 0.35  # ~20 degrees in radians

            log.debug("shake: using set_target for smooth gesture", times=times, speed=speed)
            try:
                for _ in range(times):
                    # Turn left (positive yaw)
                    await self._request(
                        "POST",
                        "/api/move/set_target",
                        json_data={"target_head_pose": {"yaw": yaw_angle}},
                    )
                    await asyncio.sleep(delay)
                    # Turn right (negative yaw)
                    await self._request(
                        "POST",
                        "/api/move/set_target",
                        json_data={"target_head_pose": {"yaw": -yaw_angle}},
                    )
                    await asyncio.sleep(delay)
                # Return to center
                await self._request(
                    "POST",
                    "/api/move/set_target",
                    json_data={"target_head_pose": {"yaw": 0}},
                )
                return {"status": "success", "gesture": "shake", "times": str(times)}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon uses /gesture/shake
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

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive robot status.

        Returns:
            Robot status including position, motor states, temperature, etc.
        """
        try:
            return await self._request("GET", "/api/daemon/status")
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def cancel_action(
        self,
        action_id: str | None = None,
        all_actions: bool = False,
    ) -> dict[str, str]:
        """Cancel running actions.

        Args:
            action_id: Specific action ID to cancel (optional).
            all_actions: If True, cancel all running actions.

        Returns:
            Operation status with cancelled action count.
        """
        data: dict[str, Any] = {}
        if action_id:
            data["action_id"] = action_id
        if all_actions:
            data["all_actions"] = True

        try:
            return await self._request("POST", "/actions/cancel", json_data=data)
        except ReachyDaemonError as e:
            return {"status": "error", "message": str(e)}

    async def look_at_world(
        self,
        x: float,
        y: float,
        z: float,
        duration: float = 1.0,
    ) -> dict[str, str]:
        """Look at a 3D point in world coordinates.

        Orients the head to gaze at a specific point in 3D space.
        This is useful for spatial awareness tasks like "look at where
        the sound came from" or "look at the detected object".

        Args:
            x: X coordinate in meters (positive = right of robot).
            y: Y coordinate in meters (positive = forward/in front of robot).
            z: Z coordinate in meters (positive = up).
            duration: Movement duration in seconds.

        Returns:
            Operation status.

        Example:
            # Look at a point 1 meter in front and 0.5m to the left
            await client.look_at_world(x=-0.5, y=1.0, z=0.3, duration=1.0)
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon: POST /api/kinematics/look_at_world
            # Note: This endpoint computes inverse kinematics to orient the head
            data = {
                "x": x,
                "y": y,
                "z": z,
                "duration": duration,
            }
            log.info(
                "Looking at world coordinates",
                x=x,
                y=y,
                z=z,
                duration=duration,
            )
            try:
                result = await self._request(
                    "POST", "/api/kinematics/look_at_world", json_data=data
                )
                return {"status": "success", "uuid": str(result.get("uuid", ""))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon doesn't support this
            return {
                "status": "error",
                "message": "look_at_world only available on real daemon",
            }

    async def look_at_pixel(
        self,
        u: int,
        v: int,
        duration: float = 1.0,
    ) -> dict[str, str]:
        """Look at a pixel coordinate in the camera image.

        Orients the head to center the camera view on a specific pixel.
        This is extremely useful for visual tracking tasks like "look at
        the detected face" or "center on the object of interest".

        Args:
            u: Horizontal pixel coordinate (0 = left edge of image).
            v: Vertical pixel coordinate (0 = top edge of image).
            duration: Movement duration in seconds.

        Returns:
            Operation status.

        Example:
            # Look at the center of a 640x480 image
            await client.look_at_pixel(u=320, v=240, duration=0.5)
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon: POST /api/kinematics/look_at_pixel
            # Maps to SDK look_at_image() which takes pixel coordinates
            data = {
                "u": u,
                "v": v,
                "duration": duration,
            }
            log.info(
                "Looking at pixel coordinates",
                u=u,
                v=v,
                duration=duration,
            )
            try:
                result = await self._request(
                    "POST", "/api/kinematics/look_at_pixel", json_data=data
                )
                return {"status": "success", "uuid": str(result.get("uuid", ""))}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon doesn't support this
            return {
                "status": "error",
                "message": "look_at_pixel only available on real daemon",
            }

    async def set_motor_mode(
        self,
        mode: str,
    ) -> dict[str, str]:
        """Set the motor control mode.

        Controls motor torque and behavior. Essential for safety and
        teaching mode where the robot can be physically manipulated.

        Args:
            mode: Motor mode to set:
                - "enabled": Motors powered and holding position (normal operation)
                - "disabled": Motors powered off, robot can be moved by hand
                - "gravity_compensation": Motors compensate for gravity only,
                  allowing smooth manual positioning while preventing collapse

        Returns:
            Operation status.

        Example:
            # Enable teaching mode for manual positioning
            await client.set_motor_mode("gravity_compensation")

            # Return to normal operation
            await client.set_motor_mode("enabled")
        """
        valid_modes = ["enabled", "disabled", "gravity_compensation"]
        if mode not in valid_modes:
            return {"status": "error", "message": f"Invalid mode. Must be one of: {valid_modes}"}

        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon: POST /api/motors/set_mode/{mode}
            log.info("Setting motor mode", mode=mode)
            try:
                await self._request("POST", f"/api/motors/set_mode/{mode}")
                return {"status": "success", "mode": mode}
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon doesn't support this
            return {
                "status": "error",
                "message": "set_motor_mode only available on real daemon",
            }

    async def get_current_pose(self) -> dict[str, Any]:
        """Get the robot's current pose (proprioceptive feedback).

        Returns the actual current position of the head, body, and antennas,
        allowing the agent to verify movements and understand its physical state.

        Returns:
            Dictionary containing:
            - head: {roll, pitch, yaw} in degrees (-45 to 45 typical range)
            - body_yaw: Body rotation in degrees
            - antennas: {left, right} angles in degrees (0-90)
            - timestamp: ISO timestamp of the reading
            - status: "success" or "error"

        For the REAL daemon, this queries the actual MuJoCo simulation state.
        For the MOCK daemon, this returns the last commanded position.
        """
        backend = await self.detect_backend()

        if backend == DaemonBackend.REAL:
            # Real daemon has dedicated state endpoints that return actual positions
            try:
                full_state = await self._request("GET", "/api/state/full")

                # Extract head pose (daemon returns radians, convert to degrees)
                head_pose = full_state.get("head_pose", {})
                roll_rad = head_pose.get("roll", 0.0)
                pitch_rad = head_pose.get("pitch", 0.0)
                yaw_rad = head_pose.get("yaw", 0.0)

                # Extract body yaw (single float in radians)
                body_yaw_rad = full_state.get("body_yaw", 0.0)

                # Extract antenna positions (array of 2 floats in radians)
                antennas_rad = full_state.get("antennas_position", [0.0, 0.0])
                left_antenna_rad = antennas_rad[0] if len(antennas_rad) > 0 else 0.0
                right_antenna_rad = antennas_rad[1] if len(antennas_rad) > 1 else 0.0

                # Convert to degrees for human-readable output
                result = {
                    "status": "success",
                    "head": {
                        "roll": round(rad_to_deg(roll_rad), 1),
                        "pitch": round(rad_to_deg(pitch_rad), 1),
                        "yaw": round(rad_to_deg(yaw_rad), 1),
                    },
                    "body_yaw": round(rad_to_deg(body_yaw_rad), 1),
                    "antennas": {
                        "left": round(rad_to_deg(left_antenna_rad), 1),
                        "right": round(rad_to_deg(right_antenna_rad), 1),
                    },
                    "timestamp": full_state.get("timestamp", ""),
                    "control_mode": full_state.get("control_mode", "unknown"),
                }

                log.debug(
                    "get_current_pose: retrieved state from real daemon",
                    head_roll_deg=result["head"]["roll"],
                    head_pitch_deg=result["head"]["pitch"],
                    head_yaw_deg=result["head"]["yaw"],
                    left_antenna_deg=result["antennas"]["left"],
                    right_antenna_deg=result["antennas"]["right"],
                )

                return result

            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
        else:
            # Mock daemon - use /pose endpoint which tracks commanded positions
            try:
                return await self._request("GET", "/pose")
            except ReachyDaemonError as e:
                return {"status": "error", "message": str(e)}
