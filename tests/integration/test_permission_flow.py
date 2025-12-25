"""Integration tests for the permission system flow.

Tests the full permission flow from permission hooks through handlers
and audit storage to verify:
- Tier 1 (Autonomous) executes immediately without notification
- Tier 2 (Notify) executes and notifies user
- Tier 3 (Confirm) requires confirmation callback
- Tier 4 (Forbidden) blocks execution
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from reachy_agent.permissions.handlers import (
    CLIPermissionHandler,
    WebSocketPermissionHandler,
)
from reachy_agent.permissions.hooks import (
    PermissionHooks,
    ToolExecution,
)
from reachy_agent.permissions.storage.sqlite_audit import (
    AuditRecord,
    SQLiteAuditStorage,
    create_audit_callback,
)
from reachy_agent.permissions.tiers import (
    PermissionConfig,
    PermissionEvaluator,
    PermissionRule,
    PermissionTier,
)


def create_test_config_with_rules(rules: list[PermissionRule]) -> PermissionConfig:
    """Create a test config with specific rules only (no defaults)."""
    return PermissionConfig(tiers=[], rules=rules)


class TestTier1Autonomous:
    """Tests for Tier 1 (Autonomous) permission flow."""

    @pytest.mark.asyncio
    async def test_tier1_executes_immediately(self) -> None:
        """Test that Tier 1 tools execute without any callbacks."""
        # Create a config where move_head is Tier 1
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__reachy__move_head",
                tier=1,
                reason="Body control - autonomous"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        # Track callback invocations
        confirmation_called = False
        notification_called = False

        async def confirmation_cb(
            tool_name: str, reason: str, tool_input: dict[str, Any]
        ) -> bool:
            nonlocal confirmation_called
            confirmation_called = True
            return True

        async def notification_cb(tool_name: str, message: str) -> None:
            nonlocal notification_called
            notification_called = True

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=confirmation_cb,
            notification_callback=notification_cb,
        )

        # Execute pre_tool_use
        result = await hooks.pre_tool_use(
            "mcp__reachy__move_head",
            {"direction": "left"},
        )

        # Should allow execution
        assert result is not None
        assert "_execution_id" in result
        assert "error" not in result

        # No callbacks should be invoked for Tier 1
        assert not confirmation_called
        assert not notification_called

    @pytest.mark.asyncio
    async def test_tier1_audit_log_records_allowed(self) -> None:
        """Test that Tier 1 executions are logged as 'allowed'."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__reachy__get_sensor_data",
                tier=1,
                reason="Observation - autonomous"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        audit_records: list[ToolExecution] = []

        async def audit_cb(execution: ToolExecution) -> None:
            audit_records.append(execution)

        hooks = PermissionHooks(
            evaluator=evaluator,
            audit_callback=audit_cb,
        )

        # Execute pre and post hooks
        result = await hooks.pre_tool_use(
            "mcp__reachy__get_sensor_data",
            {"sensors": ["all"]},
        )
        execution_id = result["_execution_id"] if result else None

        await hooks.post_tool_use(
            "mcp__reachy__get_sensor_data",
            {"sensors": ["all"]},
            {"temperature": 42.0},
            execution_id=execution_id,
        )

        # Check audit record
        assert len(audit_records) == 1
        record = audit_records[0]
        assert record.decision == "allowed"
        assert record.result == "success"
        assert record.permission_tier == PermissionTier.AUTONOMOUS.value


class TestTier2Notify:
    """Tests for Tier 2 (Notify) permission flow."""

    @pytest.mark.asyncio
    async def test_tier2_notifies_user(self) -> None:
        """Test that Tier 2 tools notify the user but don't require confirmation."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__reachy__speak",
                tier=2,
                reason="Reversible communication"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        notifications: list[tuple[str, str]] = []

        async def notification_cb(tool_name: str, message: str) -> None:
            notifications.append((tool_name, message))

        hooks = PermissionHooks(
            evaluator=evaluator,
            notification_callback=notification_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__reachy__speak",
            {"text": "Hello!"},
        )

        # Should allow execution
        assert result is not None
        assert "_execution_id" in result
        assert "error" not in result

        # Notification should be called
        assert len(notifications) == 1
        assert "mcp__reachy__speak" in notifications[0][0]

    @pytest.mark.asyncio
    async def test_tier2_audit_log_records_notified(self) -> None:
        """Test that Tier 2 executions are logged as 'notified'."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__reachy__speak",
                tier=2,
                reason="Reversible communication"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        audit_records: list[ToolExecution] = []

        async def audit_cb(execution: ToolExecution) -> None:
            audit_records.append(execution)

        hooks = PermissionHooks(
            evaluator=evaluator,
            notification_callback=AsyncMock(),
            audit_callback=audit_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__reachy__speak",
            {"text": "Hello!"},
        )
        execution_id = result["_execution_id"] if result else None

        await hooks.post_tool_use(
            "mcp__reachy__speak",
            {"text": "Hello!"},
            {"status": "success"},
            execution_id=execution_id,
        )

        assert len(audit_records) == 1
        assert audit_records[0].decision == "notified"
        assert audit_records[0].result == "success"


