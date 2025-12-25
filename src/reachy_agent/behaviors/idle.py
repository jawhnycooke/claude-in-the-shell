"""Idle Behavior Controller - Natural look-around behavior when idle.

This module implements casual idle behaviors that run when the agent
is not actively responding to user commands. The robot looks around
its environment with natural curiosity, occasionally expressing interest
in what it sees.

The design mimics how humans and pets behave when unstimulated -
casually glancing around, sometimes with mild interest.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

log = get_logger(__name__)


class IdleState(str, Enum):
    """Current state of the idle behavior system."""

    STOPPED = "stopped"  # Not running
    PAUSED = "paused"  # Paused (user interaction in progress)
    IDLE = "idle"  # Actively running idle behaviors


@dataclass
class IdleBehaviorConfig:
    """Configuration for idle behavior parameters.

    These settings control how the robot behaves when not
    actively responding to user commands.
    """

    # Timing parameters (in seconds)
    min_look_interval: float = 3.0  # Minimum time between look movements
    max_look_interval: float = 8.0  # Maximum time between look movements
    movement_duration: float = 1.5  # How long each look movement takes

    # Head movement ranges (in degrees)
    yaw_range: tuple[float, float] = (-35.0, 35.0)  # Left/right range
    pitch_range: tuple[float, float] = (-15.0, 20.0)  # Down/up range
    roll_range: tuple[float, float] = (-8.0, 8.0)  # Tilt range (subtle)

    # Behavior probabilities (0.0 to 1.0)
    curiosity_chance: float = 0.15  # Chance to show curiosity emotion
    double_look_chance: float = 0.10  # Chance to look at same spot twice
    return_to_neutral_chance: float = 0.25  # Chance to return to neutral between looks

    # Curiosity expression settings
    curiosity_intensity: float = 0.6  # Intensity of curiosity expression
    curiosity_emotions: list[str] = field(
        default_factory=lambda: ["curious", "thinking", "recognition"]
    )

    # Safety settings
    pause_on_interaction: bool = True  # Pause when user is interacting
    interaction_cooldown: float = 2.0  # Seconds to wait after interaction ends

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdleBehaviorConfig:
        """Create config from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class LookTarget:
    """A target position for the robot to look at."""

    yaw: float  # Left/right in degrees
    pitch: float  # Up/down in degrees
    roll: float = 0.0  # Head tilt in degrees
    duration: float = 1.5  # Movement duration

    @classmethod
    def random(cls, config: IdleBehaviorConfig) -> LookTarget:
        """Generate a random look target within config bounds."""
        yaw = random.uniform(*config.yaw_range)
        pitch = random.uniform(*config.pitch_range)
        roll = random.uniform(*config.roll_range)
        return cls(yaw=yaw, pitch=pitch, roll=roll, duration=config.movement_duration)

    @classmethod
    def neutral(cls) -> LookTarget:
        """Return a neutral (center) position."""
        return cls(yaw=0.0, pitch=0.0, roll=0.0)


