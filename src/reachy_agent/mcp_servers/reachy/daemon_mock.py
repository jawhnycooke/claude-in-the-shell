"""Mock Reachy Daemon for development and testing.

Provides a FastAPI server that mimics the Reachy Daemon API,
allowing development without physical hardware.
"""

from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, Field

# Optional FastAPI import - only used when running the mock server
try:
    from fastapi import FastAPI, Query
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


class HeadMoveRequest(BaseModel):
    """Request model for head movement."""

    direction: str
    speed: str = "normal"
    degrees: float | None = None


class EmotionRequest(BaseModel):
    """Request model for emotion expression."""

    emotion: str
    intensity: float = Field(default=0.7, ge=0.1, le=1.0)


class SpeakRequest(BaseModel):
    """Request model for speech."""

    text: str
    voice: str = "default"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class CaptureRequest(BaseModel):
    """Request model for image capture."""

    analyze: bool = False
    save: bool = False


class AntennaRequest(BaseModel):
    """Request model for antenna control."""

    left_angle: float | None = None
    right_angle: float | None = None
    wiggle: bool = False
    duration_ms: int = 500


class LookAtSoundRequest(BaseModel):
    """Request model for sound localization."""

    timeout_ms: int = 2000


class DanceRequest(BaseModel):
    """Request model for dance routine."""

    routine: str
    duration_seconds: float = 5.0


class RotateRequest(BaseModel):
    """Request model for body rotation."""

    direction: str
    degrees: float = 90.0
    speed: str = "normal"


class LookAtRequest(BaseModel):
    """Request model for precise head positioning."""

    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    z: float = 0.0
    duration: float = 1.0


class ListenRequest(BaseModel):
    """Request model for audio capture."""

    duration_seconds: float = 3.0


class GestureRequest(BaseModel):
    """Request model for gestures (nod/shake)."""

    times: int = 2
    speed: str = "normal"


class MockDaemonState:
    """Simulated state of the robot."""

    def __init__(self) -> None:
        self.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "z": 0.0}
        self.body_rotation = 0.0
        self.left_antenna_angle = 45.0
        self.right_antenna_angle = 45.0
        self.current_emotion: str | None = None
        self.is_speaking = False
        self.is_dancing = False
        self.is_awake = True
        self.is_listening = False


# Global mock state
_mock_state = MockDaemonState()