class TestTier3Confirm:
    """Tests for Tier 3 (Confirm) permission flow."""

    @pytest.mark.asyncio
    async def test_tier3_requires_confirmation(self) -> None:
        """Test that Tier 3 tools require confirmation callback."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__github__create_pr",
                tier=3,
                reason="Creates repository data"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        confirmation_requests: list[tuple[str, str, dict]] = []

        async def confirmation_cb(
            tool_name: str, reason: str, tool_input: dict[str, Any]
        ) -> bool:
            confirmation_requests.append((tool_name, reason, tool_input))
            return True  # Approve

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=confirmation_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__github__create_pr",
            {"title": "Fix bug", "body": "Description"},
        )

        # Should allow after confirmation
        assert result is not None
        assert "_execution_id" in result
        assert "error" not in result

        # Confirmation callback should be invoked
        assert len(confirmation_requests) == 1
        assert confirmation_requests[0][0] == "mcp__github__create_pr"

    @pytest.mark.asyncio
    async def test_tier3_denied_blocks_execution(self) -> None:
        """Test that denied confirmation blocks execution."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__github__create_pr",
                tier=3,
                reason="Creates repository data"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        async def confirmation_cb(
            tool_name: str, reason: str, tool_input: dict[str, Any]
        ) -> bool:
            return False  # Deny

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=confirmation_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__github__create_pr",
            {"title": "Fix bug"},
        )

        # Should block execution
        assert result is not None
        assert "error" in result
        assert "declined" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_tier3_audit_log_records_confirmed(self) -> None:
        """Test that confirmed Tier 3 executions are logged as 'confirmed'."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__home__turn_on",
                tier=3,
                reason="Smart home control"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        audit_records: list[ToolExecution] = []

        async def audit_cb(execution: ToolExecution) -> None:
            audit_records.append(execution)

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=AsyncMock(return_value=True),
            audit_callback=audit_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__home__turn_on",
            {"device": "light"},
        )
        execution_id = result["_execution_id"] if result else None

        await hooks.post_tool_use(
            "mcp__home__turn_on",
            {"device": "light"},
            {"status": "on"},
            execution_id=execution_id,
        )

        assert len(audit_records) == 1
        assert audit_records[0].decision == "confirmed"
        assert audit_records[0].result == "success"

    @pytest.mark.asyncio
    async def test_tier3_audit_log_records_denied(self) -> None:
        """Test that denied Tier 3 executions are logged as 'denied'."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__home__turn_on",
                tier=3,
                reason="Smart home control"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        audit_records: list[ToolExecution] = []

        async def audit_cb(execution: ToolExecution) -> None:
            audit_records.append(execution)

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=AsyncMock(return_value=False),
            audit_callback=audit_cb,
        )

        await hooks.pre_tool_use(
            "mcp__home__turn_on",
            {"device": "light"},
        )

        # Check audit records for denied
        assert len(audit_records) == 1
        assert audit_records[0].decision == "denied"
        assert audit_records[0].result == "error"


