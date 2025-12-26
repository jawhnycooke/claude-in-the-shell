# Memory System Reference

The memory system provides long-term personalization for the Reachy Agent through semantic memory storage and auto-injection of user context.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│              AUTO-INJECTED (Every Turn)                 │
│  - User profile (name, preferences)                     │
│  - Last session summary                                 │
│  → Injected into system prompt automatically            │
└─────────────────────────────────────────────────────────┘
                          +
┌─────────────────────────────────────────────────────────┐
│              MCP TOOLS (On-Demand)                      │
│  - search_memories(query) - Semantic search             │
│  - store_memory(content, type) - Save new memory        │
│  - get_user_profile() - Retrieve profile                │
│  - update_user_profile(key, value) - Update preference  │
└─────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────────────────────────────────────┐
│              STORAGE LAYER                              │
│  ChromaDB: ~/.reachy/memory/chroma                      │
│  SQLite: ~/.reachy/memory/reachy.db                     │
└─────────────────────────────────────────────────────────┘
```

## MCP Memory Tools

| Tool | Purpose | Permission |
|------|---------|------------|
| `search_memories` | Semantic search over past memories | Tier 1 |
| `store_memory` | Save a new memory | Tier 1 |
| `get_user_profile` | Retrieve user profile | Tier 1 |
| `update_user_profile` | Update a user preference | Tier 1 |

### search_memories

Search memories by semantic similarity.

```json
{
  "query": "user's coffee preferences",
  "n_results": 5,
  "memory_type": "preference"
}
```

**Parameters:**
- `query` (string, required): Natural language search query
- `n_results` (int, optional): Max results (default: 5, max: 20)
- `memory_type` (string, optional): Filter by type

**Memory Types:**
- `conversation` - Dialog exchanges
- `observation` - Things seen/heard
- `fact` - Learned facts
- `preference` - User preferences
- `event` - Calendar events
- `task` - Tasks and reminders

### store_memory

Save a new memory for future retrieval.

```json
{
  "content": "User prefers morning meetings before 10am",
  "memory_type": "preference"
}
```

**Parameters:**
- `content` (string, required): Information to remember (5-2000 chars)
- `memory_type` (string, optional): Category (default: "fact")

### get_user_profile

Retrieve the current user's profile and preferences.

```json
{}
```

**Returns:**
```json
{
  "status": "ok",
  "profile": {
    "user_id": "default",
    "name": "John",
    "preferences": {
      "wake_time": "7:00 AM",
      "coffee_preference": "black, no sugar"
    },
    "schedule_patterns": "Works 9-5 weekdays",
    "connected_services": ["Home Assistant", "Calendar"]
  }
}
```

### update_user_profile

Update a user preference.

```json
{
  "key": "wake_time",
  "value": "7:00 AM"
}
```

**Parameters:**
- `key` (string, required): Preference key (2-50 chars)
- `value` (string, required): Preference value (max 500 chars)

## Auto-Injection

On every turn, memory context is automatically injected:

```markdown
# Memory Context

*Current time: 2024-12-25 10:30*

## User Profile
- **Name**: John
- **Preferences**:
  - wake_time: 7:00 AM
  - coffee_preference: black, no sugar
- **Connected services**: Home Assistant, Calendar

## Last Session
- **Summary**: Discussed weekend plans and set reminder for groceries
- **Ended**: 2024-12-24 18:30
- **Key topics**: weekend, groceries, reminder
```

## Configuration

Memory configuration in `config/default.yaml`:

```yaml
memory:
  chroma_path: ~/.reachy/memory/chroma
  sqlite_path: ~/.reachy/memory/reachy.db
  embedding_model: all-MiniLM-L6-v2
  max_memories: 10000
  retention_days: 90
```

## Module Structure

```
src/reachy_agent/memory/
├── __init__.py              # Public exports
├── types.py                 # Memory, UserProfile, SessionSummary
├── embeddings.py            # EmbeddingService (sentence-transformers)
├── storage/
│   ├── chroma_store.py      # ChromaDB semantic storage
│   └── sqlite_store.py      # SQLite profile storage
├── manager.py               # MemoryManager unified interface
└── context_builder.py       # Builds context for injection

src/reachy_agent/mcp_servers/memory/
├── __init__.py
├── __main__.py              # Subprocess entry point
└── memory_mcp.py            # MCP server with 4 tools
```

## Usage Examples

### Remembering User Preferences

When user says: "I prefer to wake up at 7am"
```
Claude calls: update_user_profile(key="wake_time", value="7:00 AM")
```

### Recalling Past Information

When user asks: "What did we discuss about travel?"
```
Claude calls: search_memories(query="travel plans", memory_type="conversation")
```

### Storing Important Facts

When learning something new:
```
Claude calls: store_memory(
  content="User has a dog named Max",
  memory_type="fact"
)
```

## MemoryManager API

The `MemoryManager` class provides a unified programmatic interface:

```python
from reachy_agent.memory.manager import MemoryManager
from reachy_agent.memory.types import MemoryType

# Initialize
manager = MemoryManager(
    chroma_path="~/.reachy/memory/chroma",
    sqlite_path="~/.reachy/memory/reachy.db",
)
await manager.initialize()

# Session lifecycle
session = await manager.start_session(user_id="alice")
await manager.end_session(
    summary_text="Discussed home automation",
    key_topics=["lights", "thermostat"]
)

# Memory operations
memory = await manager.store_memory(
    "User has a cat named Luna",
    MemoryType.FACT
)
results = await manager.search_memories("pets", n_results=5)
count = await manager.memory_count()

# Profile operations
profile = await manager.get_profile()
await manager.update_preference("greeting", "informal")

# Cleanup old memories
stats = await manager.cleanup()  # Returns {"memories_deleted": N, ...}

# Close connections
await manager.close()
```

## Data Models

### Memory

```python
@dataclass
class Memory:
    id: str                    # Unique UUID
    content: str               # Text content
    memory_type: MemoryType    # Category enum
    timestamp: datetime        # Creation time
    metadata: dict[str, Any]   # Additional key-value data
    embedding: list[float]     # Vector embedding (optional)
```

### SearchResult

```python
@dataclass
class SearchResult:
    memory: Memory
    score: float  # Similarity score (0-1, higher = more similar)
```

## Troubleshooting

### "ChromaDB initialization failed"

```bash
# Check disk space
df -h ~/.reachy

# Reset ChromaDB (loses memories)
rm -rf ~/.reachy/memory/chroma
python -m reachy_agent run  # Recreates on startup
```

### "Embedding model not found"

```bash
# Install sentence-transformers
uv pip install sentence-transformers

# Pre-download model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### "SQLite database locked"

```bash
# Find processes using the database
lsof ~/.reachy/memory/reachy.db

# Kill conflicting processes
kill <PID>
```

## Disabling Memory

To disable memory for a session:

```python
agent = ReachyAgentLoop(
    enable_memory=False,  # Disable memory system
)
```
