"""Structured error codes for Reachy Agent.

These error codes provide consistent categorization of errors
across MCP tools, permission system, and agent loop.
"""

from enum import Enum


class ErrorCode(str, Enum):
    """Structured error codes for Reachy Agent.

    Error codes are grouped by category:
    - INVALID_* / MISSING_* / OUT_OF_*: Parameter validation errors
    - HARDWARE_*: Physical robot/daemon communication errors
    - TIMEOUT / CANCELLED / IN_PROGRESS: Operation lifecycle errors
    - PERMISSION_* / CONFIRMATION_*: Permission system errors
    - INTERNAL_* / SERVICE_*: System-level errors
    """

    # Parameter validation errors
    INVALID_PARAMETER = "INVALID_PARAMETER"
    """A parameter value is invalid (wrong type, format, or value)."""

    MISSING_PARAMETER = "MISSING_PARAMETER"
    """A required parameter was not provided."""

    OUT_OF_RANGE = "OUT_OF_RANGE"
    """A numeric parameter is outside allowed bounds."""

    INVALID_TOOL = "INVALID_TOOL"
    """The requested tool does not exist."""

    # Hardware/daemon errors
    HARDWARE_ERROR = "HARDWARE_ERROR"
    """General hardware communication failure."""

    HARDWARE_BUSY = "HARDWARE_BUSY"
    """Hardware is currently executing another operation."""

    NOT_READY = "NOT_READY"
    """Robot not initialized (motors not awake)."""

    DAEMON_UNAVAILABLE = "DAEMON_UNAVAILABLE"
    """Cannot connect to the Reachy daemon."""

    DAEMON_ERROR = "DAEMON_ERROR"
    """Daemon returned an error response."""

    # Operation lifecycle errors
    TIMEOUT = "TIMEOUT"
    """Operation timed out before completion."""

    CANCELLED = "CANCELLED"
    """Operation was cancelled by user or system."""

    IN_PROGRESS = "IN_PROGRESS"
    """Cannot start operation; another is already running."""

    # Permission errors
    PERMISSION_DENIED = "PERMISSION_DENIED"
    """Action blocked by permission tier (Tier 4 Forbidden)."""

    CONFIRMATION_TIMEOUT = "CONFIRMATION_TIMEOUT"
    """User did not respond to confirmation prompt in time."""

    CONFIRMATION_DENIED = "CONFIRMATION_DENIED"
    """User explicitly denied the confirmation request."""

    # System errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    """Unexpected internal error (bug or system issue)."""

    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    """Required external service is unavailable."""

    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    """Invalid or missing configuration."""

    def is_retryable(self) -> bool:
        """Check if this error type is potentially retryable.

        Returns:
            True if the error might succeed on retry.
        """
        return self in {
            ErrorCode.HARDWARE_BUSY,
            ErrorCode.IN_PROGRESS,
            ErrorCode.TIMEOUT,
            ErrorCode.DAEMON_UNAVAILABLE,
            ErrorCode.SERVICE_UNAVAILABLE,
        }

    def is_user_error(self) -> bool:
        """Check if this error was caused by user input.

        Returns:
            True if the error is due to invalid user input.
        """
        return self in {
            ErrorCode.INVALID_PARAMETER,
            ErrorCode.MISSING_PARAMETER,
            ErrorCode.OUT_OF_RANGE,
            ErrorCode.INVALID_TOOL,
        }

    def is_permission_error(self) -> bool:
        """Check if this error is permission-related.

        Returns:
            True if the error is due to permission denial.
        """
        return self in {
            ErrorCode.PERMISSION_DENIED,
            ErrorCode.CONFIRMATION_TIMEOUT,
            ErrorCode.CONFIRMATION_DENIED,
        }
