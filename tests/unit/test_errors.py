"""Tests for the error system module."""

import pytest

from reachy_agent.errors import ErrorCode, ErrorResponse, ReachyError
from reachy_agent.errors.responses import HardwareError, ParameterError, PermissionError


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_code_values(self) -> None:
        """Test that error codes have expected values."""
        assert ErrorCode.INVALID_PARAMETER.value == "INVALID_PARAMETER"
        assert ErrorCode.HARDWARE_ERROR.value == "HARDWARE_ERROR"
        assert ErrorCode.PERMISSION_DENIED.value == "PERMISSION_DENIED"

    def test_is_retryable(self) -> None:
        """Test retryable error classification."""
        # Retryable errors
        assert ErrorCode.TIMEOUT.is_retryable()
        assert ErrorCode.HARDWARE_BUSY.is_retryable()
        assert ErrorCode.IN_PROGRESS.is_retryable()
        assert ErrorCode.DAEMON_UNAVAILABLE.is_retryable()
        assert ErrorCode.SERVICE_UNAVAILABLE.is_retryable()

        # Non-retryable errors
        assert not ErrorCode.INVALID_PARAMETER.is_retryable()
        assert not ErrorCode.PERMISSION_DENIED.is_retryable()

    def test_is_user_error(self) -> None:
        """Test user error classification."""
        assert ErrorCode.INVALID_PARAMETER.is_user_error()
        assert ErrorCode.MISSING_PARAMETER.is_user_error()
        assert ErrorCode.OUT_OF_RANGE.is_user_error()
        assert not ErrorCode.HARDWARE_ERROR.is_user_error()
        assert not ErrorCode.INTERNAL_ERROR.is_user_error()

    def test_is_permission_error(self) -> None:
        """Test permission error classification."""
        assert ErrorCode.PERMISSION_DENIED.is_permission_error()
        assert ErrorCode.CONFIRMATION_TIMEOUT.is_permission_error()
        assert ErrorCode.CONFIRMATION_DENIED.is_permission_error()
        assert not ErrorCode.TIMEOUT.is_permission_error()


class TestErrorResponse:
    """Tests for ErrorResponse dataclass."""

    def test_create_error_response(self) -> None:
        """Test basic error response creation."""
        error = ErrorResponse(
            code=ErrorCode.TIMEOUT,
            message="Operation timed out",
        )

        assert error.code == ErrorCode.TIMEOUT
        assert error.message == "Operation timed out"
        assert error.retryable is True  # TIMEOUT is retryable
        assert error.details is None

    def test_to_dict(self) -> None:
        """Test serialization to dictionary."""
        error = ErrorResponse(
            code=ErrorCode.INVALID_PARAMETER,
            message="Missing required field",
            details={"field": "name"},
        )

        data = error.to_dict()

        assert data["error"] is True
        assert data["code"] == "INVALID_PARAMETER"
        assert data["message"] == "Missing required field"
        assert data["retryable"] is False
        assert data["details"] == {"field": "name"}

    def test_factory_methods(self) -> None:
        """Test factory method creation."""
        # Parameter error (requires param_name and message)
        param_error = ErrorResponse.parameter_error(
            param_name="speed",
            message="Invalid speed value",
        )
        assert param_error.code == ErrorCode.INVALID_PARAMETER
        assert "Invalid speed value" in param_error.message
        assert param_error.details is not None
        assert param_error.details["parameter"] == "speed"

        # Permission denied (requires tool_name and reason)
        perm_error = ErrorResponse.permission_denied(
            tool_name="mcp__calendar__create_event",
            reason="Action blocked by permission tier",
        )
        assert perm_error.code == ErrorCode.PERMISSION_DENIED
        assert perm_error.tool_name == "mcp__calendar__create_event"

        # Hardware error
        hw_error = ErrorResponse.hardware_error("Motor overheated")
        assert hw_error.code == ErrorCode.HARDWARE_ERROR
        assert "Motor overheated" in hw_error.message


class TestExceptionClasses:
    """Tests for exception classes."""

    def test_reachy_error(self) -> None:
        """Test ReachyError exception."""
        error = ReachyError(
            code=ErrorCode.INTERNAL_ERROR,
            message="Something went wrong",
        )

        # ReachyError uses parent Exception.__str__ which returns the message
        assert str(error) == "Something went wrong"
        assert error.code == ErrorCode.INTERNAL_ERROR

        # Test to_response conversion
        response = error.to_response()
        assert isinstance(response, ErrorResponse)
        assert response.code == ErrorCode.INTERNAL_ERROR

    def test_parameter_error(self) -> None:
        """Test ParameterError exception."""
        error = ParameterError(
            param_name="direction",
            message="Invalid direction value",
        )

        assert error.code == ErrorCode.INVALID_PARAMETER
        assert "Invalid direction value" in str(error)
        assert error.details is not None
        assert error.details["parameter"] == "direction"

    def test_parameter_error_with_value(self) -> None:
        """Test ParameterError exception with value."""
        error = ParameterError(
            param_name="speed",
            message="Speed must be between 0 and 100",
            value=150,
        )

        assert error.details is not None
        assert error.details["parameter"] == "speed"
        assert error.details["provided_value"] == "150"

    def test_hardware_error(self) -> None:
        """Test HardwareError exception."""
        error = HardwareError(message="Motor not responding")

        assert error.code == ErrorCode.HARDWARE_ERROR
        assert "Motor not responding" in str(error)

    def test_permission_error(self) -> None:
        """Test PermissionError exception."""
        error = PermissionError(
            tool_name="mcp__reachy__speak",
            reason="Action denied by user",
        )

        assert error.code == ErrorCode.PERMISSION_DENIED
        assert "Action denied by user" in str(error)
        assert error.tool_name == "mcp__reachy__speak"

    def test_permission_error_with_tier(self) -> None:
        """Test PermissionError exception with tier."""
        error = PermissionError(
            tool_name="mcp__reachy__dance",
            reason="Tier 4 actions are forbidden",
            tier=4,
        )

        assert error.details is not None
        assert error.details["permission_tier"] == 4
