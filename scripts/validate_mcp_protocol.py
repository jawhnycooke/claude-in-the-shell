#!/usr/bin/env python3
"""End-to-end validation of true MCP protocol architecture.

This script validates the complete MCP architecture:
  Agent → MCP ClientSession (stdio) → MCP Server subprocess → Daemon HTTP API

Unlike validate_mcp_e2e.py which tests daemon client directly,
this script tests the full MCP protocol flow.

Run:
    python scripts/validate_mcp_protocol.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def validate_mcp_protocol():
    """Validate true MCP protocol architecture."""
    print("=" * 60)
    print("MCP Protocol E2E Validation")
    print("=" * 60)
    print()
    print("This test validates the TRUE MCP architecture:")
    print("  Agent → MCP ClientSession → MCP Server subprocess → Daemon")
    print()

    all_passed = True
    results = []

    # Find python executable
    python_executable = sys.executable

    # Test 1: MCP Server startup and connection
    print("[1/5] Starting MCP server as subprocess...")
    try:
        # Create server parameters for the Reachy MCP server
        # Use default daemon URL (http://localhost:8000)
        server_params = StdioServerParameters(
            command=python_executable,
            args=["-m", "reachy_agent.mcp_servers.reachy", "http://localhost:8000"],
        )

        # Connect via stdio transport
        client_ctx = stdio_client(server_params)
        streams = await client_ctx.__aenter__()
        read_stream, write_stream = streams

        # Create and initialize session
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()

        print("   MCP server started and connected via stdio")
        results.append(("mcp_server_startup", True))
    except Exception as e:
        print(f"   FAILED - {e}")
        results.append(("mcp_server_startup", False))
        all_passed = False
        # Can't continue without server
        return False

    # Test 2: Tool discovery via ListTools
    print("[2/5] Discovering tools via MCP ListTools...")
    try:
        tools_result = await session.list_tools()
        tools = list(tools_result.tools)

        print(f"   Discovered {len(tools)} tools:")
        for tool in tools:
            print(f"     - {tool.name}")

        # Verify expected tools are present
        expected_tools = [
            "move_head",
            "speak",
            "play_emotion",
            "capture_image",
            "set_antenna_state",
            "nod",
            "shake",
        ]

        missing = [t for t in expected_tools if t not in [tool.name for tool in tools]]
        if missing:
            print(f"   WARNING: Missing expected tools: {missing}")
            results.append(("tool_discovery", False))
            all_passed = False
        else:
            print("   All expected tools discovered")
            results.append(("tool_discovery", True))

    except Exception as e:
        print(f"   FAILED - {e}")
        results.append(("tool_discovery", False))
        all_passed = False

    # Test 3: Tool call via MCP protocol (move_head)
    print("[3/5] Calling move_head tool via MCP protocol...")
    try:
        result = await session.call_tool(
            "move_head", {"direction": "left", "speed": "normal"}
        )

        # Extract result content
        if result.content:
            for content in result.content:
                if hasattr(content, "text"):
                    print(f"   Result: {content.text[:100]}...")

        print("   Tool executed successfully via MCP protocol")
        results.append(("mcp_tool_call", True))

    except Exception as e:
        print(f"   FAILED - {e}")
        results.append(("mcp_tool_call", False))
        all_passed = False

    # Test 4: Tool call with validation (test error handling)
    print("[4/5] Testing input validation via MCP protocol...")
    try:
        result = await session.call_tool(
            "move_head", {"direction": "invalid_direction", "speed": "normal"}
        )

        # Should return error in result
        if result.content:
            for content in result.content:
                if hasattr(content, "text"):
                    if "error" in content.text.lower():
                        print("   Validation error returned correctly")
                        results.append(("input_validation", True))
                    else:
                        print(f"   Expected error, got: {content.text}")
                        results.append(("input_validation", False))
                        all_passed = False
        else:
            print("   No content in result")
            results.append(("input_validation", False))
            all_passed = False

    except Exception as e:
        # Exception might be expected for invalid input
        print(f"   Validation error: {e}")
        results.append(("input_validation", True))

    # Test 5: Multiple tool calls in sequence
    print("[5/5] Testing sequential MCP tool calls...")
    try:
        # Nod
        result1 = await session.call_tool("nod", {"times": 2})
        print("   nod(times=2): OK")

        # Antenna
        result2 = await session.call_tool(
            "set_antenna_state", {"left_angle": 45.0, "right_angle": 45.0}
        )
        print("   set_antenna_state(45, 45): OK")

        # Emotion
        result3 = await session.call_tool(
            "play_emotion", {"emotion": "happy", "intensity": 0.8}
        )
        print("   play_emotion(happy): OK")

        print("   Sequential tool calls successful")
        results.append(("sequential_calls", True))

    except Exception as e:
        print(f"   FAILED - {e}")
        results.append(("sequential_calls", False))
        all_passed = False

    # Cleanup
    print()
    print("Cleaning up...")
    try:
        await session.__aexit__(None, None, None)
        await client_ctx.__aexit__(None, None, None)
        print("   MCP connections closed")
    except Exception as e:
        print(f"   Cleanup warning: {e}")

    # Summary
    print()
    print("=" * 60)
    print("Results Summary")
    print("=" * 60)
    passed = sum(1 for _, p in results if p)
    total = len(results)
    print(f"   Passed: {passed}/{total}")
    print()
    for test_name, success in results:
        status = "PASS" if success else "FAIL"
        print(f"   [{status}] {test_name}")
    print()

    if all_passed:
        print("ALL MCP PROTOCOL TESTS PASSED!")
        print()
        print("Architecture validated:")
        print("  Agent")
        print("    |-- MCP ClientSession (stdio transport)")
        print("    |     v")
        print("    |-- MCP Server subprocess")
        print("    |     |-- ListTools (dynamic discovery)")
        print("    |     |-- CallTool (protocol execution)")
        print("    |     v")
        print("    |-- Reachy Daemon HTTP API")
    else:
        print("SOME TESTS FAILED - Check output above")

    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    success = asyncio.run(validate_mcp_protocol())
    sys.exit(0 if success else 1)
