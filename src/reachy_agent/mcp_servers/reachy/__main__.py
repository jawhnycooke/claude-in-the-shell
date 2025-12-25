"""Entry point for running Reachy MCP server standalone.

This allows the MCP server to be run as a subprocess for true MCP protocol
communication. Other agents and clients (like Claude Desktop) can connect
to this server via stdio transport.

Usage:
    python -m reachy_agent.mcp_servers.reachy [daemon_url]

Examples:
    # Run with default daemon URL (http://localhost:8000)
    python -m reachy_agent.mcp_servers.reachy

    # Run with custom daemon URL
    python -m reachy_agent.mcp_servers.reachy http://192.168.1.100:8000

    # For Claude Desktop mcp.json:
    {
        "mcpServers": {
            "reachy": {
                "command": "python",
                "args": ["-m", "reachy_agent.mcp_servers.reachy"]
            }
        }
    }
"""

from __future__ import annotations

import asyncio
import sys

from reachy_agent.mcp_servers.reachy.reachy_mcp import create_reachy_mcp_server
from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


async def main() -> None:
    """Run the Reachy MCP server with stdio transport."""
    # Get daemon URL from command line args
    daemon_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    log.info("Starting Reachy MCP server", daemon_url=daemon_url)

    # Create the MCP server
    mcp = create_reachy_mcp_server(daemon_url=daemon_url)

    # Run with stdio transport for subprocess communication
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
