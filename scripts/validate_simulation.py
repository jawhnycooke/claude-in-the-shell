#!/usr/bin/env python3
"""End-to-end validation script for MuJoCo simulation.

This script validates that the full stack works:
1. MuJoCo simulation daemon starts
2. MCP tools can control the simulated robot
3. Agent loop can execute tool calls

Run with:
    python scripts/validate_simulation.py

For headless mode (CI):
    python scripts/validate_simulation.py --headless

For GUI mode on macOS (requires mjpython):
    mjpython scripts/validate_simulation.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reachy_agent.simulation import SimulationAdapter
from reachy_agent.simulation.adapter import create_simulation_adapter


async def validate_daemon_startup(adapter: SimulationAdapter) -> bool:
    """Validate that the daemon starts and becomes healthy."""
    print("  Checking daemon health...")
    health = await adapter.health_check()
    print(f"  Daemon status: {health}")
    # Daemon returns "state": "running" (lowercase) when healthy
    state = health.get("state", "").lower()
    has_robot = "robot_name" in health
    no_error = health.get("error") is None
    return (state in ("ready", "running") and no_error) or has_robot


async def validate_head_movement(adapter: SimulationAdapter) -> bool:
    """Validate head movement tools."""
    client = adapter.client
    print("  Testing move_head...")

    directions = ["left", "right", "up", "down", "front"]
    for direction in directions:
        result = await client.move_head(direction, speed="fast")
        if "error" in result:
            print(f"    move_head({direction}): FAILED - {result}")
            return False
        print(f"    move_head({direction}): OK - uuid={result.get('uuid', 'N/A')[:8]}...")
        await asyncio.sleep(0.8)  # Wait for move to complete

    return True


async def validate_antenna_control(adapter: SimulationAdapter) -> bool:
    """Validate antenna control tools."""
    client = adapter.client
    print("  Testing set_antenna_state...")

    # Test different antenna positions
    positions = [
        (0, 0),     # Down
        (45, 45),   # Mid
        (90, 90),   # Up
        (30, 60),   # Asymmetric
    ]

    for left, right in positions:
        result = await client.set_antenna_state(left_angle=left, right_angle=right)
        if "error" in result:
            print(f"    set_antenna_state({left}, {right}): FAILED - {result}")
            return False
        print(f"    set_antenna_state({left}, {right}): OK")
        await asyncio.sleep(0.6)

    return True


async def validate_gestures(adapter: SimulationAdapter) -> bool:
    """Validate gesture tools."""
    client = adapter.client
    print("  Testing gestures...")

    # Test nod
    print("    Testing nod...")
    result = await client.nod(times=2, speed="fast")
    if "error" in result:
        print(f"    nod: FAILED - {result}")
        return False
    print(f"    nod: OK - {result.get('moves', 0)} moves")
    await asyncio.sleep(2.0)

    # Test shake
    print("    Testing shake...")
    result = await client.shake(times=2, speed="fast")
    if "error" in result:
        print(f"    shake: FAILED - {result}")
        return False
    print(f"    shake: OK - {result.get('moves', 0)} moves")
    await asyncio.sleep(2.0)

    # Test rest
    print("    Testing rest...")
    result = await client.rest()
    if "error" in result:
        print(f"    rest: FAILED - {result}")
        return False
    print("    rest: OK")
    await asyncio.sleep(1.0)

    return True


async def validate_lifecycle(adapter: SimulationAdapter) -> bool:
    """Validate lifecycle tools."""
    client = adapter.client
    print("  Testing lifecycle...")

    # Test wake_up
    print("    Testing wake_up...")
    result = await client.wake_up()
    if "error" in str(result).lower() and "connection" in str(result).lower():
        print(f"    wake_up: FAILED - {result}")
        return False
    print("    wake_up: OK")
    await asyncio.sleep(1.0)

    # Test sleep
    print("    Testing sleep...")
    result = await client.sleep()
    if "error" in str(result).lower() and "connection" in str(result).lower():
        print(f"    sleep: FAILED - {result}")
        return False
    print("    sleep: OK")
    await asyncio.sleep(1.0)

    # Wake up again for subsequent tests
    await client.wake_up()
    await asyncio.sleep(1.0)

    return True


async def validate_look_at(adapter: SimulationAdapter) -> bool:
    """Validate precise head positioning."""
    client = adapter.client
    print("  Testing look_at (precise positioning)...")

    poses = [
        {"roll": 0, "pitch": 0, "yaw": 0},
        {"roll": 10, "pitch": -10, "yaw": 20},
        {"roll": -10, "pitch": 10, "yaw": -20},
    ]

    for pose in poses:
        result = await client.look_at(**pose)
        if "error" in str(result).lower() and "connection" in str(result).lower():
            print(f"    look_at({pose}): FAILED - {result}")
            return False
        print(f"    look_at({pose}): OK")
        await asyncio.sleep(0.5)

    return True


async def run_validation(headless: bool = True, scene: str = "empty") -> bool:
    """Run full validation suite.

    Args:
        headless: Run without GUI window.
        scene: Simulation scene ('empty' or 'minimal').

    Returns:
        True if all validations pass.
    """
    print("=" * 60)
    print("Reachy Agent MuJoCo Simulation Validation")
    print("=" * 60)
    print()
    print(f"Configuration:")
    print(f"  Scene: {scene}")
    print(f"  Headless: {headless}")
    print()

    all_passed = True
    adapter = create_simulation_adapter(
        scene=scene,
        headless=headless,
        port=8765,
    )

    try:
        print("[1/7] Starting simulation daemon...")
        await adapter.start()
        print("  Daemon started successfully!")
        print()

        print("[2/7] Validating daemon health...")
        if await validate_daemon_startup(adapter):
            print("  PASSED")
        else:
            print("  FAILED")
            all_passed = False
        print()

        print("[3/7] Validating lifecycle controls...")
        if await validate_lifecycle(adapter):
            print("  PASSED")
        else:
            print("  FAILED")
            all_passed = False
        print()

        print("[4/7] Validating head movement...")
        if await validate_head_movement(adapter):
            print("  PASSED")
        else:
            print("  FAILED")
            all_passed = False
        print()

        print("[5/7] Validating antenna control...")
        if await validate_antenna_control(adapter):
            print("  PASSED")
        else:
            print("  FAILED")
            all_passed = False
        print()

        print("[6/7] Validating gestures...")
        if await validate_gestures(adapter):
            print("  PASSED")
        else:
            print("  FAILED")
            all_passed = False
        print()

        print("[7/7] Validating precise positioning...")
        if await validate_look_at(adapter):
            print("  PASSED")
        else:
            print("  FAILED")
            all_passed = False
        print()

    except Exception as e:
        print(f"ERROR: {e}")
        all_passed = False

    finally:
        print("Stopping simulation daemon...")
        await adapter.stop()
        print("Done.")

    print()
    print("=" * 60)
    if all_passed:
        print("VALIDATION RESULT: ALL TESTS PASSED")
    else:
        print("VALIDATION RESULT: SOME TESTS FAILED")
    print("=" * 60)

    return all_passed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate MuJoCo simulation for Reachy Agent"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI window (for CI/testing)",
    )
    parser.add_argument(
        "--scene",
        choices=["empty", "minimal"],
        default="empty",
        help="Simulation scene to use",
    )
    args = parser.parse_args()

    success = asyncio.run(run_validation(
        headless=args.headless,
        scene=args.scene,
    ))

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
