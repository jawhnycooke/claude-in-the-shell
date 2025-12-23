"""Permission hooks for Claude Agent SDK.

Implements PreToolUse and PostToolUse hooks to enforce the permission
tier system defined in TECH_REQ.md.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Awaitable
from uuid import uuid4

from reachy_agent.permissions.tiers import (
    PermissionDecision,
    PermissionEvaluator,
    PermissionTier,
)
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.permissions.tiers import PermissionConfig

log = get_logger(__name__)


@dataclass
class ToolExecution:
    """Audit log entry for a tool execution.

    Matches the ToolExecution schema in TECH_REQ.md.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    permission_tier: int = 0
    decision: str = ""  # allowed, notified, confirmed, denied
    result: str = ""  # success, error, timeout
    duration_ms: int = 0


class ConfirmationTimeoutError(Exception):
    """Raised when confirmation times out."""

    pass


class PermissionDeniedError(Exception):
    """Raised when a tool execution is denied."""

    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__(f"Permission denied for {tool_name}: {reason}")
        self.tool_name = tool_name
        self.reason = reason


# Type for confirmation callback
ConfirmationCallback = Callable[[str, str, dict[str, Any]], Awaitable[bool]]


class PermissionHooks:
    """Permission enforcement hooks for Claude Agent SDK.

    Provides PreToolUse and PostToolUse hook implementations that
    enforce the permission tier system.
    """

    def __init__(
        self,
        evaluator: PermissionEvaluator | None = None,
        confirmation_callback: ConfirmationCallback | None = None,
        notification_callback: Callable[[str, str], Awaitable[None]] | None = None,
        audit_callback: Callable[[ToolExecution], Awaitable[None]] | None = None,
    ) -> None:
        """Initialize permission hooks.

        Args:
            evaluator: Permission evaluator. Uses default if None.
            confirmation_callback: Async function to request user confirmation.
                Receives (tool_name, reason, tool_input) and returns bool.
            notification_callback: Async function to notify user.
                Receives (tool_name, message).
            audit_callback: Async function to log tool executions.
                Receives ToolExecution record.
        """
        self.evaluator = evaluator or PermissionEvaluator()
        self._confirmation_callback = confirmation_callback
        self._notification_callback = notification_callback
        self._audit_callback = audit_callback
        self._pending_executions: dict[str, ToolExecution] = {}

    async def pre_tool_use(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Pre-tool-use hook for permission enforcement.

        Called before each tool execution. Returns None to allow
        execution, or a dict with an error message to block it.

        Args:
            tool_name: Name of the tool being called.
            tool_input: Input parameters for the tool.

        Returns:
            None to allow execution, or error dict to block.

        Raises:
            PermissionDeniedError: If the tool is forbidden.
            ConfirmationTimeoutError: If confirmation times out.
        """
        # Evaluate permissions
        decision = self.evaluator.evaluate(tool_name)

        log.info(
            "Permission check",
            tool_name=tool_name,
            tier=decision.tier.name,
            allowed=decision.allowed,
            reason=decision.reason,
        )

        # Create audit record
        execution = ToolExecution(
            tool_name=tool_name,
            tool_input=tool_input,
            permission_tier=decision.tier.value,
        )
        self._pending_executions[execution.id] = execution

        # Handle based on tier
        if decision.tier == PermissionTier.FORBIDDEN:
            execution.decision = "denied"
            execution.result = "error"
            await self._log_execution(execution)

            log.warning(
                "Tool execution denied",
                tool_name=tool_name,
                reason=decision.reason,
            )

            return {
                "error": f"This action is not allowed: {decision.reason}",
                "tier": "forbidden",
            }

        if decision.needs_confirmation:
            # Tier 3: Requires confirmation
            confirmed = await self._request_confirmation(
                tool_name, decision.reason, tool_input
            )

            if not confirmed:
                execution.decision = "denied"
                execution.result = "error"
                await self._log_execution(execution)

                log.info("User denied confirmation", tool_name=tool_name)
                return {
                    "error": "User declined to confirm this action",
                    "tier": "confirm",
                }

            execution.decision = "confirmed"

        elif decision.should_notify:
            # Tier 2: Notify user
            await self._notify_user(
                tool_name,
                f"Executing {tool_name}: {decision.reason}",
            )
            execution.decision = "notified"

        else:
            # Tier 1: Autonomous
            execution.decision = "allowed"

        # Store execution ID for post-hook correlation
        return {"_execution_id": execution.id}

    async def post_tool_use(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_result: Any,
        execution_id: str | None = None,
        error: Exception | None = None,
    ) -> None:
        """Post-tool-use hook for audit logging.

        Called after each tool execution completes.

        Args:
            tool_name: Name of the tool that was called.
            tool_input: Input parameters that were used.
            tool_result: Result from the tool execution.
            execution_id: ID from pre-hook for correlation.
            error: Exception if the tool failed.
        """
        # Find the execution record
        execution = None
        if execution_id and execution_id in self._pending_executions:
            execution = self._pending_executions.pop(execution_id)
        else:
            # Create a new record if we don't have one
            execution = ToolExecution(
                tool_name=tool_name,
                tool_input=tool_input,
                permission_tier=0,
                decision="unknown",
            )

        # Update with result
        if error:
            execution.result = "error"
        else:
            execution.result = "success"

        # Calculate duration (approximate)
        execution.duration_ms = int(
            (datetime.now() - execution.timestamp).total_seconds() * 1000
        )

        # Log the execution
        await self._log_execution(execution)

        log.info(
            "Tool execution completed",
            tool_name=tool_name,
            result=execution.result,
            duration_ms=execution.duration_ms,
        )

    async def _request_confirmation(
        self,
        tool_name: str,
        reason: str,
        tool_input: dict[str, Any],
    ) -> bool:
        """Request user confirmation for a tool execution.

        Args:
            tool_name: Name of the tool.
            reason: Reason confirmation is needed.
            tool_input: Tool input parameters.

        Returns:
            True if user confirmed, False otherwise.
        """
        if self._confirmation_callback:
            try:
                return await asyncio.wait_for(
                    self._confirmation_callback(tool_name, reason, tool_input),
                    timeout=60.0,  # Default timeout
                )
            except asyncio.TimeoutError:
                log.warning("Confirmation timed out", tool_name=tool_name)
                return False

        # No callback - log and allow (for development)
        log.warning(
            "No confirmation callback configured, allowing by default",
            tool_name=tool_name,
        )
        return True

    async def _notify_user(self, tool_name: str, message: str) -> None:
        """Notify user about a tool execution.

        Args:
            tool_name: Name of the tool.
            message: Notification message.
        """
        if self._notification_callback:
            await self._notification_callback(tool_name, message)
        else:
            log.info("User notification", tool_name=tool_name, message=message)

    async def _log_execution(self, execution: ToolExecution) -> None:
        """Log a tool execution to the audit log.

        Args:
            execution: The execution record to log.
        """
        if self._audit_callback:
            await self._audit_callback(execution)
        else:
            log.info(
                "Tool execution audit",
                id=execution.id,
                tool_name=execution.tool_name,
                tier=execution.permission_tier,
                decision=execution.decision,
                result=execution.result,
            )


def create_permission_hooks(
    config_path: str | None = None,
    evaluator: PermissionEvaluator | None = None,
) -> PermissionHooks:
    """Create permission hooks with optional configuration.

    Args:
        config_path: Path to permissions.yaml file.
        evaluator: Pre-configured evaluator to use.

    Returns:
        Configured PermissionHooks instance.
    """
    from pathlib import Path

    from reachy_agent.permissions.tiers import PermissionConfig

    if evaluator:
        return PermissionHooks(evaluator=evaluator)

    if config_path:
        config = PermissionConfig.from_yaml(Path(config_path))
        evaluator = PermissionEvaluator(config=config)
    else:
        evaluator = PermissionEvaluator()

    return PermissionHooks(evaluator=evaluator)
