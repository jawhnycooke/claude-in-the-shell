"""Unit tests for memory type definitions."""

import json
from datetime import datetime

import pytest

from reachy_agent.memory.types import (
    Memory,
    MemoryType,
    SearchResult,
    SessionSummary,
    UserProfile,
)


class TestMemoryType:
    """Tests for MemoryType enum."""

    def test_all_types_defined(self) -> None:
        """Verify all expected memory types exist."""
        expected = {"conversation", "observation", "fact", "preference", "event", "task"}
        actual = {t.value for t in MemoryType}
        assert actual == expected

    def test_from_string_valid(self) -> None:
        """Test parsing valid memory type strings."""
        assert MemoryType.from_string("fact") == MemoryType.FACT
        assert MemoryType.from_string("PREFERENCE") == MemoryType.PREFERENCE
        assert MemoryType.from_string("Conversation") == MemoryType.CONVERSATION

    def test_from_string_invalid_defaults_to_fact(self) -> None:
        """Test that invalid strings default to FACT type."""
        assert MemoryType.from_string("invalid") == MemoryType.FACT
        assert MemoryType.from_string("") == MemoryType.FACT


class TestMemory:
    """Tests for Memory dataclass."""

    def test_memory_creation(self) -> None:
        """Test creating a memory with all fields."""
        memory = Memory(
            id="test-123",
            content="User likes coffee",
            memory_type=MemoryType.PREFERENCE,
            metadata={"source": "conversation"},
        )
        assert memory.id == "test-123"
        assert memory.content == "User likes coffee"
        assert memory.memory_type == MemoryType.PREFERENCE
        assert memory.metadata == {"source": "conversation"}
        assert memory.embedding is None

    def test_memory_to_dict(self) -> None:
        """Test converting memory to dictionary."""
        timestamp = datetime(2024, 12, 25, 10, 30, 0)
        memory = Memory(
            id="test-123",
            content="Test content",
            memory_type=MemoryType.FACT,
            timestamp=timestamp,
        )
        result = memory.to_dict()

        assert result["id"] == "test-123"
        assert result["content"] == "Test content"
        assert result["memory_type"] == "fact"
        assert result["timestamp"] == "2024-12-25T10:30:00"

    def test_memory_from_dict(self) -> None:
        """Test creating memory from dictionary."""
        data = {
            "id": "test-456",
            "content": "Test content",
            "memory_type": "preference",
            "timestamp": "2024-12-25T10:30:00",
            "metadata": {"key": "value"},
        }
        memory = Memory.from_dict(data)

        assert memory.id == "test-456"
        assert memory.content == "Test content"
        assert memory.memory_type == MemoryType.PREFERENCE
        assert memory.metadata == {"key": "value"}


class TestUserProfile:
    """Tests for UserProfile model."""

    def test_default_profile(self) -> None:
        """Test creating a profile with defaults."""
        profile = UserProfile()
        assert profile.user_id == "default"
        assert profile.name == "User"
        assert profile.preferences == {}
        assert profile.connected_services == []

    def test_preference_operations(self) -> None:
        """Test getting and setting preferences."""
        profile = UserProfile()
        assert profile.get_preference("coffee") == ""
        assert profile.get_preference("coffee", "tea") == "tea"

        profile.set_preference("coffee", "black, no sugar")
        assert profile.get_preference("coffee") == "black, no sugar"

    def test_to_context_string_minimal(self) -> None:
        """Test context string with minimal profile."""
        profile = UserProfile()
        result = profile.to_context_string()
        assert "- **Name**: User" in result

    def test_to_context_string_full(self) -> None:
        """Test context string with full profile."""
        profile = UserProfile(
            name="John",
            preferences={"wake_time": "7:00 AM", "coffee": "black"},
            schedule_patterns="Works 9-5 weekdays",
            connected_services=["Home Assistant", "Calendar"],
        )
        result = profile.to_context_string()

        assert "- **Name**: John" in result
        assert "- **Preferences**:" in result
        assert "wake_time: 7:00 AM" in result
        assert "- **Schedule**: Works 9-5 weekdays" in result
        assert "- **Connected services**: Home Assistant, Calendar" in result

    def test_to_db_dict(self) -> None:
        """Test converting profile to database format."""
        profile = UserProfile(
            user_id="user-123",
            name="John",
            preferences={"key": "value"},
            connected_services=["service1"],
        )
        result = profile.to_db_dict()

        assert result["user_id"] == "user-123"
        assert result["name"] == "John"
        assert json.loads(result["preferences"]) == {"key": "value"}
        assert json.loads(result["connected_services"]) == ["service1"]

    def test_from_db_dict(self) -> None:
        """Test creating profile from database row."""
        data = {
            "user_id": "user-456",
            "name": "Jane",
            "preferences": '{"key": "value"}',
            "schedule_patterns": "Flexible",
            "connected_services": '["service1", "service2"]',
            "created_at": "2024-12-25T10:00:00",
            "updated_at": "2024-12-25T11:00:00",
        }
        profile = UserProfile.from_db_dict(data)

        assert profile.user_id == "user-456"
        assert profile.name == "Jane"
        assert profile.preferences == {"key": "value"}
        assert profile.connected_services == ["service1", "service2"]


