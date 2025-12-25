"""Memory MCP Server - Exposes memory operations as MCP tools.

Provides 4 tools for memory management:
- search_memories: Semantic search over stored memories
- store_memory: Save a new memory
- get_user_profile: Retrieve user profile
- update_user_profile: Update a user preference
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from reachy_agent.memory import MemoryManager, MemoryType
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


def create_memory_mcp_server(
    manager: MemoryManager,
) -> FastMCP:
    """Create and configure the Memory MCP server.

    Args:
        manager: Initialized MemoryManager instance.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP("Memory System")

    @mcp.tool()
    async def search_memories(
        query: str,
        n_results: int = 5,
        memory_type: str | None = None,
    ) -> dict:
        """Search memories by semantic similarity.

        Use this to find relevant past memories, facts, preferences,
        or observations that might help answer the current question.

        Args:
            query: Natural language search query describing what you're looking for.
            n_results: Maximum number of results to return (default: 5).
            memory_type: Optional filter by type (conversation, observation,
                        fact, preference, event, task).

        Returns:
            Dictionary with list of matching memories and their relevance scores.

        Example:
            search_memories("user's coffee preferences") -> finds preferences about coffee
            search_memories("previous conversations about travel", memory_type="conversation")
        """
        log.info(f"Searching memories: {query}")

        # Parse memory type if provided
        type_filter = None
        if memory_type:
            try:
                type_filter = MemoryType.from_string(memory_type)
            except ValueError:
                return {
                    "error": f"Invalid memory_type. Must be one of: {[t.value for t in MemoryType]}"
                }

        # Clamp n_results to reasonable range
        n_results = max(1, min(n_results, 20))

        try:
            results = await manager.search_memories(query, n_results, type_filter)

            return {
                "status": "ok",
                "count": len(results),
                "memories": [
                    {
                        "content": r.memory.content,
                        "type": r.memory.memory_type.value,
                        "score": round(r.score, 3),
                        "timestamp": r.memory.timestamp.isoformat(),
                    }
                    for r in results
                ],
            }
        except Exception as e:
            log.error(f"Memory search failed: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def store_memory(
        content: str,
        memory_type: str = "fact",
    ) -> dict:
        """Store a new memory for future retrieval.

        Use this to save important information learned during the conversation
        that should be remembered for future sessions.

        Args:
            content: The information to remember (be specific and concise).
            memory_type: Category of memory:
                - conversation: Dialog exchanges
                - observation: Things seen or heard
                - fact: Learned facts about the user or world
                - preference: User preferences
                - event: Calendar events or schedules
                - task: Tasks or reminders

        Returns:
            Confirmation with the stored memory ID.

        Example:
            store_memory("User prefers morning meetings before 10am", "preference")
            store_memory("User mentioned they have a dog named Max", "fact")
        """
        log.info(f"Storing memory: {content[:50]}...")

        # Validate memory type
        try:
            mem_type = MemoryType.from_string(memory_type)
        except ValueError:
            return {
                "error": f"Invalid memory_type. Must be one of: {[t.value for t in MemoryType]}"
            }

        # Validate content length
        if not content or len(content.strip()) < 5:
            return {"error": "Content must be at least 5 characters"}
        if len(content) > 2000:
            return {"error": "Content must be less than 2000 characters"}

        try:
            memory = await manager.store_memory(content.strip(), mem_type)

            return {
                "status": "ok",
                "message": f"Memory stored successfully",
                "memory_id": memory.id,
                "type": mem_type.value,
            }
        except Exception as e:
            log.error(f"Failed to store memory: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def get_user_profile() -> dict:
        """Get the current user's profile and preferences.

        Use this to retrieve stored information about the user including
        their name, preferences, schedule patterns, and connected services.

        Returns:
            User profile with all stored preferences.
        """
        log.info("Getting user profile")

        try:
            profile = await manager.get_profile()

            return {
                "status": "ok",
                "profile": {
                    "user_id": profile.user_id,
                    "name": profile.name,
                    "preferences": profile.preferences,
                    "schedule_patterns": profile.schedule_patterns,
                    "connected_services": profile.connected_services,
                },
            }
        except Exception as e:
            log.error(f"Failed to get profile: {e}")
            return {"error": str(e)}

    @mcp.tool()
    async def update_user_profile(
        key: str,
        value: str,
    ) -> dict:
        """Update a user preference.

        Use this when the user explicitly states a preference that should
        be remembered for future sessions.

        Args:
            key: The preference key (e.g., "wake_time", "coffee_preference",
                "nickname", "timezone").
            value: The preference value.

        Returns:
            Confirmation of the update.

        Example:
            update_user_profile("nickname", "John")
            update_user_profile("wake_time", "7:00 AM")
            update_user_profile("coffee_preference", "black, no sugar")
        """
        log.info(f"Updating preference: {key}={value}")

        # Validate inputs
        if not key or len(key.strip()) < 2:
            return {"error": "Key must be at least 2 characters"}
        if len(key) > 50:
            return {"error": "Key must be less than 50 characters"}
        if len(value) > 500:
            return {"error": "Value must be less than 500 characters"}

        try:
            profile = await manager.update_preference(key.strip(), value.strip())

            return {
                "status": "ok",
                "message": f"Updated preference '{key}'",
                "preferences": profile.preferences,
            }
        except Exception as e:
            log.error(f"Failed to update preference: {e}")
            return {"error": str(e)}

    return mcp
