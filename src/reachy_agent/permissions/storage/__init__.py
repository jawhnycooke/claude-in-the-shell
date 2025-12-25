"""Audit storage backends for permission system.

This module provides persistent storage for tool execution audit logs.
"""

from reachy_agent.permissions.storage.sqlite_audit import SQLiteAuditStorage

__all__ = ["SQLiteAuditStorage"]