class IdleBehaviorController:
    """Controls autonomous idle behaviors for the robot.

    This controller runs in the background and makes the robot
    look around naturally when not engaged in conversation.
    It can be paused during user interactions and resumed after.

    Example usage:
        client = ReachyDaemonClient(base_url="http://localhost:8000")
        controller = IdleBehaviorController(client)
        await controller.start()
        # ... later when user starts talking ...
        controller.pause()
        # ... after conversation ends ...
        controller.resume()
        # ... when shutting down ...
        await controller.stop()
    """

    def __init__(
        self,
        daemon_client: ReachyDaemonClient,
        config: IdleBehaviorConfig | None = None,
    ) -> None:
        """Initialize the idle behavior controller.

        Args:
            daemon_client: Client for sending commands to the robot.
            config: Configuration for idle behavior. Uses defaults if not provided.
        """
        self.client = daemon_client
        self.config = config or IdleBehaviorConfig()
        self._state = IdleState.STOPPED
        self._state_lock = asyncio.Lock()  # Thread-safe state management
        self._task: asyncio.Task[None] | None = None
        self._last_interaction: datetime | None = None
        self._last_target: LookTarget | None = None
        self._movement_count: int = 0

    @property
    def state(self) -> IdleState:
        """Get current state of the controller."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if the controller is actively running."""
        return self._state == IdleState.IDLE

    async def start(self) -> None:
        """Start the idle behavior loop.

        This begins the background task that controls idle movements.
        Safe to call multiple times.
        """
        if self._task is not None and not self._task.done():
            log.debug("Idle behavior already running")
            return

        log.info("Starting idle behavior controller")
        self._state = IdleState.IDLE
        self._task = asyncio.create_task(self._idle_loop())

    async def stop(self) -> None:
        """Stop the idle behavior loop.

        This cancels the background task and waits for cleanup.
        """
        if self._task is None:
            return

        log.info("Stopping idle behavior controller")
        self._state = IdleState.STOPPED
        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None
        log.info(
            "Idle behavior stopped",
            total_movements=self._movement_count,
        )

    async def pause(self) -> None:
        """Pause idle behaviors (e.g., when user starts talking).

        The loop continues running but doesn't execute movements.
        Uses async lock for thread-safe state modification.
        """
        async with self._state_lock:
            if self._state == IdleState.IDLE:
                log.debug("Pausing idle behavior")
                self._state = IdleState.PAUSED
                self._last_interaction = datetime.now()

    async def resume(self) -> None:
        """Resume idle behaviors after a pause.

        Respects the interaction cooldown before starting movements again.
        Uses async lock for thread-safe state modification.
        """
        async with self._state_lock:
            if self._state == IdleState.PAUSED:
                log.debug("Resuming idle behavior")
                self._state = IdleState.IDLE
                self._last_interaction = datetime.now()

    async def notify_interaction(self) -> None:
        """Notify the controller that a user interaction occurred.

        Call this when user sends input or agent responds.
        Automatically pauses if configured to do so.
        Uses async lock for thread-safe state modification.
        """
        async with self._state_lock:
            self._last_interaction = datetime.now()
            if self.config.pause_on_interaction and self._state == IdleState.IDLE:
                self._state = IdleState.PAUSED
                log.debug("Pausing idle behavior due to interaction")

    async def _idle_loop(self) -> None:
        """Main loop that executes idle behaviors."""
        log.debug("Idle behavior loop started")

        while True:
            try:
                # Wait for next action interval
                interval = random.uniform(
                    self.config.min_look_interval,
                    self.config.max_look_interval,
                )
                await asyncio.sleep(interval)

                # Check if we should execute movements
                if not await self._should_execute():
                    continue

                # Execute a look-around action
                await self._execute_look_around()

            except asyncio.CancelledError:
                log.debug("Idle behavior loop cancelled")
                break
            except Exception as e:
                log.error("Error in idle behavior loop", error=str(e))
                await asyncio.sleep(1.0)  # Brief pause before retrying

    async def _should_execute(self) -> bool:
        """Check if we should execute an idle movement now.

        Uses async lock for thread-safe state reading.
        """
        async with self._state_lock:
            if self._state != IdleState.IDLE:
                return False

            # Check interaction cooldown
            if self._last_interaction:
                elapsed = datetime.now() - self._last_interaction
                if elapsed < timedelta(seconds=self.config.interaction_cooldown):
                    return False

            return True

    async def _execute_look_around(self) -> None:
        """Execute a single look-around action."""
        # Decide what kind of look to do
        if (
            self._last_target
            and random.random() < self.config.double_look_chance
        ):
            # Look at the same spot again (as if re-checking something)
            target = self._last_target
            log.debug("Double-look at previous target")
        elif random.random() < self.config.return_to_neutral_chance:
            # Return to neutral/center position
            target = LookTarget.neutral()
            log.debug("Returning to neutral position")
        else:
            # Pick a random new target
            target = LookTarget.random(self.config)

        # Execute the look movement
        await self._look_at(target)
        self._last_target = target
        self._movement_count += 1

        # Maybe express curiosity
        if random.random() < self.config.curiosity_chance:
            await self._express_curiosity()

        # Use get_pose to verify the movement (tests proprioceptive feedback)
        await self._verify_pose(target)

    async def _look_at(self, target: LookTarget) -> None:
        """Execute a look_at command to move the head."""
        log.debug(
            "Looking at target",
            yaw=target.yaw,
            pitch=target.pitch,
            roll=target.roll,
        )

        try:
            result = await self.client.look_at(
                yaw=target.yaw,
                pitch=target.pitch,
                roll=target.roll,
                duration=target.duration,
            )

            if result.get("status") == "error":
                log.warning(
                    "Look command failed",
                    error=result.get("message"),
                )
        except Exception as e:
            log.error("Error executing look command", error=str(e))

    async def _express_curiosity(self) -> None:
        """Express a curiosity emotion occasionally."""
        emotion = random.choice(self.config.curiosity_emotions)

        log.debug("Expressing curiosity", emotion=emotion)

        try:
            await self.client.play_emotion(
                emotion=emotion,
                intensity=self.config.curiosity_intensity,
            )
        except Exception as e:
            log.warning("Error expressing emotion", error=str(e))

    async def _verify_pose(self, expected: LookTarget) -> None:
        """Verify the pose after movement using get_current_pose.

        This serves both as a verification mechanism and as a way
        to test the get_pose feature alongside idle behavior.
        """
        try:
            pose = await self.client.get_current_pose()

            if pose.get("status") == "success":
                actual_yaw = pose.get("head", {}).get("yaw", 0.0)
                actual_pitch = pose.get("head", {}).get("pitch", 0.0)

                # Log the difference (helps verify get_pose is working)
                yaw_diff = abs(expected.yaw - actual_yaw)
                pitch_diff = abs(expected.pitch - actual_pitch)

                log.debug(
                    "Pose verification",
                    expected_yaw=expected.yaw,
                    actual_yaw=actual_yaw,
                    yaw_diff=round(yaw_diff, 1),
                    expected_pitch=expected.pitch,
                    actual_pitch=actual_pitch,
                    pitch_diff=round(pitch_diff, 1),
                )

                # Log a warning if there's a large discrepancy
                if yaw_diff > 10.0 or pitch_diff > 10.0:
                    log.warning(
                        "Large pose discrepancy detected",
                        yaw_diff=yaw_diff,
                        pitch_diff=pitch_diff,
                    )
            else:
                log.debug(
                    "Could not verify pose",
                    reason=pose.get("message", "unknown"),
                )

        except Exception as e:
            log.debug("Pose verification failed", error=str(e))


async def run_idle_demo(
    daemon_url: str = "http://localhost:8000",
    duration_seconds: float = 30.0,
) -> None:
    """Demo function to test idle behavior standalone.

    Args:
        daemon_url: URL of the Reachy daemon.
        duration_seconds: How long to run the demo.
    """
    from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

    print(f"Starting idle behavior demo for {duration_seconds}s...")
    print(f"Daemon URL: {daemon_url}")

    client = ReachyDaemonClient(base_url=daemon_url)

    # Use faster settings for demo visibility
    config = IdleBehaviorConfig(
        min_look_interval=2.0,
        max_look_interval=5.0,
        curiosity_chance=0.3,  # Higher for demo
        movement_duration=1.0,
    )

    controller = IdleBehaviorController(client, config)

    try:
        await controller.start()
        print("Idle behavior running... Press Ctrl+C to stop")

        # Run for specified duration
        await asyncio.sleep(duration_seconds)

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        await controller.stop()
        print(f"Demo complete. Total movements: {controller._movement_count}")


if __name__ == "__main__":
    # Allow running as standalone demo
    import sys

    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    daemon_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000"

    asyncio.run(run_idle_demo(daemon_url=daemon_url, duration_seconds=duration))
