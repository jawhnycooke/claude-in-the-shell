"""Unit tests for SQLite profile store."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from reachy_agent.memory.storage.sqlite_store import SQLiteProfileStore
from reachy_agent.memory.types import SessionSummary, UserProfile


@pytest.fixture
def temp_db() -> Path:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


@pytest.fixture
async def store(temp_db: Path) -> SQLiteProfileStore:
    """Create and initialize a SQLite store."""
    store = SQLiteProfileStore(temp_db)
    await store.initialize()
    return store


class TestSQLiteProfileStore:
    """Tests for SQLiteProfileStore class."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, temp_db: Path) -> None:
        """Test that initialization creates required tables."""
        store = SQLiteProfileStore(temp_db)
        await store.initialize()

        # Tables should exist now
        import sqlite3

        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "user_profiles" in tables
        assert "sessions" in tables

    @pytest.mark.asyncio
    async def test_get_profile_creates_default(self, store: SQLiteProfileStore) -> None:
        """Test that get_profile creates a default profile if none exists."""
        profile = await store.get_profile("new-user")

        assert profile.user_id == "new-user"
        assert profile.name == "User"
        assert profile.preferences == {}

    @pytest.mark.asyncio
    async def test_save_and_get_profile(self, store: SQLiteProfileStore) -> None:
        """Test saving and retrieving a profile."""
        profile = UserProfile(
            user_id="test-user",
            name="John",
            preferences={"coffee": "black"},
            connected_services=["Home Assistant"],
        )
        await store.save_profile(profile)

        retrieved = await store.get_profile("test-user")

        assert retrieved.name == "John"
        assert retrieved.preferences == {"coffee": "black"}
        assert retrieved.connected_services == ["Home Assistant"]

    @pytest.mark.asyncio
    async def test_update_preference(self, store: SQLiteProfileStore) -> None:
        """Test updating a single preference."""
        # Create initial profile
        await store.get_profile("user1")

        # Update preference
        profile = await store.update_preference("wake_time", "7:00 AM", "user1")

        assert profile.preferences["wake_time"] == "7:00 AM"

        # Verify persisted
        retrieved = await store.get_profile("user1")
        assert retrieved.preferences["wake_time"] == "7:00 AM"

    @pytest.mark.asyncio
    async def test_delete_profile(self, store: SQLiteProfileStore) -> None:
        """Test deleting a profile."""
        # Create profile
        profile = UserProfile(user_id="to-delete", name="Temp")
        await store.save_profile(profile)

        # Delete it
        deleted = await store.delete_profile("to-delete")
        assert deleted is True

        # Verify gone (will create new default)
        retrieved = await store.get_profile("to-delete")
        assert retrieved.name == "User"  # New default

    @pytest.mark.asyncio
    async def test_delete_nonexistent_profile(self, store: SQLiteProfileStore) -> None:
        """Test deleting a profile that doesn't exist."""
        deleted = await store.delete_profile("nonexistent")
        assert deleted is False


class TestSQLiteSessionStore:
    """Tests for session operations in SQLiteProfileStore."""

    @pytest.mark.asyncio
    async def test_save_and_get_session(self, store: SQLiteProfileStore) -> None:
        """Test saving and retrieving a session."""
        session = SessionSummary(
            session_id="s1",
            user_id="u1",
            summary_text="Test session",
            key_topics=["topic1", "topic2"],
        )
        await store.save_session(session)

        retrieved = await store.get_session("s1")

        assert retrieved is not None
        assert retrieved.session_id == "s1"
        assert retrieved.summary_text == "Test session"
        assert retrieved.key_topics == ["topic1", "topic2"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, store: SQLiteProfileStore) -> None:
        """Test getting a session that doesn't exist."""
        result = await store.get_session("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_session(self, store: SQLiteProfileStore) -> None:
        """Test getting the most recent completed session."""
        # Create sessions with different end times
        s1 = SessionSummary(
            session_id="s1",
            user_id="u1",
            end_time=datetime(2024, 12, 24, 10, 0),
        )
        s2 = SessionSummary(
            session_id="s2",
            user_id="u1",
            end_time=datetime(2024, 12, 24, 12, 0),  # Later
        )
        s3 = SessionSummary(
            session_id="s3",
            user_id="u1",
            end_time=None,  # Not completed
        )
        await store.save_session(s1)
        await store.save_session(s2)
        await store.save_session(s3)

        last = await store.get_last_session("u1")

        assert last is not None
        assert last.session_id == "s2"  # Most recent completed

    @pytest.mark.asyncio
    async def test_get_last_session_none_completed(
        self, store: SQLiteProfileStore
    ) -> None:
        """Test getting last session when none are completed."""
        session = SessionSummary(session_id="s1", user_id="u1", end_time=None)
        await store.save_session(session)

        result = await store.get_last_session("u1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_recent_sessions(self, store: SQLiteProfileStore) -> None:
        """Test getting recent sessions."""
        for i in range(5):
            session = SessionSummary(
                session_id=f"s{i}",
                user_id="u1",
                start_time=datetime(2024, 12, 20 + i, 10, 0),
            )
            await store.save_session(session)

        recent = await store.get_recent_sessions("u1", limit=3)

        assert len(recent) == 3
        assert recent[0].session_id == "s4"  # Most recent first

    @pytest.mark.asyncio
    async def test_delete_session(self, store: SQLiteProfileStore) -> None:
        """Test deleting a session."""
        session = SessionSummary(session_id="to-delete", user_id="u1")
        await store.save_session(session)

        deleted = await store.delete_session("to-delete")
        assert deleted is True

        retrieved = await store.get_session("to-delete")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup_old_sessions(self, store: SQLiteProfileStore) -> None:
        """Test cleaning up old sessions."""
        # Create old and new sessions
        old_session = SessionSummary(
            session_id="old",
            user_id="u1",
            end_time=datetime(2020, 1, 1),  # Very old
        )
        new_session = SessionSummary(
            session_id="new",
            user_id="u1",
            end_time=datetime.now(),  # Recent
        )
        await store.save_session(old_session)
        await store.save_session(new_session)

        # Cleanup sessions older than 30 days
        count = await store.cleanup_old_sessions(30)

        assert count == 1

        # Old session should be gone
        assert await store.get_session("old") is None
        # New session should still exist
        assert await store.get_session("new") is not None
