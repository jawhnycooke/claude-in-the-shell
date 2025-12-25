"""Memory MCP Server entry point for subprocess execution.

Run as: python -m reachy_agent.mcp_servers.memory
"""

import asyncio
import os
import sys

from reachy_agent.memory import MemoryManager
from reachy_agent.mcp_servers.memory import create_memory_mcp_server


async def main() -> None:
    """Initialize and run the Memory MCP server."""
    # Get paths from environment or use defaults
    chroma_path = os.environ.get(
        "REACHY_MEMORY_CHROMA_PATH",
        os.path.expanduser("~/.reachy/memory/chroma"),
    )
    sqlite_path = os.environ.get(
        "REACHY_MEMORY_SQLITE_PATH",
        os.path.expanduser("~/.reachy/memory/reachy.db"),
    )
    embedding_model = os.environ.get(
        "REACHY_MEMORY_EMBEDDING_MODEL",
        "all-MiniLM-L6-v2",
    )

    # Initialize memory manager with proper resource cleanup
    manager = MemoryManager(
        chroma_path=chroma_path,
        sqlite_path=sqlite_path,
        embedding_model=embedding_model,
    )

    try:
        await manager.initialize()

        # Create and run MCP server
        mcp = create_memory_mcp_server(manager)
        await mcp.run_async()
    finally:
        # Always close manager, even if initialization failed partway
        await manager.close()


if __name__ == "__main__":
    asyncio.run(main())
