#!/usr/bin/env python3
"""Live demonstration of Reachy Mini simulation.

Run against an already-running daemon:
    python scripts/live_demo.py

Start daemon first with:
    python -m reachy_mini.daemon.app.main --sim --scene minimal --headless --fastapi-port 8765
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reachy_agent.simulation.reachy_client import ReachyMiniClient


async def demo():
    """Run live demonstration."""
    client = ReachyMiniClient(base_url="http://localhost:8765")

    print("=" * 60)
    print("🤖 Reachy Mini Live Demo")
    print("=" * 60)
    print()

    # 1. Wake up
    print("1️⃣  Waking up robot...")
    result = await client.wake_up()
    print(f"   ✓ {result}")
    await asyncio.sleep(1)

    # 2. Head movements
    print()
    print("2️⃣  Head movements:")
    for direction in ["left", "right", "up", "down", "front"]:
        print(f"   → Looking {direction}...", end=" ", flush=True)
        result = await client.move_head(direction, speed="fast")
        print(f"✓ uuid={result.get('uuid', 'N/A')[:8]}...")
        await asyncio.sleep(0.8)

    # 3. Antenna expressions
    print()
    print("3️⃣  Antenna expressions:")

    expressions = [
        ("Antennas down (sleeping)", 0, 0),
        ("Antennas mid (alert)", 45, 45),
        ("Antennas up (engaged)", 90, 90),
        ("Curious tilt", 30, 70),
        ("Other way", 70, 30),
    ]
    for name, left, right in expressions:
        print(f"   → {name}...", end=" ", flush=True)
        await client.set_antenna_state(left_angle=left, right_angle=right)
        print("✓")
        await asyncio.sleep(0.6)

    # 4. Gestures
    print()
    print("4️⃣  Gestures:")

    print("   → Nodding (yes)...", end=" ", flush=True)
    result = await client.nod(times=3, speed="normal")
    print(f"✓ {result.get('moves', 0)} moves")
    await asyncio.sleep(1.5)

    print("   → Shaking (no)...", end=" ", flush=True)
    result = await client.shake(times=3, speed="normal")
    print(f"✓ {result.get('moves', 0)} moves")
    await asyncio.sleep(1.5)

    # 5. Precise look_at
    print()
    print("5️⃣  Precise positioning:")

    poses = [
        {"roll": 15, "pitch": 0, "yaw": 0, "desc": "Tilt right"},
        {"roll": -15, "pitch": 0, "yaw": 0, "desc": "Tilt left"},
        {"roll": 0, "pitch": -20, "yaw": 30, "desc": "Look up-left"},
        {"roll": 0, "pitch": 20, "yaw": -30, "desc": "Look down-right"},
    ]
    for pose in poses:
        desc = pose.pop("desc")
        print(f"   → {desc}...", end=" ", flush=True)
        await client.look_at(**pose)
        print("✓")
        await asyncio.sleep(0.7)

    # 6. Return to rest
    print()
    print("6️⃣  Returning to rest position...")
    await client.rest()
    print("   ✓ Done!")

    # 7. Optional: sleep
    print()
    print("7️⃣  Going to sleep...")
    await client.sleep()
    print("   ✓ Robot is now sleeping")

    await client.close()

    print()
    print("=" * 60)
    print("✅ Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
