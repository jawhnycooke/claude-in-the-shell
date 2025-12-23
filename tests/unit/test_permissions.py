"""Unit tests for the permission system."""

from __future__ import annotations

import pytest

from reachy_agent.permissions.tiers import (
    PermissionConfig,
    PermissionDecision,
    PermissionEvaluator,
    PermissionRule,
    PermissionTier,
    TIER_BEHAVIORS,
)


class TestPermissionTier:
    """Tests for PermissionTier enum."""

    def test_tier_ordering(self) -> None:
        """Verify tiers are ordered correctly (lower = more permissive)."""
        assert PermissionTier.AUTONOMOUS < PermissionTier.NOTIFY
        assert PermissionTier.NOTIFY < PermissionTier.CONFIRM
        assert PermissionTier.CONFIRM < PermissionTier.FORBIDDEN

    def test_tier_values(self) -> None:
        """Verify tier integer values."""
        assert PermissionTier.AUTONOMOUS.value == 1
        assert PermissionTier.NOTIFY.value == 2
        assert PermissionTier.CONFIRM.value == 3
        assert PermissionTier.FORBIDDEN.value == 4


class TestPermissionRule:
    """Tests for PermissionRule matching."""

    def test_exact_match(self) -> None:
        """Test exact tool name matching."""
        rule = PermissionRule(pattern="move_head", tier=1, reason="test")
        assert rule.matches("move_head")
        assert not rule.matches("move_body")

    def test_wildcard_suffix(self) -> None:
        """Test wildcard matching at end of pattern."""
        rule = PermissionRule(pattern="mcp__reachy__*", tier=1, reason="test")
        assert rule.matches("mcp__reachy__move_head")
        assert rule.matches("mcp__reachy__speak")
        assert not rule.matches("mcp__calendar__get_events")

    def test_wildcard_prefix(self) -> None:
        """Test wildcard matching at start of pattern."""
        rule = PermissionRule(pattern="*__get_events", tier=1, reason="test")
        assert rule.matches("mcp__calendar__get_events")
        assert rule.matches("custom__get_events")
        assert not rule.matches("mcp__calendar__create_event")

    def test_wildcard_middle(self) -> None:
        """Test wildcard in middle of pattern."""
        rule = PermissionRule(pattern="mcp__*__get_*", tier=1, reason="test")
        assert rule.matches("mcp__calendar__get_events")
        assert rule.matches("mcp__github__get_notifications")

    def test_permission_tier_property(self) -> None:
        """Test converting tier int to enum."""
        rule = PermissionRule(pattern="test", tier=3, reason="test")
        assert rule.permission_tier == PermissionTier.CONFIRM


class TestPermissionEvaluator:
    """Tests for PermissionEvaluator."""

    def test_reachy_tools_are_autonomous(
        self, permission_evaluator: PermissionEvaluator
    ) -> None:
        """Reachy body control tools should be tier 1 (autonomous)."""
        tools = [
            "mcp__reachy__move_head",
            "mcp__reachy__speak",
            "mcp__reachy__play_emotion",
            "mcp__reachy__capture_image",
        ]

        for tool in tools:
            decision = permission_evaluator.evaluate(tool)
            assert decision.tier == PermissionTier.AUTONOMOUS, f"{tool} should be autonomous"
            assert decision.allowed
            assert not decision.needs_confirmation

    def test_homeassistant_notify_tier(
        self, permission_evaluator: PermissionEvaluator
    ) -> None:
        """Home Assistant control should be tier 2 (notify)."""
        tools = [
            "mcp__homeassistant__turn_on_lights",
            "mcp__homeassistant__turn_off_fan",
        ]

        for tool in tools:
            decision = permission_evaluator.evaluate(tool)
            assert decision.tier == PermissionTier.NOTIFY, f"{tool} should be notify"
            assert decision.allowed
            assert decision.should_notify
            assert not decision.needs_confirmation

    def test_create_actions_need_confirmation(
        self, permission_evaluator: PermissionEvaluator
    ) -> None:
        """Create actions should require confirmation."""
        tools = [
            "mcp__calendar__create_event",
            "mcp__github__create_issue",
        ]

        for tool in tools:
            decision = permission_evaluator.evaluate(tool)
            assert decision.tier == PermissionTier.CONFIRM, f"{tool} should be confirm"
            assert decision.needs_confirmation

    def test_forbidden_tools_are_blocked(
        self, permission_evaluator: PermissionEvaluator
    ) -> None:
        """Forbidden tools should not be allowed."""
        tools = [
            "mcp__homeassistant__disarm_alarm",
            "mcp__email__send",
            "mcp__banking__transfer",
        ]

        for tool in tools:
            decision = permission_evaluator.evaluate(tool)
            assert decision.tier == PermissionTier.FORBIDDEN, f"{tool} should be forbidden"
            assert not decision.allowed

    def test_unknown_tool_uses_default(
        self, permission_evaluator: PermissionEvaluator
    ) -> None:
        """Unknown tools should use default tier (CONFIRM)."""
        decision = permission_evaluator.evaluate("unknown__tool__name")
        assert decision.tier == PermissionTier.CONFIRM  # Default
        assert decision.matched_rule is None

    def test_first_matching_rule_wins(self) -> None:
        """First matching rule should take precedence."""
        config = PermissionConfig(
            tiers=[],
            rules=[
                PermissionRule(pattern="test__*", tier=2, reason="broad"),
                PermissionRule(pattern="test__specific", tier=1, reason="specific"),
            ],
        )
        evaluator = PermissionEvaluator(config=config)

        decision = evaluator.evaluate("test__specific")
        # First rule matches, so tier 2
        assert decision.tier == PermissionTier.NOTIFY

    def test_add_rule(self, permission_evaluator: PermissionEvaluator) -> None:
        """Test adding a new rule."""
        new_rule = PermissionRule(
            pattern="custom__tool",
            tier=1,
            reason="Custom tool",
        )
        permission_evaluator.add_rule(new_rule, priority=0)

        decision = permission_evaluator.evaluate("custom__tool")
        assert decision.tier == PermissionTier.AUTONOMOUS

    def test_remove_rule(self, permission_evaluator: PermissionEvaluator) -> None:
        """Test removing a rule."""
        # First verify the rule exists
        decision = permission_evaluator.evaluate("mcp__reachy__move_head")
        assert decision.tier == PermissionTier.AUTONOMOUS

        # Remove the rule
        removed = permission_evaluator.remove_rule("mcp__reachy__*")
        assert removed

        # Now should fall to default
        decision = permission_evaluator.evaluate("mcp__reachy__move_head")
        assert decision.tier == PermissionTier.CONFIRM  # Default tier


