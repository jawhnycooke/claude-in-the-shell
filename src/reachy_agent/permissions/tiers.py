"""Permission tier definitions for Reachy Agent.

Implements a 4-tier permission system as defined in TECH_REQ.md:
- Tier 1 (Autonomous): Execute immediately without notification
- Tier 2 (Notify): Execute and notify user
- Tier 3 (Confirm): Request confirmation before execution
- Tier 4 (Forbidden): Never execute
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PermissionTier(IntEnum):
    """Permission tier levels.

    Lower numbers = more permissive.
    """

    AUTONOMOUS = 1  # Execute immediately, no notification
    NOTIFY = 2  # Execute and notify user
    CONFIRM = 3  # Request confirmation before execution
    FORBIDDEN = 4  # Never execute, explain why


@dataclass
class TierBehavior:
    """Behavior configuration for a permission tier."""

    execute: bool
    notify_user: bool
    require_confirmation: bool
    confirmation_timeout_seconds: int = 60


# Default behaviors for each tier
TIER_BEHAVIORS: dict[PermissionTier, TierBehavior] = {
    PermissionTier.AUTONOMOUS: TierBehavior(
        execute=True,
        notify_user=False,
        require_confirmation=False,
    ),
    PermissionTier.NOTIFY: TierBehavior(
        execute=True,
        notify_user=True,
        require_confirmation=False,
    ),
    PermissionTier.CONFIRM: TierBehavior(
        execute=True,
        notify_user=True,
        require_confirmation=True,
        confirmation_timeout_seconds=60,
    ),
    PermissionTier.FORBIDDEN: TierBehavior(
        execute=False,
        notify_user=True,
        require_confirmation=False,
    ),
}


class PermissionRule(BaseModel):
    """A single permission rule matching tools to tiers."""

    pattern: str = Field(description="Tool name pattern with wildcards")
    tier: int = Field(ge=1, le=4, description="Permission tier (1-4)")
    reason: str = Field(description="Human-readable reason for this tier")

    def matches(self, tool_name: str) -> bool:
        """Check if this rule matches a tool name.

        Supports glob-style wildcards (* matches any characters).

        Args:
            tool_name: The tool name to check.

        Returns:
            True if the pattern matches the tool name.
        """
        return fnmatch.fnmatch(tool_name, self.pattern)

    @property
    def permission_tier(self) -> PermissionTier:
        """Get the permission tier as an enum."""
        return PermissionTier(self.tier)


class TierDefinition(BaseModel):
    """Definition of a permission tier from config."""

    tier: int = Field(ge=1, le=4)
    name: str
    description: str
    behavior: dict[str, Any] = Field(default_factory=dict)


class PermissionConfig(BaseModel):
    """Complete permission configuration."""

    tiers: list[TierDefinition] = Field(default_factory=list)
    rules: list[PermissionRule] = Field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> PermissionConfig:
        """Load permission configuration from YAML file.

        Args:
            path: Path to the permissions YAML file.

        Returns:
            Validated PermissionConfig instance.
        """
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    @classmethod
    def default(cls) -> PermissionConfig:
        """Get default permission configuration.

        Returns:
            PermissionConfig with sensible defaults for Reachy.
        """
        return cls(
            tiers=[
                TierDefinition(
                    tier=1,
                    name="autonomous",
                    description="Execute immediately without notification",
                    behavior={
                        "execute": True,
                        "notify_user": False,
                        "require_confirmation": False,
                    },
                ),
                TierDefinition(
                    tier=2,
                    name="notify",
                    description="Execute and notify user",
                    behavior={
                        "execute": True,
                        "notify_user": True,
                        "require_confirmation": False,
                    },
                ),
                TierDefinition(
                    tier=3,
                    name="confirm",
                    description="Request confirmation before execution",
                    behavior={
                        "execute": True,
                        "notify_user": True,
                        "require_confirmation": True,
                        "confirmation_timeout_seconds": 60,
                    },
                ),
                TierDefinition(
                    tier=4,
                    name="forbidden",
                    description="Never execute, explain why",
                    behavior={
                        "execute": False,
                        "notify_user": True,
                        "require_confirmation": False,
                    },
                ),
            ],
            rules=_default_rules(),
        )


def _default_rules() -> list[PermissionRule]:
    """Get default permission rules for Reachy Agent."""
    return [
        # Tier 1: Autonomous (body control, observation)
        PermissionRule(
            pattern="mcp__reachy__*",
            tier=1,
            reason="Body control",
        ),
        PermissionRule(
            pattern="mcp__calendar__get_*",
            tier=1,
            reason="Read-only calendar access",
        ),
        PermissionRule(
            pattern="mcp__weather__*",
            tier=1,
            reason="Weather information",
        ),
        PermissionRule(
            pattern="mcp__github__get_*",
            tier=1,
            reason="Read-only GitHub access",
        ),
        # Tier 2: Notify (reversible actions)
        PermissionRule(
            pattern="mcp__homeassistant__turn_on_*",
            tier=2,
            reason="Smart home control",
        ),
        PermissionRule(
            pattern="mcp__homeassistant__turn_off_*",
            tier=2,
            reason="Smart home control",
        ),
        PermissionRule(
            pattern="mcp__slack__send_message",
            tier=2,
            reason="Communication",
        ),
        PermissionRule(
            pattern="mcp__spotify__*",
            tier=2,
            reason="Media control",
        ),
        # Tier 3: Confirm (irreversible or sensitive)
        PermissionRule(
            pattern="mcp__calendar__create_*",
            tier=3,
            reason="Creates calendar data",
        ),
        PermissionRule(
            pattern="mcp__github__create_*",
            tier=3,
            reason="Creates repository data",
        ),
        PermissionRule(
            pattern="mcp__homeassistant__unlock_*",
            tier=3,
            reason="Security action",
        ),
        PermissionRule(
            pattern="Bash",
            tier=3,
            reason="System access",
        ),
        # Tier 4: Forbidden
        PermissionRule(
            pattern="mcp__homeassistant__disarm_*",
            tier=4,
            reason="Security critical - never autonomous",
        ),
        PermissionRule(
            pattern="mcp__email__send",
            tier=4,
            reason="Impersonation risk",
        ),
        PermissionRule(
            pattern="mcp__banking__*",
            tier=4,
            reason="Financial operations",
        ),
    ]


@dataclass
class PermissionDecision:
    """Result of a permission check."""

    tool_name: str
    tier: PermissionTier
    behavior: TierBehavior
    reason: str
    matched_rule: PermissionRule | None = None

    @property
    def allowed(self) -> bool:
        """Whether the tool execution is allowed."""
        return self.behavior.execute

    @property
    def needs_confirmation(self) -> bool:
        """Whether user confirmation is required."""
        return self.behavior.require_confirmation

    @property
    def should_notify(self) -> bool:
        """Whether user should be notified."""
        return self.behavior.notify_user


class PermissionEvaluator:
    """Evaluates tool permissions against configured rules."""

    def __init__(
        self,
        config: PermissionConfig | None = None,
        default_tier: PermissionTier = PermissionTier.CONFIRM,
    ) -> None:
        """Initialize the permission evaluator.

        Args:
            config: Permission configuration. Uses defaults if None.
            default_tier: Default tier for unmatched tools.
        """
        self.config = config or PermissionConfig.default()
        self.default_tier = default_tier
        self._rules = self.config.rules

    def evaluate(self, tool_name: str) -> PermissionDecision:
        """Evaluate permissions for a tool.

        Args:
            tool_name: Name of the tool to check.

        Returns:
            PermissionDecision with tier, behavior, and reason.
        """
        # Find first matching rule
        for rule in self._rules:
            if rule.matches(tool_name):
                tier = rule.permission_tier
                return PermissionDecision(
                    tool_name=tool_name,
                    tier=tier,
                    behavior=TIER_BEHAVIORS[tier],
                    reason=rule.reason,
                    matched_rule=rule,
                )

        # No matching rule - use default tier
        return PermissionDecision(
            tool_name=tool_name,
            tier=self.default_tier,
            behavior=TIER_BEHAVIORS[self.default_tier],
            reason="No matching rule - using default tier",
            matched_rule=None,
        )

    def add_rule(self, rule: PermissionRule, priority: int = 0) -> None:
        """Add a permission rule.

        Args:
            rule: The rule to add.
            priority: Position in rule list (0 = highest priority).
        """
        self._rules.insert(priority, rule)

    def remove_rule(self, pattern: str) -> bool:
        """Remove rules matching a pattern.

        Args:
            pattern: Pattern to match for removal.

        Returns:
            True if any rules were removed.
        """
        original_count = len(self._rules)
        self._rules = [r for r in self._rules if r.pattern != pattern]
        return len(self._rules) < original_count
