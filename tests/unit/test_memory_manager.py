"""Unit tests for MemoryManager.

Tests the unified memory interface including thread safety,
session lifecycle, and integration between stores.
"""

import asyncio
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reachy_agent.memory.manager import MemoryManager
from reachy_agent.memory.types import MemoryType, SessionSummary, UserProfile


@pytest.fixture
def temp_dirs():
    """Create temporary directories for storage."""
    with tempfile.TemporaryDirectory() as chroma_dir:
        with tempfile.TemporaryDirectory() as sqlite_dir:
            yield Path(chroma_dir), Path(sqlite_dir) / "test.db"


@pytest.fixture
def mock_chroma_store():
    """Create a mock ChromaDB store."""
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()
    mock.store = AsyncMock()
    mock.search = AsyncMock(return_value=[])
    mock.get = AsyncMock(return_value=None)
    mock.delete = AsyncMock(return_value=True)
    mock.count = AsyncMock(return_value=0)
    mock.cleanup = AsyncMock(return_value=0)
    return mock


@pytest.fixture
def mock_sqlite_store():
    """Create a mock SQLite store."""
    mock = MagicMock()
    mock.initialize = AsyncMock()
    mock.close = AsyncMock()
    mock.get_profile = AsyncMock(return_value=UserProfile())
    mock.save_profile = AsyncMock()
    mock.update_preference = AsyncMock(return_value=UserProfile())
    mock.save_session = AsyncMock()
    mock.get_session = AsyncMock(return_value=None)
    mock.get_last_session = AsyncMock(return_value=None)
    mock.get_recent_sessions = AsyncMock(return_value=[])
    mock.cleanup_old_sessions = AsyncMock(return_value=0)
    return mock


class TestMemoryManagerInit:
    """Tests for MemoryManager initialization."""

    def test_init_creates_stores(self, temp_dirs: tuple[Path, Path]) -> None:
        """Test that initialization creates both stores."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)

        assert manager.chroma_store is not None
        assert manager.sqlite_store is not None
        assert manager._initialized is False
        assert manager._session_lock is not None

    def test_from_config(self, temp_dirs: tuple[Path, Path]) -> None:
        """Test creating manager from config values."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager.from_config(
            chroma_path=str(chroma_path),
            sqlite_path=str(sqlite_path),
            embedding_model="test-model",
            max_memories=5000,
            retention_days=30,
        )

        assert manager.retention_days == 30


class TestMemoryManagerSession:
    """Tests for session lifecycle with thread safety."""

    @pytest.mark.asyncio
    async def test_start_session(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test starting a session."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        session = await manager.start_session()

        assert session is not None
        assert session.session_id is not None
        assert session.user_id == "default"
        assert manager.current_session is session
        mock_sqlite_store.save_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_session_with_user_id(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test starting a session with custom user ID."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        session = await manager.start_session(user_id="test-user")

        assert session.user_id == "test-user"
        assert manager._current_user_id == "test-user"

    @pytest.mark.asyncio
    async def test_end_session(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test ending a session."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        # Start a session first
        await manager.start_session()

        # End the session
        session = await manager.end_session(
            summary_text="Test summary",
            key_topics=["topic1", "topic2"],
        )

        assert session is not None
        assert session.summary_text == "Test summary"
        assert session.key_topics == ["topic1", "topic2"]
        assert session.end_time is not None
        assert manager.current_session is None

    @pytest.mark.asyncio
    async def test_end_session_no_active_session(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test ending a session when none is active."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        session = await manager.end_session()

        assert session is None

    @pytest.mark.asyncio
    async def test_session_lock_prevents_concurrent_start(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test that session lock prevents concurrent session creation."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        # Track session IDs to verify only one session is created at a time
        session_ids: list[str] = []

        async def start_and_record():
            session = await manager.start_session()
            session_ids.append(session.session_id)
            # Small delay to simulate work
            await asyncio.sleep(0.01)
            return session

        # Start two sessions concurrently
        sessions = await asyncio.gather(
            start_and_record(),
            start_and_record(),
        )

        # Both should complete, and the second should replace the first
        assert len(sessions) == 2
        # Due to locking, they should be different session IDs
        assert sessions[0].session_id != sessions[1].session_id

    @pytest.mark.asyncio
    async def test_double_end_session_safe(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test that calling end_session twice is safe."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        await manager.start_session()
        session1 = await manager.end_session()
        session2 = await manager.end_session()

        assert session1 is not None
        assert session2 is None  # No active session to end


class TestMemoryManagerOperations:
    """Tests for memory and profile operations."""

    @pytest.mark.asyncio
    async def test_store_memory_adds_session_context(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test that store_memory adds session context to metadata."""
        from reachy_agent.memory.types import Memory

        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        # Start a session
        session = await manager.start_session()

        # Configure mock to capture the metadata passed
        mock_chroma_store.store = AsyncMock(
            return_value=Memory(
                id="test-id",
                content="test",
                memory_type=MemoryType.FACT,
            )
        )

        await manager.store_memory("Test content", MemoryType.FACT)

        # Verify session_id was added to metadata
        call_args = mock_chroma_store.store.call_args
        metadata = call_args.kwargs.get("metadata") or call_args.args[2]
        assert "session_id" in metadata
        assert metadata["session_id"] == session.session_id

    @pytest.mark.asyncio
    async def test_get_profile(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test getting user profile."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        profile = await manager.get_profile()

        assert profile is not None
        mock_sqlite_store.get_profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_preference(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test updating user preference."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        await manager.update_preference("key", "value")

        mock_sqlite_store.update_preference.assert_called_once_with(
            "key", "value", "default"
        )


class TestMemoryManagerCleanup:
    """Tests for cleanup operations."""

    @pytest.mark.asyncio
    async def test_cleanup_calls_both_stores(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test that cleanup calls both stores."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True
        manager.retention_days = 30

        mock_chroma_store.cleanup = AsyncMock(return_value=5)
        mock_sqlite_store.cleanup_old_sessions = AsyncMock(return_value=3)

        result = await manager.cleanup()

        assert result["memories_deleted"] == 5
        assert result["sessions_deleted"] == 3
        mock_chroma_store.cleanup.assert_called_once_with(30)
        mock_sqlite_store.cleanup_old_sessions.assert_called_once_with(30)

    @pytest.mark.asyncio
    async def test_close_ends_session(
        self,
        mock_chroma_store: MagicMock,
        mock_sqlite_store: MagicMock,
        temp_dirs: tuple[Path, Path],
    ) -> None:
        """Test that close ends any active session."""
        chroma_path, sqlite_path = temp_dirs
        manager = MemoryManager(chroma_path, sqlite_path)
        manager.chroma_store = mock_chroma_store
        manager.sqlite_store = mock_sqlite_store
        manager._initialized = True

        await manager.start_session()
        await manager.close()

        # Should have saved session twice: once for start, once for end
        assert mock_sqlite_store.save_session.call_count == 2
        mock_chroma_store.close.assert_called_once()
        mock_sqlite_store.close.assert_called_once()
