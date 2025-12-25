"""Permission UI handlers for Reachy Agent.

This module provides pluggable handlers for permission confirmation
and notification in both CLI and Web interfaces.
"""

from reachy_agent.permissions.handlers.base import PermissionHandler
from reachy_agent.permissions.handlers.cli_handler import CLIPermissionHandler
from reachy_agent.permissions.handlers.web_handler import WebSocketPermissionHandler

__all__ = [
    "PermissionHandler",
    "CLIPermissionHandler",
    "WebSocketPermissionHandler",
]