class TestPermissionDecision:
    """Tests for PermissionDecision."""

    def test_autonomous_decision(self) -> None:
        """Test autonomous tier decision properties."""
        decision = PermissionDecision(
            tool_name="test",
            tier=PermissionTier.AUTONOMOUS,
            behavior=TIER_BEHAVIORS[PermissionTier.AUTONOMOUS],
            reason="test",
        )

        assert decision.allowed
        assert not decision.needs_confirmation
        assert not decision.should_notify

    def test_notify_decision(self) -> None:
        """Test notify tier decision properties."""
        decision = PermissionDecision(
            tool_name="test",
            tier=PermissionTier.NOTIFY,
            behavior=TIER_BEHAVIORS[PermissionTier.NOTIFY],
            reason="test",
        )

        assert decision.allowed
        assert not decision.needs_confirmation
        assert decision.should_notify

    def test_confirm_decision(self) -> None:
        """Test confirm tier decision properties."""
        decision = PermissionDecision(
            tool_name="test",
            tier=PermissionTier.CONFIRM,
            behavior=TIER_BEHAVIORS[PermissionTier.CONFIRM],
            reason="test",
        )

        assert decision.allowed  # Allowed after confirmation
        assert decision.needs_confirmation
        assert decision.should_notify

    def test_forbidden_decision(self) -> None:
        """Test forbidden tier decision properties."""
        decision = PermissionDecision(
            tool_name="test",
            tier=PermissionTier.FORBIDDEN,
            behavior=TIER_BEHAVIORS[PermissionTier.FORBIDDEN],
            reason="test",
        )

        assert not decision.allowed
        assert not decision.needs_confirmation
        assert decision.should_notify


class TestPermissionConfig:
    """Tests for PermissionConfig loading."""

    def test_default_config(self) -> None:
        """Test loading default configuration."""
        config = PermissionConfig.default()

        assert len(config.tiers) == 4
        assert len(config.rules) > 0

        # Verify tier names
        tier_names = [t.name for t in config.tiers]
        assert "autonomous" in tier_names
        assert "notify" in tier_names
        assert "confirm" in tier_names
        assert "forbidden" in tier_names

    def test_from_yaml(self, tmp_path) -> None:
        """Test loading config from YAML file."""
        config_path = tmp_path / "permissions.yaml"
        config_path.write_text("""
tiers:
  - tier: 1
    name: autonomous
    description: Test tier
    behavior:
      execute: true
      notify_user: false
      require_confirmation: false

rules:
  - pattern: "test__*"
    tier: 1
    reason: "Test rule"
""")

        config = PermissionConfig.from_yaml(config_path)

        assert len(config.tiers) == 1
        assert len(config.rules) == 1
        assert config.rules[0].pattern == "test__*"
