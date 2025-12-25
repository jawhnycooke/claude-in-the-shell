"""Abstract base class for permission UI handlers.

Provides the interface that CLI and Web handlers must implement
for permission confirmation and notification.
"""

from abc import ABC, abstractmethod
from typing import Any


class PermissionHandler(ABC):
    """Abstract base for permission UI handlers.

    This interface allows the permission system to request user
    confirmation and display notifications through different UIs
    (CLI, Web, etc.) without coupling to a specific implementation.

    Subclasses must implement:
    - request_confirmation: Ask user to approve an action
    - notify: Inform user about an executed action
    - display_error: Show error message to user

    Example:
        ```python
        class MyHandler(PermissionHandler):
            async def request_confirmation(
                self, tool_name, reason, tool_input, timeout
            ) -> bool:
                # Show confirmation UI
                return user_approved

            async def notify(self, tool_name, message, tier) -> None:
                # Show notification
                pass

            async def display_error(self, tool_name, error, code) -> None:
                # Show error
                pass
        ```
    """

    @abstractmethod
    async def request_confirmation(
        self,
        tool_name: str,
        reason: str,
        tool_input: dict[str, Any],
        timeout_seconds: float = 60.0,
    ) -> bool:
        """Request user confirmation for a tool execution.

        Called when a tool requires Tier 3 (Confirm) permission.
        The handler should display the request and wait for user response.

        Args:
            tool_name: Name of the tool requiring confirmation.
            reason: Human-readable explanation of why confirmation is needed.
            tool_input: The tool's input parameters for user review.
            timeout_seconds: Maximum time to wait for response.

        Returns:
            True if user approved the action, False if denied or timeout.

        Note:
            Implementations should handle timeout gracefully and return
            False if the user doesn't respond in time.
        """
        pass

    @abstractmethod
    async def notify(
        self,
        tool_name: str,
        message: str,
        tier: int = 2,
    ) -> None:
        """Notify user about a tool execution.

        Called when a tool with Tier 2 (Notify) permission is executed.
        This is informational only - the action has already been taken.

        Args:
            tool_name: Name of the tool that was executed.
            message: Human-readable notification message.
            tier: Permission tier for context (default 2).
        """
        pass

    @abstractmethod
    async def display_error(
        self,
        tool_name: str,
        error: str,
        code: str | None = None,
    ) -> None:
        """Display an error message to the user.

        Called when a tool execution fails or permission is denied.

        Args:
            tool_name: Name of the tool that caused the error.
            error: Human-readable error message.
            code: Optional error code for categorization.
        """
        pass

    async def on_tool_start(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """Called when a tool starts executing.

        Optional hook for handlers to show loading/progress indicators.
        Default implementation does nothing.

        Args:
            tool_name: Name of the tool being executed.
            tool_input: The tool's input parameters.
        """
        pass

    async def on_tool_complete(
        self,
        tool_name: str,
        result: Any,
        duration_ms: int,
    ) -> None:
        """Called when a tool completes successfully.

        Optional hook for handlers to update UI with results.
        Default implementation does nothing.

        Args:
            tool_name: Name of the completed tool.
            result: The tool's return value.
            duration_ms: Execution time in milliseconds.
        """
        pass
