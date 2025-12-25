"""SQLite storage for user profiles and session summaries.

Provides structured storage for:
- User profiles (name, preferences, connected services)
- Session summaries (for continuity across conversations)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from reachy_agent.memory.types import SessionSummary, UserProfile

logger = logging.getLogger(__name__)

# SQL schema for tables
SCHEMA = """
-- User profiles table
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    preferences TEXT DEFAULT '{}',
    schedule_patterns TEXT DEFAULT '',
    connected_services TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Session summaries table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT,
    summary_text TEXT DEFAULT '',
    key_topics TEXT DEFAULT '[]',
    memory_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id)
);

-- Index for faster session lookups by user and time
CREATE INDEX IF NOT EXISTS idx_sessions_user_time
ON sessions(user_id, end_time DESC);
"""


class SQLiteProfileStore:
    """SQLite-backed storage for user profiles and sessions.

    Provides CRUD operations for user profiles and session summaries.
    Data is stored in a local SQLite database for persistence.

    Args:
        path: Path to the SQLite database file.

    Example:
        >>> store = SQLiteProfileStore("~/.reachy/memory/reachy.db")
        >>> await store.initialize()
        >>> profile = await store.get_profile("default")
        >>> profile.name = "John"
        >>> await store.save_profile(profile)
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._initialized = False

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        """Get a database connection with proper cleanup."""
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    async def initialize(self) -> None:
        """Initialize the database schema.

        Creates the database file and tables if they don't exist.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing SQLite database at {self.path}")
        with self._get_connection() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

        self._initialized = True
        logger.info("SQLite profile store ready")

    # ─────────────────────────────────────────────────────────────────
    # User Profile Operations
    # ─────────────────────────────────────────────────────────────────

    async def get_profile(self, user_id: str = "default") -> UserProfile:
        """Get a user profile, creating default if not exists.

        Args:
            user_id: The user identifier.

        Returns:
            The UserProfile for the given user.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            row = cursor.fetchone()

            if row is None:
                # Create default profile
                profile = UserProfile(user_id=user_id)
                await self.save_profile(profile)
                return profile

            return UserProfile.from_db_dict(dict(row))

    async def save_profile(self, profile: UserProfile) -> None:
        """Save or update a user profile.

        Args:
            profile: The UserProfile to save.
        """
        profile.updated_at = datetime.now()
        data = profile.to_db_dict()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles
                    (user_id, name, preferences, schedule_patterns,
                     connected_services, created_at, updated_at)
                VALUES
                    (:user_id, :name, :preferences, :schedule_patterns,
                     :connected_services, :created_at, :updated_at)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    preferences = excluded.preferences,
                    schedule_patterns = excluded.schedule_patterns,
                    connected_services = excluded.connected_services,
                    updated_at = excluded.updated_at
                """,
                data,
            )
            conn.commit()

        logger.debug(f"Saved profile for user {profile.user_id}")

    async def update_preference(
        self,
        key: str,
        value: str,
        user_id: str = "default",
    ) -> UserProfile:
        """Update a single preference for a user.

        Args:
            key: The preference key.
            value: The preference value.
            user_id: The user identifier.

        Returns:
            The updated UserProfile.
        """
        profile = await self.get_profile(user_id)
        profile.set_preference(key, value)
        await self.save_profile(profile)
        return profile

    async def delete_profile(self, user_id: str) -> bool:
        """Delete a user profile.

        Args:
            user_id: The user identifier.

        Returns:
            True if deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM user_profiles WHERE user_id = ?",
                (user_id,),
            )
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.debug(f"Deleted profile for user {user_id}")
        return deleted

    # ─────────────────────────────────────────────────────────────────
    # Session Operations
    # ─────────────────────────────────────────────────────────────────

    async def save_session(self, session: SessionSummary) -> None:
        """Save or update a session summary.

        Args:
            session: The SessionSummary to save.
        """
        data = session.to_db_dict()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions
                    (session_id, user_id, start_time, end_time,
                     summary_text, key_topics, memory_count)
                VALUES
                    (:session_id, :user_id, :start_time, :end_time,
                     :summary_text, :key_topics, :memory_count)
                ON CONFLICT(session_id) DO UPDATE SET
                    end_time = excluded.end_time,
                    summary_text = excluded.summary_text,
                    key_topics = excluded.key_topics,
                    memory_count = excluded.memory_count
                """,
                data,
            )
            conn.commit()

        logger.debug(f"Saved session {session.session_id}")

    async def get_session(self, session_id: str) -> SessionSummary | None:
        """Get a specific session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The SessionSummary if found, None otherwise.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return SessionSummary.from_db_dict(dict(row))

    async def get_last_session(self, user_id: str = "default") -> SessionSummary | None:
        """Get the most recent completed session for a user.

        Args:
            user_id: The user identifier.

        Returns:
            The most recent SessionSummary with an end_time, or None.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ? AND end_time IS NOT NULL
                ORDER BY end_time DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            return SessionSummary.from_db_dict(dict(row))

    async def get_recent_sessions(
        self,
        user_id: str = "default",
        limit: int = 10,
    ) -> list[SessionSummary]:
        """Get recent sessions for a user.

        Args:
            user_id: The user identifier.
            limit: Maximum number of sessions to return.

        Returns:
            List of SessionSummary objects, most recent first.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM sessions
                WHERE user_id = ?
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = cursor.fetchall()

            return [SessionSummary.from_db_dict(dict(row)) for row in rows]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: The session identifier.

        Returns:
            True if deleted, False if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.debug(f"Deleted session {session_id}")
        return deleted

    async def cleanup_old_sessions(self, retention_days: int) -> int:
        """Delete sessions older than retention period.

        Args:
            retention_days: Number of days to retain sessions.

        Returns:
            Number of sessions deleted.
        """
        from datetime import timedelta

        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE end_time < ?",
                (cutoff,),
            )
            conn.commit()
            count = cursor.rowcount

        if count > 0:
            logger.info(f"Cleaned up {count} sessions older than {retention_days} days")
        return count

    async def close(self) -> None:
        """Close the store.

        SQLite connections are managed per-operation via context manager,
        so this method primarily updates state for consistency with other stores.
        """
        if not self._initialized:
            logger.debug("SQLite profile store already closed")
            return

        self._initialized = False
        logger.info("SQLite profile store closed")
