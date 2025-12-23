"""Reachy MCP Server - Exposes robot body control as MCP tools.

This server provides tools for controlling the Reachy Mini robot's head,
antennas, camera, and audio output. It communicates with the Reachy Daemon
running on localhost:8000.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.utils.config import ReachyConfig

log = get_logger(__name__)


def create_reachy_mcp_server(
    config: ReachyConfig | None = None,
    daemon_url: str = "http://localhost:8000",
) -> FastMCP:
    """Create and configure the Reachy MCP server.

    Args:
        config: Optional Reachy configuration.
        daemon_url: URL of the Reachy daemon API.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP("Reachy Body Control")

    # Create daemon client for hardware communication
    client = ReachyDaemonClient(base_url=daemon_url)

    @mcp.tool()
    async def move_head(
        direction: str,
        speed: str = "normal",
        degrees: float | None = None,
    ) -> dict[str, str]:
        """Move Reachy's head to look in a direction.

        Args:
            direction: Direction to look (left, right, up, down, front).
            speed: Movement speed (slow, normal, fast).
            degrees: Optional specific angle in degrees (0-45).

        Returns:
            Status of the movement operation.
        """
        valid_directions = ["left", "right", "up", "down", "front"]
        valid_speeds = ["slow", "normal", "fast"]

        if direction not in valid_directions:
            return {"error": f"Invalid direction. Must be one of: {valid_directions}"}
        if speed not in valid_speeds:
            return {"error": f"Invalid speed. Must be one of: {valid_speeds}"}
        if degrees is not None and not (0 <= degrees <= 45):
            return {"error": "Degrees must be between 0 and 45"}

        log.info("Moving head", direction=direction, speed=speed, degrees=degrees)

        result = await client.move_head(
            direction=direction,
            speed=speed,
            degrees=degrees,
        )
        return result

    @mcp.tool()
    async def play_emotion(
        emotion: str,
        intensity: float = 0.7,
    ) -> dict[str, str]:
        """Display an emotional expression through movement and antennas.

        Args:
            emotion: Emotion to express (happy, sad, curious, excited,
                    confused, thinking, surprised, tired, alert).
            intensity: Expression intensity from 0.1 to 1.0.

        Returns:
            Status of the expression operation.
        """
        valid_emotions = [
            "happy",
            "sad",
            "curious",
            "excited",
            "confused",
            "thinking",
            "surprised",
            "tired",
            "alert",
        ]

        if emotion not in valid_emotions:
            return {"error": f"Invalid emotion. Must be one of: {valid_emotions}"}
        if not (0.1 <= intensity <= 1.0):
            return {"error": "Intensity must be between 0.1 and 1.0"}

        log.info("Playing emotion", emotion=emotion, intensity=intensity)

        result = await client.play_emotion(emotion=emotion, intensity=intensity)
        return result

    @mcp.tool()
    async def speak(
        text: str,
        voice: str = "default",
        speed: float = 1.0,
    ) -> dict[str, str]:
        """Speak text aloud through Reachy's speaker.

        Args:
            text: Text to speak (max 500 characters).
            voice: Voice profile to use.
            speed: Speech speed from 0.5 to 2.0.

        Returns:
            Status of the speech operation.
        """
        if len(text) > 500:
            return {"error": "Text exceeds 500 character limit"}
        if not (0.5 <= speed <= 2.0):
            return {"error": "Speed must be between 0.5 and 2.0"}

        log.info("Speaking", text_length=len(text), voice=voice, speed=speed)

        result = await client.speak(text=text, voice=voice, speed=speed)
        return result

    @mcp.tool()
    async def capture_image(
        analyze: bool = False,
        save: bool = False,
    ) -> dict[str, str]:
        """Capture an image from Reachy's camera.

        Args:
            analyze: Whether to analyze the image content via vision model.
            save: Whether to save the image to disk.

        Returns:
            Image capture result, optionally with analysis.
        """
        log.info("Capturing image", analyze=analyze, save=save)

        result = await client.capture_image(analyze=analyze, save=save)
        return result

    @mcp.tool()
    async def set_antenna_state(
        left_angle: float | None = None,
        right_angle: float | None = None,
        wiggle: bool = False,
        duration_ms: int = 500,
    ) -> dict[str, str]:
        """Control antenna positions for expression.

        Args:
            left_angle: Left antenna angle (0-90 degrees).
            right_angle: Right antenna angle (0-90 degrees).
            wiggle: Whether to wiggle the antennas.
            duration_ms: Duration of the motion in milliseconds.

        Returns:
            Status of the antenna operation.
        """
        if left_angle is not None and not (0 <= left_angle <= 90):
            return {"error": "Left angle must be between 0 and 90"}
        if right_angle is not None and not (0 <= right_angle <= 90):
            return {"error": "Right angle must be between 0 and 90"}
        if duration_ms < 100:
            return {"error": "Duration must be at least 100ms"}

        log.info(
            "Setting antenna state",
            left_angle=left_angle,
            right_angle=right_angle,
            wiggle=wiggle,
        )

        result = await client.set_antenna_state(
            left_angle=left_angle,
            right_angle=right_angle,
            wiggle=wiggle,
            duration_ms=duration_ms,
        )
        return result

    @mcp.tool()
    async def get_sensor_data(
        sensors: list[str] | None = None,
    ) -> dict[str, dict[str, float] | str]:
        """Get current sensor readings.

        Args:
            sensors: List of sensors to read (imu, audio_level, temperature, all).
                    Defaults to all sensors.

        Returns:
            Sensor readings dictionary.
        """
        valid_sensors = ["imu", "audio_level", "temperature", "all"]
        if sensors is None:
            sensors = ["all"]

        for sensor in sensors:
            if sensor not in valid_sensors:
                return {"error": f"Invalid sensor. Must be one of: {valid_sensors}"}

        log.info("Getting sensor data", sensors=sensors)

        result = await client.get_sensor_data(sensors=sensors)
        return result

    @mcp.tool()
    async def look_at_sound(
        timeout_ms: int = 2000,
    ) -> dict[str, str]:
        """Turn to face the direction of detected sound.

        Uses the 4-microphone array to detect sound direction
        and turns the head to face it.

        Args:
            timeout_ms: Maximum time to wait for sound detection.

        Returns:
            Status of the operation and detected direction.
        """
        if timeout_ms < 500:
            return {"error": "Timeout must be at least 500ms"}

        log.info("Looking at sound", timeout_ms=timeout_ms)

        result = await client.look_at_sound(timeout_ms=timeout_ms)
        return result

    @mcp.tool()
    async def dance(
        routine: str,
        duration_seconds: float = 5.0,
    ) -> dict[str, str]:
        """Perform a choreographed dance routine.

        Args:
            routine: Name of dance routine (celebrate, greeting, thinking, custom).
            duration_seconds: Duration of the dance (1-30 seconds).

        Returns:
            Status of the dance operation.
        """
        valid_routines = ["celebrate", "greeting", "thinking", "custom"]

        if routine not in valid_routines:
            return {"error": f"Invalid routine. Must be one of: {valid_routines}"}
        if not (1 <= duration_seconds <= 30):
            return {"error": "Duration must be between 1 and 30 seconds"}

        log.info("Dancing", routine=routine, duration_seconds=duration_seconds)

        result = await client.dance(routine=routine, duration_seconds=duration_seconds)
        return result

    # ========== NEW TOOLS FOR FULL SDK SUPPORT ==========

    @mcp.tool()
    async def rotate(
        direction: str,
        degrees: float = 90.0,
        speed: str = "normal",
    ) -> dict[str, str]:
        """Rotate Reachy's body on its 360° base.

        Args:
            direction: Rotation direction (left, right).
            degrees: Rotation angle in degrees (0-360).
            speed: Rotation speed (slow, normal, fast).

        Returns:
            Status of the rotation operation.
        """
        valid_directions = ["left", "right"]
        valid_speeds = ["slow", "normal", "fast"]

        if direction not in valid_directions:
            return {"error": f"Invalid direction. Must be one of: {valid_directions}"}
        if not (0 <= degrees <= 360):
            return {"error": "Degrees must be between 0 and 360"}
        if speed not in valid_speeds:
            return {"error": f"Invalid speed. Must be one of: {valid_speeds}"}

        log.info("Rotating body", direction=direction, degrees=degrees, speed=speed)

        result = await client.rotate(direction=direction, degrees=degrees, speed=speed)
        return result

    @mcp.tool()
    async def look_at(
        roll: float = 0.0,
        pitch: float = 0.0,
        yaw: float = 0.0,
        z: float = 0.0,
        duration: float = 1.0,
    ) -> dict[str, str]:
        """Position Reachy's head with precise angles.

        Use this for fine-grained head control with exact positioning.

        Args:
            roll: Roll angle in degrees (-45 to 45). Tilts head side to side.
            pitch: Pitch angle in degrees (-45 to 45). Looks up/down.
            yaw: Yaw angle in degrees (-45 to 45). Looks left/right.
            z: Vertical offset in mm (-50 to 50). Raises/lowers head.
            duration: Movement duration in seconds (0.1 to 5.0).

        Returns:
            Status with final head position.
        """
        if not (-45 <= roll <= 45):
            return {"error": "Roll must be between -45 and 45 degrees"}
        if not (-45 <= pitch <= 45):
            return {"error": "Pitch must be between -45 and 45 degrees"}
        if not (-45 <= yaw <= 45):
            return {"error": "Yaw must be between -45 and 45 degrees"}
        if not (-50 <= z <= 50):
            return {"error": "Z offset must be between -50 and 50 mm"}
        if not (0.1 <= duration <= 5.0):
            return {"error": "Duration must be between 0.1 and 5.0 seconds"}

        log.info(
            "Looking at position",
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            z=z,
            duration=duration,
        )

        result = await client.look_at(
            roll=roll, pitch=pitch, yaw=yaw, z=z, duration=duration
        )
        return result

    @mcp.tool()
    async def listen(
        duration_seconds: float = 3.0,
    ) -> dict[str, str]:
        """Capture audio from Reachy's 4-microphone array.

        Records audio that can be used for speech recognition or analysis.

        Args:
            duration_seconds: Recording duration (0.5 to 10.0 seconds).

        Returns:
            Audio data as base64-encoded string with format info.
        """
        if not (0.5 <= duration_seconds <= 10.0):
            return {"error": "Duration must be between 0.5 and 10.0 seconds"}

        log.info("Listening", duration_seconds=duration_seconds)

        result = await client.listen(duration_seconds=duration_seconds)
        return result

    @mcp.tool()
    async def wake_up() -> dict[str, str]:
        """Initialize Reachy's motors and prepare for operation.

        Call this before other motor commands after the robot has been sleeping.
        Motors will be enabled and move to a neutral position.

        Returns:
            Status of the wake up operation.
        """
        log.info("Waking up robot")
        result = await client.wake_up()
        return result

    @mcp.tool()
    async def sleep() -> dict[str, str]:
        """Power down Reachy's motors and enter sleep mode.

        Call this when done using the robot to conserve power and
        reduce wear. The robot will safely power down motors.

        Returns:
            Status of the sleep operation.
        """
        log.info("Putting robot to sleep")
        result = await client.sleep()
        return result

    @mcp.tool()
    async def nod(
        times: int = 2,
        speed: str = "normal",
    ) -> dict[str, str]:
        """Perform a nodding gesture to express agreement or acknowledgment.

        Args:
            times: Number of nods (1 to 5).
            speed: Nod speed (slow, normal, fast).

        Returns:
            Status of the nod gesture.
        """
        valid_speeds = ["slow", "normal", "fast"]

        if not (1 <= times <= 5):
            return {"error": "Times must be between 1 and 5"}
        if speed not in valid_speeds:
            return {"error": f"Invalid speed. Must be one of: {valid_speeds}"}

        log.info("Nodding", times=times, speed=speed)

        result = await client.nod(times=times, speed=speed)
        return result

    @mcp.tool()
    async def shake(
        times: int = 2,
        speed: str = "normal",
    ) -> dict[str, str]:
        """Perform a head shake gesture to express disagreement or negation.

        Args:
            times: Number of shakes (1 to 5).
            speed: Shake speed (slow, normal, fast).

        Returns:
            Status of the shake gesture.
        """
        valid_speeds = ["slow", "normal", "fast"]

        if not (1 <= times <= 5):
            return {"error": "Times must be between 1 and 5"}
        if speed not in valid_speeds:
            return {"error": f"Invalid speed. Must be one of: {valid_speeds}"}

        log.info("Shaking head", times=times, speed=speed)

        result = await client.shake(times=times, speed=speed)
        return result

    @mcp.tool()
    async def rest() -> dict[str, str]:
        """Return Reachy to a neutral resting pose.

        Moves head to center, antennas to neutral, and body to forward.
        Useful after expressions or gestures to reset to a calm state.

        Returns:
            Status of the rest operation.
        """
        log.info("Returning to rest pose")
        result = await client.rest()
        return result

    return mcp
