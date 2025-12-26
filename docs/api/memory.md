# Memory Module API

The memory module provides semantic memory storage and user profile management.

## Memory Manager

::: reachy_agent.memory.manager.MemoryManager
    options:
      show_source: true
      members:
        - __init__
        - from_config
        - initialize
        - close
        - start_session
        - end_session
        - store_memory
        - search_memories
        - get_memory
        - delete_memory
        - memory_count
        - get_profile
        - save_profile
        - update_preference
        - get_last_session
        - cleanup

## Types

### Memory

::: reachy_agent.memory.types.Memory

### MemoryType

::: reachy_agent.memory.types.MemoryType

### UserProfile

::: reachy_agent.memory.types.UserProfile

### SessionSummary

::: reachy_agent.memory.types.SessionSummary

### SearchResult

::: reachy_agent.memory.types.SearchResult

## Storage Backends

### ChromaDB Store

::: reachy_agent.memory.storage.chroma_store.ChromaMemoryStore
    options:
      show_source: true
      members:
        - __init__
        - initialize
        - store
        - search
        - get
        - delete
        - count
        - cleanup
        - close

### SQLite Store

::: reachy_agent.memory.storage.sqlite_store.SQLiteProfileStore
    options:
      show_source: true
      members:
        - __init__
        - initialize
        - get_profile
        - save_profile
        - update_preference
        - save_session
        - get_last_session
        - close

## Embeddings

::: reachy_agent.memory.embeddings.EmbeddingService
    options:
      show_source: true
      members:
        - __init__
        - embed
        - embed_batch

## Context Builder

::: reachy_agent.memory.context_builder
    options:
      show_source: true
      members:
        - build_memory_context

## Usage Example

```python
from reachy_agent.memory.manager import MemoryManager
from reachy_agent.memory.types import MemoryType

# Initialize
manager = MemoryManager(
    chroma_path="~/.reachy/memory/chroma",
    sqlite_path="~/.reachy/memory/reachy.db",
)
await manager.initialize()

# Session management
await manager.start_session(user_id="alice")

# Store memories
await manager.store_memory(
    "User prefers morning meetings",
    MemoryType.PREFERENCE
)

# Search memories
results = await manager.search_memories("meeting preferences")
for result in results:
    print(f"{result.memory.content} (score: {result.score})")

# Profile operations
profile = await manager.get_profile()
await manager.update_preference("greeting", "informal")

# Cleanup and close
await manager.end_session(
    summary_text="Discussed scheduling preferences",
    key_topics=["meetings", "calendar"]
)
await manager.close()
```

## Configuration

Memory is configured in `config/default.yaml`:

```yaml
memory:
  chroma_path: ~/.reachy/memory/chroma
  sqlite_path: ~/.reachy/memory/reachy.db
  embedding_model: all-MiniLM-L6-v2
  max_memories: 10000
  retention_days: 90
```

## Related Documentation

- [Memory System Architecture](../../ai_docs/memory-system.md)
