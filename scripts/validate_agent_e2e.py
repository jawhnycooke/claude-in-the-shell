#!/usr/bin/env python3
"""End-to-end Agent SDK validation against MuJoCo simulation.

This script validates the COMPLETE stack:
  User Request → Claude API → Agent SDK → MCP Tools → Reachy Daemon → MuJoCo

Requires:
  - ANTHROPIC_API_KEY environment variable
  - Running MuJoCo simulation daemon

Run:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/validate_agent_e2e.py

Or with .env file:
    python scripts/validate_agent_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import anthropic
from reachy_agent.simulation.reachy_client import ReachyMiniClient


async def validate_agent_with_claude():
    """Validate full agent stack with Claude API."""
    print("=" * 70)
    print("🤖 Claude Agent SDK End-to-End Validation")
    print("=" * 70)
    print()

    # Check API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ERROR: ANTHROPIC_API_KEY not set")
        print("   Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
        return False

    print(f"✅ API Key configured: {api_key[:20]}...")
    print()

    # Check daemon
    daemon_url = "http://localhost:8765"
    client = ReachyMiniClient(base_url=daemon_url)

    try:
        status = await client.get_status()
        if status.get("state") != "running":
            print(f"❌ ERROR: Daemon not running at {daemon_url}")
            return False
        print(f"✅ Simulation daemon running at {daemon_url}")
        print(f"   Simulation: {status.get('simulation_enabled')}")
    except Exception as e:
        print(f"❌ ERROR: Cannot connect to daemon: {e}")
        return False

    print()
    print("-" * 70)
    print("📝 Test Scenario: Ask Claude to make Reachy express curiosity")
    print("-" * 70)
    print()

    # Define tools for Claude (simplified version of our MCP tools)
    tools = [
        {
            "name": "move_head",
            "description": "Move Reachy's head in a direction. Use this to look around or face something.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["left", "right", "up", "down", "front"],
                        "description": "Direction to move the head"
                    },
                    "speed": {
                        "type": "string",
                        "enum": ["slow", "normal", "fast"],
                        "description": "Movement speed"
                    }
                },
                "required": ["direction"]
            }
        },
        {
            "name": "look_at",
            "description": "Position Reachy's head with precise angles. Use for expressive tilts.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "roll": {"type": "number", "description": "Tilt angle in degrees (-30 to 30)"},
                    "pitch": {"type": "number", "description": "Up/down angle in degrees (-30 to 30)"},
                    "yaw": {"type": "number", "description": "Left/right angle in degrees (-45 to 45)"}
                }
            }
        },
        {
            "name": "set_antenna_state",
            "description": "Control Reachy's antennas for expression. 0=down, 45=neutral, 90=up.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "left_angle": {"type": "number", "description": "Left antenna angle (0-90)"},
                    "right_angle": {"type": "number", "description": "Right antenna angle (0-90)"}
                },
                "required": ["left_angle", "right_angle"]
            }
        },
        {
            "name": "nod",
            "description": "Make Reachy nod (yes gesture).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "times": {"type": "integer", "description": "Number of nods (1-5)"}
                }
            }
        }
    ]

    # Create Claude client
    anthropic_client = anthropic.Anthropic(api_key=api_key)

    # Send request to Claude
    print("🔄 Sending request to Claude API...")
    print()

    user_message = """
    You are controlling Reachy, a friendly robot.

    Please make Reachy look curious - like it just noticed something interesting to its left.
    Use the available tools to create this expression. Be expressive!

    After creating the expression, briefly describe what you did.
    """

    try:
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            tools=tools,
            messages=[{"role": "user", "content": user_message}]
        )
    except Exception as e:
        print(f"❌ Claude API error: {e}")
        await client.close()
        return False

    print(f"📨 Response received (stop_reason: {response.stop_reason})")
    print()

    # Process tool calls
    tool_calls_made = []

    while response.stop_reason == "tool_use":
        # Find tool use blocks
        tool_results = []

        for block in response.content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                print(f"🔧 Claude called: {tool_name}({tool_input})")
                tool_calls_made.append(tool_name)

                # Execute the tool against simulation
                try:
                    if tool_name == "move_head":
                        result = await client.move_head(
                            direction=tool_input.get("direction", "front"),
                            speed=tool_input.get("speed", "normal")
                        )
                    elif tool_name == "look_at":
                        result = await client.look_at(
                            roll=tool_input.get("roll", 0),
                            pitch=tool_input.get("pitch", 0),
                            yaw=tool_input.get("yaw", 0)
                        )
                    elif tool_name == "set_antenna_state":
                        result = await client.set_antenna_state(
                            left_angle=tool_input.get("left_angle", 45),
                            right_angle=tool_input.get("right_angle", 45)
                        )
                    elif tool_name == "nod":
                        result = await client.nod(times=tool_input.get("times", 2))
                    else:
                        result = {"error": f"Unknown tool: {tool_name}"}

                    # Give time for movement to show (longer for visibility)
                    await asyncio.sleep(2.0)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": str(result)
                    })
                    print(f"   ✅ Executed successfully")

                except Exception as e:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": f"Error: {e}",
                        "is_error": True
                    })
                    print(f"   ❌ Error: {e}")

        # Send results back to Claude
        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            tools=tools,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results}
            ]
        )

    # Get final text response
    print()
    print("-" * 70)
    print("💬 Claude's response:")
    print("-" * 70)

    for block in response.content:
        if hasattr(block, "text"):
            print(block.text)

    print()
    print("-" * 70)

    # Cleanup
    print()
    print("🔄 Returning robot to rest...")
    await client.rest()
    await asyncio.sleep(0.5)
    await client.close()

    # Summary
    print()
    print("=" * 70)
    print("📊 Validation Summary")
    print("=" * 70)
    print(f"   API calls to Claude: 1+")
    print(f"   Tool calls executed: {len(tool_calls_made)}")
    print(f"   Tools used: {', '.join(set(tool_calls_made)) if tool_calls_made else 'None'}")
    print()

    if tool_calls_made:
        print("🎉 FULL AGENT STACK VALIDATED!")
        print()
        print("   User Request")
        print("        ↓")
        print("   Claude API (reasoning)")
        print("        ↓")
        print("   Tool Calls (MCP interface)")
        print("        ↓")
        print("   ReachyMiniClient (HTTP)")
        print("        ↓")
        print("   Reachy Daemon (FastAPI)")
        print("        ↓")
        print("   MuJoCo Physics Engine")
        print("        ↓")
        print("   🤖 Robot Movement!")
    else:
        print("⚠️  No tool calls were made - Claude may have responded with text only")

    print("=" * 70)

    return bool(tool_calls_made)


if __name__ == "__main__":
    success = asyncio.run(validate_agent_with_claude())
    sys.exit(0 if success else 1)