class TestTier4Forbidden:
    """Tests for Tier 4 (Forbidden) permission flow."""

    @pytest.mark.asyncio
    async def test_tier4_blocks_immediately(self) -> None:
        """Test that Tier 4 tools are blocked without any callbacks."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__system__reboot",
                tier=4,
                reason="Security critical"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        confirmation_called = False

        async def confirmation_cb(
            tool_name: str, reason: str, tool_input: dict[str, Any]
        ) -> bool:
            nonlocal confirmation_called
            confirmation_called = True
            return True

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=confirmation_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__system__reboot",
            {},
        )

        # Should block execution
        assert result is not None
        assert "error" in result
        assert result.get("tier") == "forbidden"

        # No callbacks should be invoked
        assert not confirmation_called

    @pytest.mark.asyncio
    async def test_tier4_audit_log_records_denied(self) -> None:
        """Test that Tier 4 executions are logged as 'denied'."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__system__reboot",
                tier=4,
                reason="Security critical"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        audit_records: list[ToolExecution] = []

        async def audit_cb(execution: ToolExecution) -> None:
            audit_records.append(execution)

        hooks = PermissionHooks(
            evaluator=evaluator,
            audit_callback=audit_cb,
        )

        await hooks.pre_tool_use(
            "mcp__system__reboot",
            {},
        )

        assert len(audit_records) == 1
        assert audit_records[0].decision == "denied"
        assert audit_records[0].result == "error"
        assert audit_records[0].permission_tier == PermissionTier.FORBIDDEN.value


class TestHandlerIntegration:
    """Tests for handler integration with permission hooks."""

    @pytest.mark.asyncio
    async def test_websocket_handler_confirmation_flow(self) -> None:
        """Test WebSocket handler confirmation flow."""
        handler = WebSocketPermissionHandler()

        # Simulate a connected client
        mock_ws = AsyncMock()
        handler.register_client(mock_ws)

        # Create a pending confirmation
        request_id = "test-confirmation-123"
        future: asyncio.Future[bool] = asyncio.Future()
        handler._pending_confirmations[request_id] = future

        # Simulate user approval via handle_confirmation_response
        result = await handler.handle_confirmation_response(request_id, approved=True)

        assert result is True
        assert future.result() is True

    @pytest.mark.asyncio
    async def test_websocket_handler_broadcasts_notifications(self) -> None:
        """Test WebSocket handler broadcasts notifications."""
        handler = WebSocketPermissionHandler()

        mock_ws = AsyncMock()
        handler.register_client(mock_ws)

        await handler.notify(
            tool_name="mcp__reachy__speak",
            message="Speaking: Hello!",
            tier=2,
        )

        # Should broadcast to connected client
        mock_ws.send_text.assert_called_once()

        # Verify message content
        import json
        call_args = mock_ws.send_text.call_args[0][0]
        msg = json.loads(call_args)
        assert msg["type"] == "notification"
        assert msg["tool_name"] == "mcp__reachy__speak"

    @pytest.mark.asyncio
    async def test_cli_handler_notification(self) -> None:
        """Test CLI handler displays notifications."""
        mock_console = MagicMock()
        handler = CLIPermissionHandler(console=mock_console)

        await handler.notify(
            tool_name="mcp__reachy__move_head",
            message="Moving head to the left",
            tier=2,
        )

        # Verify console.print was called
        mock_console.print.assert_called_once()