def create_mock_daemon_app() -> Any:
    """Create the mock daemon FastAPI application.

    Returns:
        FastAPI application instance.

    Raises:
        ImportError: If FastAPI is not installed.
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is required for the mock daemon. "
            "Install with: pip install fastapi uvicorn"
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Reset state on startup."""
        global _mock_state
        _mock_state = MockDaemonState()
        yield

    app = FastAPI(
        title="Reachy Mock Daemon",
        description="Mock daemon for development without hardware",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Check daemon health."""
        return {"status": "healthy", "mode": "mock"}

    @app.post("/head/move")
    async def move_head(request: HeadMoveRequest) -> dict[str, Any]:
        """Simulate head movement."""
        # Simulate movement delay based on speed
        delay_map = {"slow": 0.5, "normal": 0.3, "fast": 0.1}
        await asyncio.sleep(delay_map.get(request.speed, 0.3))

        # Update simulated position
        degrees = request.degrees or 20.0
        direction_map = {
            "left": ("yaw", -degrees),
            "right": ("yaw", degrees),
            "up": ("pitch", -degrees),
            "down": ("pitch", degrees),
            "front": ("yaw", 0.0),
        }

        if request.direction in direction_map:
            axis, value = direction_map[request.direction]
            if request.direction == "front":
                _mock_state.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0}
            else:
                _mock_state.head_position[axis] = value

        return {
            "status": "success",
            "position": _mock_state.head_position,
            "message": f"Head moved {request.direction}",
        }

    @app.post("/expression/emotion")
    async def play_emotion(request: EmotionRequest) -> dict[str, Any]:
        """Simulate emotional expression."""
        # Simulate expression duration
        await asyncio.sleep(0.5 * request.intensity)

        _mock_state.current_emotion = request.emotion

        return {
            "status": "success",
            "emotion": request.emotion,
            "intensity": request.intensity,
            "message": f"Expressing {request.emotion}",
        }

    @app.post("/audio/speak")
    async def speak(request: SpeakRequest) -> dict[str, Any]:
        """Simulate speech output."""
        # Estimate speech duration (rough: 5 chars per second)
        base_duration = len(request.text) / 5.0
        duration = base_duration / request.speed

        _mock_state.is_speaking = True
        await asyncio.sleep(min(duration, 2.0))  # Cap at 2s for testing
        _mock_state.is_speaking = False

        return {
            "status": "success",
            "text": request.text,
            "duration_seconds": duration,
            "message": "Speech completed",
        }

    @app.post("/camera/capture")
    async def capture_image(request: CaptureRequest) -> dict[str, Any]:
        """Simulate image capture."""
        await asyncio.sleep(0.1)  # Simulate capture delay

        result: dict[str, Any] = {
            "status": "success",
            "width": 640,
            "height": 480,
            "format": "jpeg",
        }

        if request.analyze:
            # Simulate vision analysis
            await asyncio.sleep(0.5)
            result["analysis"] = {
                "objects_detected": ["desk", "computer", "person"],
                "faces_detected": 1,
                "description": "A person sitting at a desk with a computer",
            }

        if request.save:
            result["saved_path"] = "/tmp/reachy_capture_mock.jpg"

        return result

    @app.post("/antenna/state")
    async def set_antenna_state(request: AntennaRequest) -> dict[str, Any]:
        """Simulate antenna control."""
        await asyncio.sleep(request.duration_ms / 1000.0)

        if request.left_angle is not None:
            _mock_state.left_antenna_angle = request.left_angle
        if request.right_angle is not None:
            _mock_state.right_antenna_angle = request.right_angle

        return {
            "status": "success",
            "left_angle": _mock_state.left_antenna_angle,
            "right_angle": _mock_state.right_antenna_angle,
            "wiggle": request.wiggle,
        }

    @app.get("/sensors")
    async def get_sensors(
        sensors: str = Query(default="all"),
    ) -> dict[str, Any]:
        """Simulate sensor readings."""
        sensor_list = sensors.split(",")

        result: dict[str, Any] = {"status": "success"}

        if "all" in sensor_list or "imu" in sensor_list:
            result["imu"] = {
                "acceleration": {
                    "x": random.uniform(-0.1, 0.1),
                    "y": random.uniform(-0.1, 0.1),
                    "z": 9.8 + random.uniform(-0.1, 0.1),
                },
                "gyroscope": {
                    "x": random.uniform(-1, 1),
                    "y": random.uniform(-1, 1),
                    "z": random.uniform(-1, 1),
                },
            }

        if "all" in sensor_list or "audio_level" in sensor_list:
            result["audio_level"] = {
                "level_db": random.uniform(-60, -20),
                "is_speech_detected": random.random() > 0.7,
            }

        if "all" in sensor_list or "temperature" in sensor_list:
            result["temperature"] = {
                "cpu_celsius": 45.0 + random.uniform(-5, 10),
                "ambient_celsius": 22.0 + random.uniform(-2, 2),
            }

        return result

    @app.post("/audio/look_at_sound")
    async def look_at_sound(request: LookAtSoundRequest) -> dict[str, Any]:
        """Simulate sound localization."""
        # Simulate listening period
        await asyncio.sleep(min(request.timeout_ms / 1000.0, 1.0))

        # Randomly determine if sound was detected
        if random.random() > 0.3:
            direction = random.choice(["left", "right", "front"])
            angle = random.uniform(10, 45) * (1 if direction == "right" else -1)

            return {
                "status": "success",
                "sound_detected": True,
                "direction": direction,
                "angle_degrees": angle,
                "confidence": random.uniform(0.7, 0.95),
            }
        else:
            return {
                "status": "success",
                "sound_detected": False,
                "message": "No significant sound detected",
            }

    @app.post("/expression/dance")
    async def dance(request: DanceRequest) -> dict[str, Any]:
        """Simulate dance routine."""
        _mock_state.is_dancing = True

        # Simulate dance duration (capped for testing)
        await asyncio.sleep(min(request.duration_seconds, 2.0))

        _mock_state.is_dancing = False

        return {
            "status": "success",
            "routine": request.routine,
            "duration_seconds": request.duration_seconds,
            "message": f"Completed {request.routine} dance",
        }

    # ========== NEW ENDPOINTS FOR FULL SDK SUPPORT ==========

    @app.post("/body/rotate")
    async def rotate(request: RotateRequest) -> dict[str, Any]:
        """Simulate body rotation."""
        delay_map = {"slow": 0.5, "normal": 0.3, "fast": 0.1}
        await asyncio.sleep(delay_map.get(request.speed, 0.3))

        # Update rotation (accumulate, wrap at 360)
        delta = request.degrees if request.direction == "right" else -request.degrees
        _mock_state.body_rotation = (_mock_state.body_rotation + delta) % 360

        return {
            "status": "success",
            "direction": request.direction,
            "degrees": request.degrees,
            "current_rotation": _mock_state.body_rotation,
            "message": f"Rotated {request.direction} by {request.degrees} degrees",
        }

    @app.post("/head/look_at")
    async def look_at(request: LookAtRequest) -> dict[str, Any]:
        """Simulate precise head positioning."""
        await asyncio.sleep(request.duration)

        _mock_state.head_position = {
            "pitch": request.pitch,
            "yaw": request.yaw,
            "roll": request.roll,
            "z": request.z,
        }

        return {
            "status": "success",
            "position": _mock_state.head_position,
            "duration": request.duration,
            "message": "Head positioned",
        }

    @app.post("/audio/listen")
    async def listen(request: ListenRequest) -> dict[str, Any]:
        """Simulate audio capture."""
        _mock_state.is_listening = True

        # Simulate recording (capped for testing)
        await asyncio.sleep(min(request.duration_seconds, 1.0))

        _mock_state.is_listening = False

        # Return mock audio data (base64-encoded silence)
        import base64

        # Generate mock audio header (WAV format indicator)
        mock_audio = base64.b64encode(b"RIFF" + b"\x00" * 100).decode("utf-8")

        return {
            "status": "success",
            "duration_seconds": request.duration_seconds,
            "format": "wav",
            "sample_rate": 16000,
            "channels": 4,
            "audio_base64": mock_audio,
            "message": f"Recorded {request.duration_seconds}s of audio",
        }

    @app.post("/lifecycle/wake_up")
    async def wake_up() -> dict[str, Any]:
        """Simulate motor initialization."""
        await asyncio.sleep(0.5)  # Simulate startup time

        _mock_state.is_awake = True
        # Reset to neutral position
        _mock_state.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "z": 0.0}
        _mock_state.left_antenna_angle = 45.0
        _mock_state.right_antenna_angle = 45.0

        return {
            "status": "success",
            "is_awake": True,
            "message": "Robot motors initialized and ready",
        }

    @app.post("/lifecycle/sleep")
    async def sleep() -> dict[str, Any]:
        """Simulate motor shutdown."""
        await asyncio.sleep(0.3)  # Simulate shutdown time

        _mock_state.is_awake = False
        _mock_state.is_dancing = False
        _mock_state.is_speaking = False

        return {
            "status": "success",
            "is_awake": False,
            "message": "Robot motors powered down",
        }

    @app.post("/gesture/nod")
    async def nod(request: GestureRequest) -> dict[str, Any]:
        """Simulate nodding gesture."""
        delay_map = {"slow": 0.4, "normal": 0.25, "fast": 0.15}
        nod_delay = delay_map.get(request.speed, 0.25)

        # Simulate nodding motion
        for _ in range(request.times):
            await asyncio.sleep(nod_delay)

        return {
            "status": "success",
            "gesture": "nod",
            "times": request.times,
            "speed": request.speed,
            "message": f"Nodded {request.times} time(s)",
        }

    @app.post("/gesture/shake")
    async def shake(request: GestureRequest) -> dict[str, Any]:
        """Simulate head shake gesture."""
        delay_map = {"slow": 0.4, "normal": 0.25, "fast": 0.15}
        shake_delay = delay_map.get(request.speed, 0.25)

        # Simulate shaking motion
        for _ in range(request.times):
            await asyncio.sleep(shake_delay)

        return {
            "status": "success",
            "gesture": "shake",
            "times": request.times,
            "speed": request.speed,
            "message": f"Shook head {request.times} time(s)",
        }

    @app.post("/gesture/rest")
    async def rest() -> dict[str, Any]:
        """Simulate returning to rest pose."""
        await asyncio.sleep(0.3)

        # Reset to neutral
        _mock_state.head_position = {"pitch": 0.0, "yaw": 0.0, "roll": 0.0, "z": 0.0}
        _mock_state.left_antenna_angle = 45.0
        _mock_state.right_antenna_angle = 45.0
        _mock_state.current_emotion = None

        return {
            "status": "success",
            "position": _mock_state.head_position,
            "left_antenna": _mock_state.left_antenna_angle,
            "right_antenna": _mock_state.right_antenna_angle,
            "message": "Returned to rest pose",
        }

    return app


def run_mock_daemon(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the mock daemon server.

    Args:
        host: Host to bind to.
        port: Port to listen on.
    """
    try:
        import uvicorn
    except ImportError:
        raise ImportError(
            "uvicorn is required to run the mock daemon. "
            "Install with: pip install uvicorn"
        )

    app = create_mock_daemon_app()
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_mock_daemon()
