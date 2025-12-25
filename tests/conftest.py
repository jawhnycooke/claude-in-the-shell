"""Pytest fixtures for Reachy Agent tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from reachy_agent.permissions.tiers import (
    PermissionConfig,
    PermissionEvaluator,
)
from reachy_agent.utils.config import ReachyConfig


@pytest.fixture
def anyio_backend() -> str:
    """Specify async backend for pytest-asyncio."""
    return "asyncio"


@pytest.fixture
def sample_config() -> ReachyConfig:
    """Create a sample configuration for testing."""
    return ReachyConfig()


@pytest.fixture
def permission_config() -> PermissionConfig:
    """Create a default permission configuration."""
    return PermissionConfig.default()


@pytest.fixture
def permission_evaluator(permission_config: PermissionConfig) -> PermissionEvaluator:
    """Create a permission evaluator with default config."""
    return PermissionEvaluator(config=permission_config)


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory with test files."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create a test config file
    config_file = config_dir / "default.yaml"
    config_file.write_text("""
version: "1.0"
agent:
  name: TestReachy
  wake_word: hey test
  model: claude-sonnet-4-20250514
  max_tokens: 512
""")

    return config_dir


@pytest.fixture
def sample_tool_calls() -> list[dict[str, str]]:
    """Sample tool calls for testing permissions."""
    return [
        {"name": "mcp__reachy__move_head", "expected_tier": 1},
        {"name": "mcp__homeassistant__turn_on_lights", "expected_tier": 2},
        {"name": "mcp__calendar__create_event", "expected_tier": 3},
        {"name": "mcp__banking__transfer", "expected_tier": 4},
    ]