class TestSQLiteAuditIntegration:
    """Tests for SQLite audit storage integration."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_execution(self, tmp_path) -> None:
        """Test storing and retrieving tool executions."""
        db_path = tmp_path / "test_audit.db"
        storage = SQLiteAuditStorage(db_path=db_path)

        try:
            # Create an AuditRecord (not ToolExecution)
            record = AuditRecord(
                id="test-123",
                timestamp=datetime.now(),
                tool_name="mcp__reachy__speak",
                tool_input={"text": "Hello!"},
                permission_tier=2,
                decision="notified",
                result="success",
                duration_ms=150,
            )

            # Store it
            await storage.store(record)

            # Retrieve recent records
            records = await storage.get_recent(limit=10)

            assert len(records) == 1
            assert records[0].id == "test-123"
            assert records[0].tool_name == "mcp__reachy__speak"
            assert records[0].decision == "notified"

        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_audit_callback_integration(self, tmp_path) -> None:
        """Test permission hooks with SQLite audit callback using adapter."""
        db_path = tmp_path / "test_audit.db"
        storage = SQLiteAuditStorage(db_path=db_path)

        try:
            config = create_test_config_with_rules([
                PermissionRule(
                    pattern="mcp__reachy__capture_image",
                    tier=1,
                    reason="Observation"
                )
            ])
            evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

            # Use the adapter function to convert ToolExecution to AuditRecord
            audit_callback = create_audit_callback(storage)

            hooks = PermissionHooks(
                evaluator=evaluator,
                audit_callback=audit_callback,
            )

            # Execute a tool
            result = await hooks.pre_tool_use(
                "mcp__reachy__capture_image",
                {"analyze": True},
            )
            execution_id = result["_execution_id"] if result else None

            await hooks.post_tool_use(
                "mcp__reachy__capture_image",
                {"analyze": True},
                {"image_data": "base64..."},
                execution_id=execution_id,
            )

            # Check the database
            records = await storage.get_recent(limit=10)
            assert len(records) == 1
            assert records[0].tool_name == "mcp__reachy__capture_image"
            assert records[0].decision == "allowed"

        finally:
            await storage.close()


class TestErrorHandling:
    """Tests for error handling in permission flow."""

    @pytest.mark.asyncio
    async def test_confirmation_timeout(self) -> None:
        """Test that confirmation timeout is handled gracefully."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__slow__tool",
                tier=3,
                reason="Requires confirmation"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        async def slow_confirmation(
            tool_name: str, reason: str, tool_input: dict[str, Any]
        ) -> bool:
            await asyncio.sleep(120)  # Longer than timeout
            return True

        hooks = PermissionHooks(
            evaluator=evaluator,
            confirmation_callback=slow_confirmation,
        )

        # The hook uses a 60 second timeout internally
        # For testing, we mock wait_for to cancel the coroutine and raise TimeoutError
        import unittest.mock

        original_wait_for = asyncio.wait_for

        async def mock_wait_for(coro, timeout):
            """Cancel the coroutine properly before raising TimeoutError."""
            # Close the coroutine to prevent 'never awaited' warning
            coro.close()
            raise asyncio.TimeoutError()

        with unittest.mock.patch.object(asyncio, 'wait_for', side_effect=mock_wait_for):
            result = await hooks.pre_tool_use(
                "mcp__slow__tool",
                {},
            )

        # Should block on timeout
        assert result is not None
        assert "error" in result

    @pytest.mark.asyncio
    async def test_post_hook_error_recording(self) -> None:
        """Test that post-hook records errors correctly."""
        config = create_test_config_with_rules([
            PermissionRule(
                pattern="mcp__reachy__move_head",
                tier=1,
                reason="Body control"
            )
        ])
        evaluator = PermissionEvaluator(config=config, default_tier=PermissionTier.CONFIRM)

        audit_records: list[ToolExecution] = []

        async def audit_cb(execution: ToolExecution) -> None:
            audit_records.append(execution)

        hooks = PermissionHooks(
            evaluator=evaluator,
            audit_callback=audit_cb,
        )

        result = await hooks.pre_tool_use(
            "mcp__reachy__move_head",
            {"direction": "left"},
        )
        execution_id = result["_execution_id"] if result else None

        # Simulate an error during execution
        await hooks.post_tool_use(
            "mcp__reachy__move_head",
            {"direction": "left"},
            None,
            execution_id=execution_id,
            error=RuntimeError("Motor failed"),
        )

        assert len(audit_records) == 1
        assert audit_records[0].result == "error"


class TestDefaultPermissions:
    """Tests for default permission rules from PermissionConfig.default()."""

    @pytest.mark.asyncio
    async def test_reachy_tools_are_tier1_by_default(self) -> None:
        """Test that mcp__reachy__* tools are Tier 1 in default config."""
        # Use the default config with all default rules
        evaluator = PermissionEvaluator()

        decision = evaluator.evaluate("mcp__reachy__move_head")
        assert decision.tier == PermissionTier.AUTONOMOUS
        assert decision.allowed
        assert not decision.needs_confirmation

    @pytest.mark.asyncio
    async def test_github_create_is_tier3_by_default(self) -> None:
        """Test that mcp__github__create_* tools are Tier 3 in default config."""
        evaluator = PermissionEvaluator()

        decision = evaluator.evaluate("mcp__github__create_pr")
        assert decision.tier == PermissionTier.CONFIRM
        assert decision.needs_confirmation

    @pytest.mark.asyncio
    async def test_banking_is_tier4_by_default(self) -> None:
        """Test that mcp__banking__* tools are Tier 4 in default config."""
        evaluator = PermissionEvaluator()

        decision = evaluator.evaluate("mcp__banking__transfer")
        assert decision.tier == PermissionTier.FORBIDDEN
        assert not decision.allowed

    @pytest.mark.asyncio
    async def test_unknown_tools_default_to_confirm(self) -> None:
        """Test that unknown tools default to Tier 3 (Confirm)."""
        evaluator = PermissionEvaluator()

        decision = evaluator.evaluate("mcp__unknown__tool")
        assert decision.tier == PermissionTier.CONFIRM
        assert decision.needs_confirmation
