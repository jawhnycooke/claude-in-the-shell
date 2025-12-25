"""Memory system type definitions.

Defines the core data models for the memory system:
- MemoryType: Categories of memories (conversation, observation, fact, etc.)
- Memory: A single memory item with embedding metadata
- UserProfile: User preferences and connected services
- SessionSummary: Summary of a conversation session
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Categories of memories stored in the system.

    Each type has different retention and retrieval characteristics:
    - conversation: Dialog exchanges, moderate retention
    - observation: Things seen/heard, short retention
    - fact: Learned facts, long retention
    - preference: User preferences, permanent
    - event: Calendar events, permanent until past
    - task: Tasks and reminders, permanent until completed
    """

    CONVERSATION = "conversation"
    OBSERVATION = "observation"
    FACT = "fact"
    PREFERENCE = "preference"
    EVENT = "event"
    TASK = "task"

    @classmethod
    def from_string(cls, value: str) -> MemoryType:
        """Parse a string into a MemoryType, case-insensitive."""
        try:
            return cls(value.lower())
        except ValueError:
            # Default to fact for unknown types
            return cls.FACT


@dataclass
class Memory:
    """A single memory item stored in ChromaDB.

    Attributes:
        id: Unique identifier for this memory
        content: The text content of the memory
        memory_type: Category of this memory
        timestamp: When this memory was created
        metadata: Additional key-value metadata
        embedding: Optional pre-computed embedding vector
    """

    id: str
    content: str
    memory_type: MemoryType
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Memory:
        """Create Memory from dictionary."""
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=MemoryType.from_string(data["memory_type"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            metadata=data.get("metadata", {}),
        )


class UserProfile(BaseModel):
    """User profile stored in SQLite.

    Contains personalization data that persists across sessions:
    - Name and basic info
    - Preferences (key-value pairs)
    - Schedule patterns (natural language)
    - Connected services list
    """

    user_id: str = Field(default="default")
    name: str = Field(default="User")
    preferences: dict[str, str] = Field(default_factory=dict)
    schedule_patterns: str = Field(default="")
    connected_services: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    def get_preference(self, key: str, default: str = "") -> str:
        """Get a preference value by key."""
        return self.preferences.get(key, default)

    def set_preference(self, key: str, value: str) -> None:
        """Set a preference value and update timestamp."""
        self.preferences[key] = value
        self.updated_at = datetime.now()

    def to_context_string(self) -> str:
        """Format profile for injection into system prompt."""
        lines = [f"- **Name**: {self.name}"]

        if self.preferences:
            lines.append("- **Preferences**:")
            for key, value in self.preferences.items():
                lines.append(f"  - {key}: {value}")

        if self.schedule_patterns:
            lines.append(f"- **Schedule**: {self.schedule_patterns}")

        if self.connected_services:
            services = ", ".join(self.connected_services)
            lines.append(f"- **Connected services**: {services}")

        return "\n".join(lines)

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SQLite storage."""
        return {
            "user_id": self.user_id,
            "name": self.name,
            "preferences": json.dumps(self.preferences),
            "schedule_patterns": self.schedule_patterns,
            "connected_services": json.dumps(self.connected_services),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_db_dict(cls, data: dict[str, Any]) -> UserProfile:
        """Create UserProfile from SQLite row."""
        return cls(
            user_id=data["user_id"],
            name=data["name"],
            preferences=json.loads(data.get("preferences", "{}")),
            schedule_patterns=data.get("schedule_patterns", ""),
            connected_services=json.loads(data.get("connected_services", "[]")),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class SessionSummary(BaseModel):
    """Summary of a conversation session.

    Stored in SQLite, one per session. Used for:
    - Injecting last session context
    - Continuity across conversations
    """

    session_id: str
    user_id: str = Field(default="default")
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime | None = None
    summary_text: str = Field(default="")
    key_topics: list[str] = Field(default_factory=list)
    memory_count: int = Field(default=0)

    def to_context_string(self) -> str:
        """Format session for injection into system prompt."""
        lines = []

        if self.summary_text:
            lines.append(f"- **Summary**: {self.summary_text}")

        if self.end_time:
            end_str = self.end_time.strftime("%Y-%m-%d %H:%M")
            lines.append(f"- **Ended**: {end_str}")

        if self.key_topics:
            topics = ", ".join(self.key_topics)
            lines.append(f"- **Key topics**: {topics}")

        return "\n".join(lines) if lines else "No previous session"

    def to_db_dict(self) -> dict[str, Any]:
        """Convert to dictionary for SQLite storage."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "summary_text": self.summary_text,
            "key_topics": json.dumps(self.key_topics),
            "memory_count": self.memory_count,
        }

    @classmethod
    def from_db_dict(cls, data: dict[str, Any]) -> SessionSummary:
        """Create SessionSummary from SQLite row."""
        return cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=(
                datetime.fromisoformat(data["end_time"])
                if data.get("end_time")
                else None
            ),
            summary_text=data.get("summary_text", ""),
            key_topics=json.loads(data.get("key_topics", "[]")),
            memory_count=data.get("memory_count", 0),
        )


@dataclass
class SearchResult:
    """Result from a memory search query.

    Includes the memory and its similarity score for ranking.
    """

    memory: Memory
    score: float  # Similarity score (0-1, higher is better)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "memory": self.memory.to_dict(),
            "score": self.score,
        }
