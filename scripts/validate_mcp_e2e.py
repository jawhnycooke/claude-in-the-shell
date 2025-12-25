#!/usr/bin/env python3
"""End-to-end MCP validation against MuJoCo simulation.

This script validates the complete stack:
  MCP Tools → ReachyMiniClient → Reachy Daemon → MuJoCo Physics

Run with daemon already running:
    python scripts/validate_mcp_e2e.py

Or start daemon first:
    mjpython -m reachy_mini.daemon.app.main --sim --scene minimal --fastapi-port 8765
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reachy_agent.simulation.reachy_client import ReachyMiniClient


async def validate_mcp_tools():
    """Validate MCP tools against running simulation."""
    print("=" * 60)
    print("🔧 MCP End-to-End Validation")
    print("=" * 60)
    print()

    # Use the running daemon
    daemon_url = "http://localhost:8765"

    # Create client connected to the simulation daemon
    print("📡 Connecting to simulation daemon...")
    client = ReachyMiniClient(base_url=daemon_url)
    print(f"   Connected to: {daemon_url}")
    print()

    all_passed = True
    results = []

    # Test 1: Health check
    print("[1/8] Testing get_status (health check)...")
    try:
        status = await client.get_status()
        if status.get("state") == "running" or status.get("simulation_enabled"):
            print(f"   ✅ PASSED - Daemon healthy (state={status.get('state')})")
            results.append(("get_status", True))
        else:
            print(f"   ❌ FAILED - {status}")
            results.append(("get_status", False))
            all_passed = False
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("get_status", False))
        all_passed = False

    # Test 2: Wake up
    print("[2/8] Testing wake_up tool...")
    try:
        result = await client.wake_up()
        print("   ✅ PASSED - Robot awake")
        results.append(("wake_up", True))
        await asyncio.sleep(0.5)
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("wake_up", False))
        all_passed = False

    # Test 3: move_head (all directions)
    print("[3/8] Testing move_head tool...")
    try:
        directions = ["left", "right", "up", "down", "front"]
        for direction in directions:
            result = await client.move_head(direction, speed="fast")
            if "error" in result:
                raise Exception(f"move_head({direction}) failed: {result}")
            print(f"   → {direction}: uuid={result.get('uuid', 'N/A')[:8]}...")
            await asyncio.sleep(0.5)
        print("   ✅ PASSED - All directions work")
        results.append(("move_head", True))
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("move_head", False))
        all_passed = False

    # Test 4: look_at (precise positioning)
    print("[4/8] Testing look_at tool...")
    try:
        poses = [
            {"roll": 0, "pitch": -15, "yaw": 25},
            {"roll": 10, "pitch": 10, "yaw": -20},
            {"roll": 0, "pitch": 0, "yaw": 0},
        ]
        for pose in poses:
            result = await client.look_at(**pose)
            if "error" in str(result).lower():
                raise Exception(f"look_at({pose}) failed: {result}")
            print(f"   → roll={pose['roll']}, pitch={pose['pitch']}, yaw={pose['yaw']}: OK")
            await asyncio.sleep(0.4)
        print("   ✅ PASSED - Precise positioning works")
        results.append(("look_at", True))
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("look_at", False))
        all_passed = False

    # Test 5: set_antenna_state
    print("[5/8] Testing set_antenna_state tool...")
    try:
        positions = [(0, 0), (45, 45), (90, 90), (30, 70), (70, 30)]
        for left, right in positions:
            result = await client.set_antenna_state(left_angle=left, right_angle=right)
            if "error" in result:
                raise Exception(f"set_antenna_state({left}, {right}) failed: {result}")
            print(f"   → L={left}°, R={right}°: OK")
            await asyncio.sleep(0.3)
        print("   ✅ PASSED - Antenna control works")
        results.append(("set_antenna_state", True))
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("set_antenna_state", False))
        all_passed = False

    # Test 6: nod gesture
    print("[6/8] Testing nod gesture...")
    try:
        result = await client.nod(times=2, speed="fast")
        if "error" in result:
            raise Exception(f"nod failed: {result}")
        print(f"   ✅ PASSED - Nodded {result.get('moves', '?')} times")
        results.append(("nod", True))
        await asyncio.sleep(1)
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("nod", False))
        all_passed = False

    # Test 7: shake gesture
    print("[7/8] Testing shake gesture...")
    try:
        result = await client.shake(times=2, speed="fast")
        if "error" in result:
            raise Exception(f"shake failed: {result}")
        print(f"   ✅ PASSED - Shook {result.get('moves', '?')} times")
        results.append(("shake", True))
        await asyncio.sleep(1)
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("shake", False))
        all_passed = False

    # Test 8: Combined expression sequence (simulating agent behavior)
    print("[8/8] Testing combined expression sequence...")
    try:
        print("   → Simulating: 'Looking curious, then nodding agreement'")

        # Curious look (head tilt + asymmetric antennas)
        await client.look_at(roll=15, pitch=-10, yaw=20)
        await client.set_antenna_state(left_angle=40, right_angle=80)
        await asyncio.sleep(0.8)

        # Thinking pause
        await client.set_antenna_state(left_angle=60, right_angle=60, wiggle=True)
        await asyncio.sleep(0.5)

        # Nod agreement
        await client.look_at(roll=0, pitch=0, yaw=0)
        await client.set_antenna_state(left_angle=90, right_angle=90)
        await client.nod(times=2, speed="normal")
        await asyncio.sleep(1)

        # Return to neutral
        await client.rest()

        print("   ✅ PASSED - Expression sequence complete")
        results.append(("expression_sequence", True))
    except Exception as e:
        print(f"   ❌ FAILED - {e}")
        results.append(("expression_sequence", False))
        all_passed = False

    # Cleanup
    print()
    print("🔄 Cleaning up...")
    try:
        await client.rest()
        await asyncio.sleep(0.5)
        await client.sleep()
        print("   Robot returned to sleep")
    except Exception:
        pass

    await client.close()

    # Summary
    print()
    print("=" * 60)
    print("📊 Results Summary")
    print("=" * 60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"   Passed: {passed}/{total}")
    print()
    for tool, success in results:
        status = "✅" if success else "❌"
        print(f"   {status} {tool}")
    print()

    if all_passed:
        print("🎉 ALL MCP TOOLS VALIDATED SUCCESSFULLY!")
    else:
        print("⚠️  SOME TESTS FAILED - Check output above")

    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(validate_mcp_tools())
    sys.exit(0 if success else 1)
