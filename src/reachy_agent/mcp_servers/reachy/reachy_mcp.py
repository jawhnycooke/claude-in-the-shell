"""Reachy MCP Server - Exposes robot body control as MCP tools.

This server provides tools for controlling the Reachy Mini robot's head,
antennas, camera, and audio output. It communicates with the Reachy Daemon
running on localhost:8000.

Motion tools use fire-and-forget execution to reduce latency - they return
"acknowledged" immediately while the daemon executes asynchronously.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any, TypeVar

from mcp.server.fastmcp import FastMCP

from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.utils.config import ReachyConfig

log = get_logger(__name__)

# Type variable for generic daemon call result
T = TypeVar("T")


async def _fire_and_forget(
    coro: Awaitable[T],
    tool_name: str,
) -> dict[str, str]:
    """Execute a coroutine in fire-and-forget mode.

    Starts the coroutine as a background task and returns immediately
    with an "acknowledged" status. Errors are logged but not propagated.

    This reduces tool execution latency for motion commands that don't
    return data needed for Claude's response generation.

    Args:
        coro: The awaitable coroutine to execute.
        tool_name: Name of the tool for logging.

    Returns:
        Acknowledgment dict indicating the command was dispatched.
    """
    async def _run_and_log() -> None:
        try:
            result = await coro
            log.debug(
                "fire_and_forget_completed",
                tool=tool_name,
                result=result,
            )
        except Exception as e:
            log.warning(
                "fire_and_forget_error",
                tool=tool_name,
                error=str(e),
            )

    # Create background task - doesn't block
    asyncio.create_task(_run_and_log())

    return {
        "status": "acknowledged",
        "message": f"{tool_name} command dispatched",
    }


def create_reachy_mcp_server(
    config: ReachyConfig | None = None,  # noqa: ARG001
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

        # Fire-and-forget: return immediately while motion executes
        return await _fire_and_forget(
            client.move_head(direction=direction, speed=speed, degrees=degrees),
            "move_head",
        )

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

        # Fire-and-forget: return immediately while emotion plays
        return await _fire_and_forget(
            client.play_emotion(emotion=emotion, intensity=intensity),
            "play_emotion",
        )

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

        # Fire-and-forget: return immediately while antennas move
        return await _fire_and_forget(
            client.set_antenna_state(
                left_angle=left_angle,
                right_angle=right_angle,
                wiggle=wiggle,
                duration_ms=duration_ms,
            ),
            "set_antenna_state",
        )

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

        # Fire-and-forget: return immediately while dance executes
        return await _fire_and_forget(
            client.dance(routine=routine, duration_seconds=duration_seconds),
            "dance",
        )

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

        # Fire-and-forget: return immediately while body rotates
        return await _fire_and_forget(
            client.rotate(direction=direction, degrees=degrees, speed=speed),
            "rotate",
        )

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

        # Fire-and-forget: return immediately while head moves
        return await _fire_and_forget(
            client.look_at(roll=roll, pitch=pitch, yaw=yaw, z=z, duration=duration),
            "look_at",
        )

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

        # Fire-and-forget: return immediately while robot wakes
        return await _fire_and_forget(client.wake_up(), "wake_up")

    @mcp.tool()
    async def sleep() -> dict[str, str]:
        """Power down Reachy's motors and enter sleep mode.

        Call this when done using the robot to conserve power and
        reduce wear. The robot will safely power down motors.

        Returns:
            Status of the sleep operation.
        """
        log.info("Putting robot to sleep")

        # Fire-and-forget: return immediately while robot sleeps
        return await _fire_and_forget(client.sleep(), "sleep")

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

        # Fire-and-forget: return immediately while nodding
        return await _fire_and_forget(
            client.nod(times=times, speed=speed),
            "nod",
        )

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

        # Fire-and-forget: return immediately while shaking
        return await _fire_and_forget(
            client.shake(times=times, speed=speed),
            "shake",
        )

    @mcp.tool()
    async def rest() -> dict[str, str]:
        """Return Reachy to a neutral resting pose.

        Moves head to center, antennas to neutral, and body to forward.
        Useful after expressions or gestures to reset to a calm state.

        Returns:
            Status of the rest operation.
        """
        log.info("Returning to rest pose")

        # Fire-and-forget: return immediately while moving to rest
        return await _fire_and_forget(client.rest(), "rest")

    @mcp.tool()
    async def get_status() -> dict[str, Any]:
        """Get comprehensive robot status.

        Returns current state of all robot systems including:
        - Motor positions and states
        - Head orientation (roll, pitch, yaw)
        - Body rotation angle
        - Antenna positions
        - Temperature readings
        - Whether robot is awake or sleeping
        - Any active actions in progress

        Returns:
            Comprehensive status dictionary.
        """
        log.info("Getting robot status")
        result = await client.get_status()
        return result

    @mcp.tool()
    async def cancel_action(
        action_id: str | None = None,
        all_actions: bool = False,
    ) -> dict[str, str]:
        """Cancel running actions.

        Use this to stop any movement or action currently in progress.
        Can cancel a specific action by ID or all running actions.

        Args:
            action_id: Optional ID of specific action to cancel.
            all_actions: If True, cancels all running actions.

        Returns:
            Status with number of cancelled actions.
        """
        if not action_id and not all_actions:
            return {"error": "Must specify action_id or set all_actions=True"}

        log.info("Cancelling actions", action_id=action_id, all_actions=all_actions)

        # Fire-and-forget: return immediately while cancelling
        return await _fire_and_forget(
            client.cancel_action(action_id=action_id, all_actions=all_actions),
            "cancel_action",
        )

    @mcp.tool()
    async def get_pose() -> dict[str, Any]:
        """Get Reachy's current physical pose (proprioceptive feedback).

        Use this to know your actual position before or after movements.
        This is helpful for:
        - Verifying a movement completed successfully
        - Understanding your current state before planning next action
        - Detecting if you are at a neutral or expressive pose

        Returns:
            Dictionary containing:
            - head: {roll, pitch, yaw} in degrees
              - roll: Head tilt side-to-side (-45 to 45)
              - pitch: Looking up/down (-45 to 45)
              - yaw: Looking left/right (-45 to 45)
            - body_yaw: Body rotation in degrees
            - antennas: {left, right} in degrees (0=droopy, 90=straight up)
            - timestamp: When the reading was taken

        Example response:
            {"head": {"roll": 0.0, "pitch": 12.2, "yaw": -10.5},
             "body_yaw": 0.0,
             "antennas": {"left": 80.0, "right": 80.0}}
        """
        log.info("Getting current pose")
        result = await client.get_current_pose()
        return result

    # ========== SDK COVERAGE EXPANSION TOOLS ==========

    @mcp.tool()
    async def look_at_world(
        x: float,
        y: float,
        z: float,
        duration: float = 1.0,
    ) -> dict[str, str]:
        """Look at a 3D point in world coordinates.

        Orients Reachy's head to gaze at a specific point in 3D space.
        Uses inverse kinematics to compute the required head orientation.

        This is useful for spatial awareness tasks like:
        - "Look at where the sound came from"
        - "Look at the detected object"
        - "Focus on a point in the room"

        Args:
            x: X coordinate in meters. Positive = right of robot.
            y: Y coordinate in meters. Positive = forward/in front of robot.
            z: Z coordinate in meters. Positive = up.
            duration: Movement duration in seconds (0.1 to 5.0).

        Returns:
            Status of the operation.

        Example:
            # Look at a point 1 meter in front and 0.5m to the left
            look_at_world(x=-0.5, y=1.0, z=0.3)
        """
        if not (0.1 <= duration <= 5.0):
            return {"error": "Duration must be between 0.1 and 5.0 seconds"}

        log.info("Looking at world coordinates", x=x, y=y, z=z, duration=duration)

        # Fire-and-forget: return immediately while head moves
        return await _fire_and_forget(
            client.look_at_world(x=x, y=y, z=z, duration=duration),
            "look_at_world",
        )

    @mcp.tool()
    async def look_at_pixel(
        u: int,
        v: int,
        duration: float = 1.0,
    ) -> dict[str, str]:
        """Look at a pixel coordinate in the camera image.

        Orients Reachy's head to center the camera view on a specific pixel.
        This is extremely useful for visual tracking and attention tasks.

        Common use cases:
        - "Look at the detected face" (center on face bounding box)
        - "Center on the object of interest"
        - "Track the moving target"

        Args:
            u: Horizontal pixel coordinate (0 = left edge of image).
            v: Vertical pixel coordinate (0 = top edge of image).
            duration: Movement duration in seconds (0.1 to 5.0).

        Returns:
            Status of the operation.

        Example:
            # Look at the center of a 640x480 image
            look_at_pixel(u=320, v=240)
        """
        if u < 0:
            return {"error": "Pixel u coordinate must be non-negative"}
        if v < 0:
            return {"error": "Pixel v coordinate must be non-negative"}
        if not (0.1 <= duration <= 5.0):
            return {"error": "Duration must be between 0.1 and 5.0 seconds"}

        log.info("Looking at pixel coordinates", u=u, v=v, duration=duration)

        # Fire-and-forget: return immediately while head moves
        return await _fire_and_forget(
            client.look_at_pixel(u=u, v=v, duration=duration),
            "look_at_pixel",
        )

    @mcp.tool()
    async def play_recorded_move(
        dataset: str,
        move_name: str,
    ) -> dict[str, str]:
        """Play a pre-recorded move from a HuggingFace dataset.

        The Reachy Mini SDK includes professionally motion-captured animations
        stored on HuggingFace. These include the official emotions library
        with 19+ emotion animations that include synchronized audio.

        Args:
            dataset: HuggingFace dataset name.
                Example: "pollen-robotics/reachy-mini-emotions-library"
            move_name: Name of the move within the dataset.
                Examples: "curious1", "dance1", "cheerful1", "amazed1"

        Returns:
            Status of the operation.

        Available moves in the emotions library:
        - Emotions: curious1, confused1, cheerful1, downcast1, amazed1,
          exhausted1, attentive1, attentive2, contempt1, boredom1, fear1,
          anxiety1, disgusted1, displeased1, calming1, dying1, electric1,
          enthusiastic1, enthusiastic2, come1
        - Dances: dance1, dance2, dance3

        Example:
            # Play the curious emotion
            play_recorded_move(
                dataset="pollen-robotics/reachy-mini-emotions-library",
                move_name="curious1"
            )
        """
        if not dataset:
            return {"error": "Dataset name is required"}
        if not move_name:
            return {"error": "Move name is required"}

        log.info("Playing recorded move", dataset=dataset, move_name=move_name)

        # Fire-and-forget: return immediately while move plays
        return await _fire_and_forget(
            client.play_recorded_move(dataset=dataset, move_name=move_name),
            "play_recorded_move",
        )

    @mcp.tool()
    async def set_motor_mode(
        mode: str,
    ) -> dict[str, str]:
        """Set the motor control mode.

        Controls motor torque and behavior. Essential for safety, teaching mode,
        and enabling manual physical interaction with the robot.

        Args:
            mode: Motor mode to set:
                - "enabled": Motors powered and holding position (normal operation).
                  Use this for autonomous movement.
                - "disabled": Motors powered off, robot can be moved freely by hand.
                  Use for transport or when not in use.
                - "gravity_compensation": Motors compensate for gravity only.
                  Allows smooth manual positioning while preventing collapse.
                  Ideal for teaching poses or physical interaction.

        Returns:
            Status of the operation.

        Example:
            # Enable teaching mode for manual positioning
            set_motor_mode(mode="gravity_compensation")

            # Return to normal autonomous operation
            set_motor_mode(mode="enabled")
        """
        valid_modes = ["enabled", "disabled", "gravity_compensation"]

        if mode not in valid_modes:
            return {"error": f"Invalid mode. Must be one of: {valid_modes}"}

        log.info("Setting motor mode", mode=mode)

        # Fire-and-forget: return immediately while mode changes
        return await _fire_and_forget(
            client.set_motor_mode(mode=mode),
            "set_motor_mode",
        )

    return mcp
