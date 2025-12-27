#!/usr/bin/env python3
"""Demo script for the motion blending system.

Demonstrates:
1. Breathing animation (subtle idle motion)
2. Motion source switching (breathing → idle → breathing)
3. Head wobble overlay (simulated speech)
4. Listening state (frozen antennas)

Usage:
    python scripts/demo_motion_blend.py [daemon_url]

Example:
    python scripts/demo_motion_blend.py http://localhost:8000
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, "src")

from reachy_agent.behaviors import (
    BlendControllerConfig,
    BreathingConfig,
    BreathingMotion,
    HeadPose,
    HeadWobble,
    IdleBehaviorConfig,
    IdleBehaviorController,
    MotionBlendController,
    WobbleConfig,
    simulate_speech,
)


class DemoLogger:
    """Simple logger for demo output."""

    def __init__(self) -> None:
        self.start_time = datetime.now()

    def log(self, message: str, **kwargs: object) -> None:
        elapsed = (datetime.now() - self.start_time).total_seconds()
        extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
        print(f"[{elapsed:6.2f}s] {message} {extra}")


async def demo_breathing_only(logger: DemoLogger) -> None:
    """Demo 1: Breathing motion only."""
    print("\n" + "=" * 60)
    print("DEMO 1: Breathing Motion")
    print("=" * 60)
    print("Subtle idle animation with Z-axis and antenna oscillation")
    print("-" * 60)

    config = BreathingConfig(
        z_amplitude_mm=5.0,
        z_frequency_hz=0.2,  # Faster for demo visibility
        antenna_amplitude_deg=15.0,
        antenna_frequency_hz=0.5,
    )
    breathing = BreathingMotion(config)

    await breathing.start()
    logger.log("Breathing started")

    # Sample the pose over time
    for i in range(20):
        pose = await breathing.get_contribution(HeadPose.neutral())
        phase = breathing.get_current_phase()

        logger.log(
            f"Sample {i + 1:2d}",
            z=f"{pose.z:+5.2f}mm",
            pitch=f"{pose.pitch:+5.2f}°",
            left_ant=f"{pose.left_antenna:5.1f}°",
            right_ant=f"{pose.right_antenna:5.1f}°",
            z_phase=f"{phase['z_phase']:.2f}",
        )
        await asyncio.sleep(0.2)

    await breathing.stop()
    logger.log("Breathing stopped")


async def demo_blend_controller(logger: DemoLogger) -> None:
    """Demo 2: Motion blend controller with multiple sources."""
    print("\n" + "=" * 60)
    print("DEMO 2: Motion Blend Controller")
    print("=" * 60)
    print("Orchestrates breathing + wobble with pose composition")
    print("-" * 60)

    poses_sent: list[HeadPose] = []

    async def capture_pose(pose: HeadPose) -> None:
        poses_sent.append(pose)

    # Create controller
    config = BlendControllerConfig(
        tick_rate_hz=50.0,  # Reduced for demo
        command_rate_hz=10.0,
    )
    controller = MotionBlendController(
        config=config,
        send_pose_callback=capture_pose,
    )

    # Create motion sources
    breathing = BreathingMotion(
        BreathingConfig(z_amplitude_mm=5.0, z_frequency_hz=0.2)
    )
    wobble = HeadWobble(
        WobbleConfig(max_pitch_deg=8.0, max_yaw_deg=6.0)
    )

    # Register sources
    controller.register_source("breathing", breathing)
    controller.register_source("wobble", wobble)

    # Start controller
    await controller.start()
    await controller.set_primary("breathing")
    logger.log("Controller started with breathing as primary")

    # Phase 1: Breathing only
    logger.log("Phase 1: Breathing only (2 seconds)")
    await asyncio.sleep(2.0)
    logger.log(f"Poses sent so far: {len(poses_sent)}")

    # Phase 2: Add wobble (simulated speech)
    logger.log("Phase 2: Adding wobble overlay (speech simulation)")
    await controller.enable_secondary("wobble")
    wobble.update_audio_level(0.7)

    for i in range(10):
        # Simulate varying audio levels
        level = 0.3 + 0.5 * abs((i % 5) - 2) / 2
        wobble.update_audio_level(level)
        logger.log(f"Audio level: {level:.2f}")
        await asyncio.sleep(0.2)

    # Phase 3: Listening state
    logger.log("Phase 3: Entering listening state (antennas frozen)")
    controller.set_listening(True)
    await asyncio.sleep(1.0)

    logger.log("Exiting listening state")
    controller.set_listening(False)
    await asyncio.sleep(0.5)

    # Stop
    await controller.disable_secondary("wobble")
    await controller.stop()

    logger.log(f"Controller stopped. Total poses sent: {len(poses_sent)}")

    # Show sample of poses
    if poses_sent:
        print("\nSample of sent poses:")
        for i in range(0, len(poses_sent), len(poses_sent) // 5):
            p = poses_sent[i]
            print(
                f"  [{i:3d}] pitch={p.pitch:+6.2f}° yaw={p.yaw:+6.2f}° "
                f"z={p.z:+5.2f}mm left={p.left_antenna:5.1f}° right={p.right_antenna:5.1f}°"
            )


async def demo_wobble_simulation(logger: DemoLogger) -> None:
    """Demo 3: Head wobble with simulated speech."""
    print("\n" + "=" * 60)
    print("DEMO 3: Head Wobble Speech Simulation")
    print("=" * 60)
    print("Simulates audio-reactive head motion during TTS")
    print("-" * 60)

    config = WobbleConfig(max_pitch_deg=10.0, max_yaw_deg=8.0, max_roll_deg=5.0)
    wobble = HeadWobble(config)

    logger.log("Simulating 3 seconds of speech...")

    samples = await simulate_speech(wobble, duration_seconds=3.0, sample_rate_hz=20.0)

    logger.log(f"Generated {len(samples)} offset samples")

    # Show statistics
    pitches = [s.pitch for s in samples]
    yaws = [s.yaw for s in samples]

    print(f"\nPitch range: {min(pitches):+.2f}° to {max(pitches):+.2f}°")
    print(f"Yaw range:   {min(yaws):+.2f}° to {max(yaws):+.2f}°")

    # Show sample offsets
    print("\nSample offsets (every 10th):")
    for i, s in enumerate(samples[::10]):
        print(f"  [{i * 10:3d}] pitch={s.pitch:+6.2f}° yaw={s.yaw:+6.2f}° roll={s.roll:+5.2f}°")


async def demo_with_daemon(daemon_url: str, logger: DemoLogger) -> None:
    """Demo 4: Full integration with daemon (if available)."""
    print("\n" + "=" * 60)
    print("DEMO 4: Daemon Integration")
    print("=" * 60)
    print(f"Connecting to daemon at {daemon_url}")
    print("-" * 60)

    try:
        from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

        client = ReachyDaemonClient(base_url=daemon_url)

        # Check daemon status
        status = await client.get_status()
        if status.get("status") not in ("success", "connected"):
            logger.log(f"Daemon not available: {status}")
            return

        mode = status.get("mode", "unknown")
        logger.log(f"Daemon connected!", mode=mode)

        # Create pose callback that actually sends to daemon
        async def send_to_daemon(pose: HeadPose) -> None:
            await client.look_at(
                yaw=pose.yaw,
                pitch=pose.pitch,
                roll=pose.roll,
                duration=0.05,
            )

        # Create and run blend controller
        controller = MotionBlendController(
            config=BlendControllerConfig(tick_rate_hz=50.0, command_rate_hz=20.0),
            send_pose_callback=send_to_daemon,
        )

        breathing = BreathingMotion()
        controller.register_source("breathing", breathing)

        await controller.start()
        await controller.set_primary("breathing")
        logger.log("Breathing motion active on robot")

        # Let it run
        logger.log("Running for 5 seconds (watch the robot!)...")
        await asyncio.sleep(5.0)

        await controller.stop()
        await client.close()
        logger.log("Demo complete!")

    except Exception as e:
        logger.log(f"Daemon demo failed: {e}")


async def main() -> None:
    """Run all demos."""
    daemon_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    print("=" * 60)
    print("MOTION BLENDING SYSTEM DEMO")
    print("=" * 60)
    print(f"Daemon URL: {daemon_url}")
    print()

    logger = DemoLogger()

    # Run demos
    await demo_breathing_only(logger)
    await demo_blend_controller(logger)
    await demo_wobble_simulation(logger)

    # Try daemon integration if available
    await demo_with_daemon(daemon_url, logger)

    print("\n" + "=" * 60)
    print("ALL DEMOS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
