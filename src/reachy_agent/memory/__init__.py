"""Memory module - Short-term and long-term memory storage.

Provides semantic memory storage (ChromaDB) and structured profile/session
storage (SQLite) with auto-injection into Claude's system prompt.

Key Components:
- MemoryManager: Unified interface for all memory operations
- MemoryContextBuilder: Formats memory for system prompt injection
- ChromaMemoryStore: Vector-based semantic memory storage
- SQLiteProfileStore: User profiles and session summaries

Example:
    >>> from reachy_agent.memory import MemoryManager, MemoryType
    >>> manager = MemoryManager(
    ...     chroma_path="~/.reachy/memory/chroma",
    ...     sqlite_path="~/.reachy/memory/reachy.db",
    ... )
    >>> await manager.initialize()
    >>> await manager.store_memory("User prefers tea", MemoryType.PREFERENCE)
    >>> results = await manager.search_memories("beverage preferences")
"""

from reachy_agent.memory.context_builder import (
    MemoryContextBuilder,
    build_memory_context,
)
from reachy_agent.memory.embeddings import EmbeddingService, get_embedding_service
from reachy_agent.memory.manager import MemoryManager
from reachy_agent.memory.storage import ChromaMemoryStore, SQLiteProfileStore
from reachy_agent.memory.types import (
    Memory,
    MemoryType,
    SearchResult,
    SessionSummary,
    UserProfile,
)

__all__ = [
    # Manager
    "MemoryManager",
    # Context
    "MemoryContextBuilder",
    "build_memory_context",
    # Types
    "Memory",
    "MemoryType",
    "SearchResult",
    "SessionSummary",
    "UserProfile",
    # Storage
    "ChromaMemoryStore",
    "SQLiteProfileStore",
    # Embeddings
    "EmbeddingService",
    "get_embedding_service",
]
