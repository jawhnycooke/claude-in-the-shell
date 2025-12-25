"""Structured error responses for Reachy Agent.

Provides consistent error response format and exception classes
for use across the agent system.
"""

from dataclasses import dataclass, field
from typing import Any

from reachy_agent.errors.codes import ErrorCode


@dataclass
class ErrorResponse:
    """Structured error response for consistent error handling.

    This class provides a standardized format for error responses
    that can be serialized to JSON for API responses or logging.

    Attributes:
        code: The error code categorizing this error.
        message: Human-readable error message.
        details: Optional additional context about the error.
        tool_name: Optional name of the tool that caused the error.
        retryable: Whether the operation might succeed on retry.
    """

    code: ErrorCode
    message: str
    details: dict[str, Any] | None = None
    tool_name: str | None = None
    retryable: bool = field(init=False)

    def __post_init__(self) -> None:
        """Set retryable flag based on error code."""
        self.retryable = self.code.is_retryable()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary with error information.
        """
        result: dict[str, Any] = {
            "error": True,
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.details:
            result["details"] = self.details
        return result

    @classmethod
    def from_exception(cls, exc: Exception, code: ErrorCode | None = None) -> "ErrorResponse":
        """Create ErrorResponse from an exception.

        Args:
            exc: The exception to convert.
            code: Optional error code override.

        Returns:
            ErrorResponse instance.
        """
        if isinstance(exc, ReachyError):
            return exc.to_response()

        return cls(
            code=code or ErrorCode.INTERNAL_ERROR,
            message=str(exc),
            details={"exception_type": type(exc).__name__},
        )

    @classmethod
    def parameter_error(
        cls,
        param_name: str,
        message: str,
        value: Any = None,
        tool_name: str | None = None,
    ) -> "ErrorResponse":
        """Create a parameter validation error response.

        Args:
            param_name: Name of the invalid parameter.
            message: Description of the validation failure.
            value: The invalid value (if safe to include).
            tool_name: Optional tool name for context.

        Returns:
            ErrorResponse for parameter validation failure.
        """
        details: dict[str, Any] = {"parameter": param_name}
        if value is not None:
            details["provided_value"] = str(value)

        return cls(
            code=ErrorCode.INVALID_PARAMETER,
            message=message,
            details=details,
            tool_name=tool_name,
        )

    @classmethod
    def permission_denied(
        cls,
        tool_name: str,
        reason: str,
        tier: int | None = None,
    ) -> "ErrorResponse":
        """Create a permission denied error response.

        Args:
            tool_name: Name of the tool that was blocked.
            reason: Explanation of why permission was denied.
            tier: The permission tier that blocked the action.

        Returns:
            ErrorResponse for permission denial.
        """
        details: dict[str, Any] = {}
        if tier is not None:
            details["permission_tier"] = tier

        return cls(
            code=ErrorCode.PERMISSION_DENIED,
            message=reason,
            details=details if details else None,
            tool_name=tool_name,
        )

    @classmethod
    def hardware_error(
        cls,
        message: str,
        tool_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> "ErrorResponse":
        """Create a hardware error response.

        Args:
            message: Description of the hardware failure.
            tool_name: Optional tool name for context.
            details: Optional additional error details.

        Returns:
            ErrorResponse for hardware failure.
        """
        return cls(
            code=ErrorCode.HARDWARE_ERROR,
            message=message,
            details=details,
            tool_name=tool_name,
        )


class ReachyError(Exception):
    """Base exception class for Reachy Agent errors.

    All Reachy-specific exceptions should inherit from this class
    to enable consistent error handling and conversion to ErrorResponse.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Initialize ReachyError.

        Args:
            code: The error code categorizing this error.
            message: Human-readable error message.
            details: Optional additional context about the error.
            tool_name: Optional name of the tool that caused the error.
        """
        super().__init__(message)
        self.code = code
        self.details = details
        self.tool_name = tool_name

    def to_response(self) -> ErrorResponse:
        """Convert to ErrorResponse.

        Returns:
            ErrorResponse representation of this exception.
        """
        return ErrorResponse(
            code=self.code,
            message=str(self),
            details=self.details,
            tool_name=self.tool_name,
        )


class ParameterError(ReachyError):
    """Exception for parameter validation failures."""

    def __init__(
        self,
        param_name: str,
        message: str,
        value: Any = None,
        tool_name: str | None = None,
    ) -> None:
        """Initialize ParameterError.

        Args:
            param_name: Name of the invalid parameter.
            message: Description of the validation failure.
            value: The invalid value (if safe to include).
            tool_name: Optional tool name for context.
        """
        details: dict[str, Any] = {"parameter": param_name}
        if value is not None:
            details["provided_value"] = str(value)

        super().__init__(
            code=ErrorCode.INVALID_PARAMETER,
            message=message,
            details=details,
            tool_name=tool_name,
        )


class HardwareError(ReachyError):
    """Exception for hardware/daemon communication failures."""

    def __init__(
        self,
        message: str,
        tool_name: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize HardwareError.

        Args:
            message: Description of the hardware failure.
            tool_name: Optional tool name for context.
            details: Optional additional error details.
        """
        super().__init__(
            code=ErrorCode.HARDWARE_ERROR,
            message=message,
            details=details,
            tool_name=tool_name,
        )


class PermissionError(ReachyError):
    """Exception for permission-related failures."""

    def __init__(
        self,
        tool_name: str,
        reason: str,
        code: ErrorCode = ErrorCode.PERMISSION_DENIED,
        tier: int | None = None,
    ) -> None:
        """Initialize PermissionError.

        Args:
            tool_name: Name of the tool that was blocked.
            reason: Explanation of why permission was denied.
            code: Specific permission error code.
            tier: The permission tier that blocked the action.
        """
        details: dict[str, Any] = {}
        if tier is not None:
            details["permission_tier"] = tier

        super().__init__(
            code=code,
            message=reason,
            details=details if details else None,
            tool_name=tool_name,
        )


class TimeoutError(ReachyError):
    """Exception for operation timeouts."""

    def __init__(
        self,
        message: str,
        timeout_seconds: float | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Initialize TimeoutError.

        Args:
            message: Description of what timed out.
            timeout_seconds: The timeout duration that was exceeded.
            tool_name: Optional tool name for context.
        """
        details: dict[str, Any] = {}
        if timeout_seconds is not None:
            details["timeout_seconds"] = timeout_seconds

        super().__init__(
            code=ErrorCode.TIMEOUT,
            message=message,
            details=details if details else None,
            tool_name=tool_name,
        )
