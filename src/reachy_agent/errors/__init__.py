"""Structured error handling for Reachy Agent.

This module provides consistent error codes and response formats
across the entire agent system.
"""

from reachy_agent.errors.codes import ErrorCode
from reachy_agent.errors.responses import ErrorResponse, ReachyError

__all__ = ["ErrorCode", "ErrorResponse", "ReachyError"]
