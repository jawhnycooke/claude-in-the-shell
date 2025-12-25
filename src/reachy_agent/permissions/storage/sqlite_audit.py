"""SQLite-based audit log storage for permission system.

Provides persistent storage of tool execution records with automatic
retention cleanup and query capabilities.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class AuditRecord:
    """A single tool execution audit record.

    Attributes:
        id: Unique identifier for this execution.
        timestamp: When the execution started.
        tool_name: Name of the executed tool.
        tool_input: Input parameters to the tool.
        permission_tier: The permission tier that applied.
        decision: The permission decision (allowed, denied, confirmed, etc.).
        result: The execution result (if completed).
        duration_ms: Execution duration in milliseconds.
        error_code: Error code if execution failed.
    """

    id: str
    timestamp: datetime
    tool_name: str
    tool_input: dict[str, Any]
    permission_tier: int
    decision: str
    result: str | None = None
    duration_ms: int | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "permission_tier": self.permission_tier,
            "decision": self.decision,
            "result": self.result,
            "duration_ms": self.duration_ms,
            "error_code": self.error_code,
        }

    @classmethod
    def from_row(cls, row: tuple) -> AuditRecord:
        """Create AuditRecord from database row."""
        return cls(
            id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            tool_name=row[2],
            tool_input=json.loads(row[3]) if row[3] else {},
            permission_tier=row[4],
            decision=row[5],
            result=row[6],
            duration_ms=row[7],
            error_code=row[8],
        )


class SQLiteAuditStorage:
    """SQLite-based audit log storage.

    Stores tool execution records in a local SQLite database for
    compliance, debugging, and analytics purposes.

    The storage automatically manages retention by deleting records
    older than the configured retention period.

    Example:
        ```python
        storage = SQLiteAuditStorage()

        # Store a record
        await storage.store(AuditRecord(
            id=str(uuid4()),
            timestamp=datetime.now(),
            tool_name="mcp__reachy__move_head",
            tool_input={"direction": "left"},
            permission_tier=1,
            decision="allowed",
        ))

        # Query recent records
        records = await storage.get_recent(limit=10)

        # Clean up old records
        deleted = await storage.cleanup_old(days=7)
        ```

    Attributes:
        db_path: Path to the SQLite database file.
        retention_days: Number of days to retain records.
    """

    DEFAULT_DB_PATH = "~/.reachy/audit.db"
    DEFAULT_RETENTION_DAYS = 7

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        """Initialize SQLite audit storage.

        Args:
            db_path: Path to the SQLite database file.
            retention_days: Number of days to retain records.
        """
        self.db_path = Path(db_path).expanduser()
        self.retention_days = retention_days
        self._initialized = False
        self._lock = asyncio.Lock()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection (creates DB if needed)."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema if needed."""
        if self._initialized:
            return

        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tool_executions (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_input TEXT,
                    permission_tier INTEGER NOT NULL,
                    decision TEXT NOT NULL,
                    result TEXT,
                    duration_ms INTEGER,
                    error_code TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON tool_executions(timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tool_name
                ON tool_executions(tool_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decision
                ON tool_executions(decision)
            """)

            conn.commit()

        self._initialized = True
        log.debug("Audit database initialized", db_path=str(self.db_path))

    async def store(self, record: AuditRecord) -> None:
        """Store an audit record.

        Args:
            record: The audit record to store.
        """
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(
                None, self._store_sync, record
            )

    def _store_sync(self, record: AuditRecord) -> None:
        """Synchronous store operation."""
        self._init_db()

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tool_executions
                (id, timestamp, tool_name, tool_input, permission_tier,
                 decision, result, duration_ms, error_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.timestamp.isoformat(),
                    record.tool_name,
                    json.dumps(record.tool_input),
                    record.permission_tier,
                    record.decision,
                    record.result,
                    record.duration_ms,
                    record.error_code,
                ),
            )
            conn.commit()

        log.debug(
            "Stored audit record",
            record_id=record.id,
            tool_name=record.tool_name,
            decision=record.decision,
        )

    async def update(
        self,
        record_id: str,
        result: str | None = None,
        duration_ms: int | None = None,
        error_code: str | None = None,
    ) -> None:
        """Update an existing audit record with results.

        Args:
            record_id: ID of the record to update.
            result: The execution result.
            duration_ms: Execution duration in milliseconds.
            error_code: Error code if execution failed.
        """
        async with self._lock:
            await asyncio.get_event_loop().run_in_executor(
                None, self._update_sync, record_id, result, duration_ms, error_code
            )

    def _update_sync(
        self,
        record_id: str,
        result: str | None,
        duration_ms: int | None,
        error_code: str | None,
    ) -> None:
        """Synchronous update operation."""
        self._init_db()

        updates = []
        values = []

        if result is not None:
            updates.append("result = ?")
            values.append(result)
        if duration_ms is not None:
            updates.append("duration_ms = ?")
            values.append(duration_ms)
        if error_code is not None:
            updates.append("error_code = ?")
            values.append(error_code)

        if not updates:
            return

        values.append(record_id)

        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE tool_executions SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            conn.commit()

    async def get_recent(
        self,
        limit: int = 100,
        tool_name: str | None = None,
        decision: str | None = None,
    ) -> list[AuditRecord]:
        """Get recent audit records.

        Args:
            limit: Maximum number of records to return.
            tool_name: Optional filter by tool name.
            decision: Optional filter by decision.

        Returns:
            List of audit records, most recent first.
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_recent_sync, limit, tool_name, decision
        )

    def _get_recent_sync(
        self,
        limit: int,
        tool_name: str | None,
        decision: str | None,
    ) -> list[AuditRecord]:
        """Synchronous get_recent operation."""
        self._init_db()

        query = "SELECT id, timestamp, tool_name, tool_input, permission_tier, decision, result, duration_ms, error_code FROM tool_executions"
        conditions = []
        values: list[Any] = []

        if tool_name:
            conditions.append("tool_name = ?")
            values.append(tool_name)
        if decision:
            conditions.append("decision = ?")
            values.append(decision)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        values.append(limit)

        with self._get_connection() as conn:
            cursor = conn.execute(query, values)
            rows = cursor.fetchall()

        return [AuditRecord.from_row(tuple(row)) for row in rows]

    async def get_by_id(self, record_id: str) -> AuditRecord | None:
        """Get a specific audit record by ID.

        Args:
            record_id: The record ID to retrieve.

        Returns:
            The audit record, or None if not found.
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_by_id_sync, record_id
        )

    def _get_by_id_sync(self, record_id: str) -> AuditRecord | None:
        """Synchronous get_by_id operation."""
        self._init_db()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, timestamp, tool_name, tool_input, permission_tier, decision, result, duration_ms, error_code FROM tool_executions WHERE id = ?",
                (record_id,),
            )
            row = cursor.fetchone()

        if row:
            return AuditRecord.from_row(tuple(row))
        return None

    async def cleanup_old(self, days: int | None = None) -> int:
        """Delete records older than specified days.

        Args:
            days: Number of days to retain. Uses default if not specified.

        Returns:
            Number of records deleted.
        """
        retention = days if days is not None else self.retention_days
        return await asyncio.get_event_loop().run_in_executor(
            None, self._cleanup_old_sync, retention
        )

    def _cleanup_old_sync(self, days: int) -> int:
        """Synchronous cleanup operation."""
        self._init_db()

        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM tool_executions WHERE timestamp < ?",
                (cutoff_str,),
            )
            deleted = cursor.rowcount
            conn.commit()

        if deleted > 0:
            log.info("Cleaned up old audit records", deleted=deleted, days=days)

        return deleted

    async def get_stats(self) -> dict[str, Any]:
        """Get statistics about stored audit records.

        Returns:
            Dictionary with record counts and date range.
        """
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_stats_sync
        )

    def _get_stats_sync(self) -> dict[str, Any]:
        """Synchronous get_stats operation."""
        self._init_db()

        with self._get_connection() as conn:
            # Total count
            cursor = conn.execute("SELECT COUNT(*) FROM tool_executions")
            total = cursor.fetchone()[0]

            # Count by decision
            cursor = conn.execute(
                "SELECT decision, COUNT(*) FROM tool_executions GROUP BY decision"
            )
            by_decision = dict(cursor.fetchall())

            # Date range
            cursor = conn.execute(
                "SELECT MIN(timestamp), MAX(timestamp) FROM tool_executions"
            )
            row = cursor.fetchone()
            oldest = row[0]
            newest = row[1]

        return {
            "total_records": total,
            "by_decision": by_decision,
            "oldest_record": oldest,
            "newest_record": newest,
            "db_path": str(self.db_path),
        }

    async def close(self) -> None:
        """Close any open connections (no-op for SQLite, but good interface)."""
        pass


# Factory function for creating storage with ToolExecution compatibility
def create_audit_callback(
    storage: SQLiteAuditStorage,
) -> "Callable[[Any], Awaitable[None]]":
    """Create an audit callback function compatible with PermissionHooks.

    This adapter converts ToolExecution objects from the permission system
    to AuditRecord objects for storage.

    Args:
        storage: The SQLiteAuditStorage instance to use.

    Returns:
        An async callback function for use with PermissionHooks.
    """
    from typing import Awaitable, Callable

    async def audit_callback(execution: Any) -> None:
        """Store a ToolExecution as an AuditRecord."""
        record = AuditRecord(
            id=execution.id,
            timestamp=execution.timestamp,
            tool_name=execution.tool_name,
            tool_input=execution.tool_input,
            permission_tier=execution.permission_tier,
            decision=execution.decision,
            result=execution.result,
            duration_ms=execution.duration_ms,
        )
        await storage.store(record)

    return audit_callback