class TestSessionSummary:
    """Tests for SessionSummary model."""

    def test_session_creation(self) -> None:
        """Test creating a session summary."""
        session = SessionSummary(
            session_id="session-123",
            summary_text="Discussed weekend plans",
            key_topics=["weekend", "plans"],
        )
        assert session.session_id == "session-123"
        assert session.user_id == "default"
        assert session.end_time is None

    def test_to_context_string_no_data(self) -> None:
        """Test context string with no summary data."""
        session = SessionSummary(session_id="s1")
        result = session.to_context_string()
        assert result == "No previous session"

    def test_to_context_string_with_data(self) -> None:
        """Test context string with full data."""
        session = SessionSummary(
            session_id="s1",
            summary_text="Discussed weekend plans",
            end_time=datetime(2024, 12, 24, 18, 30),
            key_topics=["weekend", "groceries"],
        )
        result = session.to_context_string()

        assert "- **Summary**: Discussed weekend plans" in result
        assert "- **Ended**: 2024-12-24 18:30" in result
        assert "- **Key topics**: weekend, groceries" in result

    def test_to_db_dict(self) -> None:
        """Test converting session to database format."""
        session = SessionSummary(
            session_id="s1",
            user_id="u1",
            start_time=datetime(2024, 12, 25, 10, 0),
            end_time=datetime(2024, 12, 25, 11, 0),
            summary_text="Test",
            key_topics=["a", "b"],
            memory_count=5,
        )
        result = session.to_db_dict()

        assert result["session_id"] == "s1"
        assert result["user_id"] == "u1"
        assert json.loads(result["key_topics"]) == ["a", "b"]
        assert result["memory_count"] == 5

    def test_from_db_dict(self) -> None:
        """Test creating session from database row."""
        data = {
            "session_id": "s2",
            "user_id": "u2",
            "start_time": "2024-12-25T10:00:00",
            "end_time": "2024-12-25T11:00:00",
            "summary_text": "Summary",
            "key_topics": '["topic1"]',
            "memory_count": 3,
        }
        session = SessionSummary.from_db_dict(data)

        assert session.session_id == "s2"
        assert session.end_time is not None
        assert session.key_topics == ["topic1"]


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result_creation(self) -> None:
        """Test creating a search result."""
        memory = Memory(
            id="m1",
            content="Test",
            memory_type=MemoryType.FACT,
        )
        result = SearchResult(memory=memory, score=0.95)

        assert result.memory.id == "m1"
        assert result.score == 0.95

    def test_to_dict(self) -> None:
        """Test converting search result to dictionary."""
        memory = Memory(
            id="m1",
            content="Test",
            memory_type=MemoryType.FACT,
        )
        result = SearchResult(memory=memory, score=0.85)
        data = result.to_dict()

        assert data["score"] == 0.85
        assert data["memory"]["id"] == "m1"
