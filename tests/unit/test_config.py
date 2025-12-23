"""Unit tests for configuration management."""

from __future__ import annotations

from pathlib import Path

import pytest

from reachy_agent.utils.config import (
    AgentConfig,
    AttentionConfig,
    ClaudeModel,
    EnvSettings,
    IntegrationsConfig,
    MemoryConfig,
    PerceptionConfig,
    PrivacyConfig,
    ReachyConfig,
    ResilienceConfig,
    WakeWordEngine,
    load_config,
)


class TestAgentConfig:
    """Tests for AgentConfig."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = AgentConfig()
        assert config.name == "Reachy"
        assert config.wake_word == "hey reachy"
        assert config.model == ClaudeModel.SONNET
        assert config.max_tokens == 1024

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = AgentConfig(
            name="TestBot",
            wake_word="hey bot",
            model=ClaudeModel.HAIKU,
            max_tokens=512,
        )
        assert config.name == "TestBot"
        assert config.model == ClaudeModel.HAIKU


class TestPerceptionConfig:
    """Tests for PerceptionConfig."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = PerceptionConfig()
        assert config.wake_word_engine == WakeWordEngine.OPENWAKEWORD
        assert config.wake_word_sensitivity == 0.5
        assert config.spatial_audio_enabled
        assert config.vision_enabled

    def test_sensitivity_validation(self) -> None:
        """Test sensitivity bounds."""
        config = PerceptionConfig(wake_word_sensitivity=0.0)
        assert config.wake_word_sensitivity == 0.0

        config = PerceptionConfig(wake_word_sensitivity=1.0)
        assert config.wake_word_sensitivity == 1.0


class TestMemoryConfig:
    """Tests for MemoryConfig."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = MemoryConfig()
        assert "chroma" in config.chroma_path
        assert config.embedding_model == "all-MiniLM-L6-v2"
        assert config.max_memories == 10000
        assert config.retention_days == 90


class TestResilienceConfig:
    """Tests for ResilienceConfig."""

    def test_defaults(self) -> None:
        """Test default values."""
        config = ResilienceConfig()
        assert config.thermal_threshold_celsius == 80.0
        assert config.api_timeout_seconds == 30.0
        assert config.max_retries == 3
        assert config.offline_llm_model == "llama3.2:3b"


class TestPrivacyConfig:
    """Tests for PrivacyConfig."""

    def test_defaults_are_privacy_preserving(self) -> None:
        """Default config should preserve privacy."""
        config = PrivacyConfig()
        assert config.audit_logging_enabled
        assert not config.store_audio  # Privacy by default
        assert not config.store_images  # Privacy by default


class TestReachyConfig:
    """Tests for complete ReachyConfig."""

    def test_defaults(self) -> None:
        """Test default configuration."""
        config = ReachyConfig()
        assert config.version == "1.0"
        assert config.agent.name == "Reachy"
        assert config.perception.wake_word_engine == WakeWordEngine.OPENWAKEWORD
        assert config.privacy.audit_logging_enabled

    def test_from_yaml(self, tmp_path: Path) -> None:
        """Test loading from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("""
version: "2.0"
agent:
  name: CustomReachy
  max_tokens: 2048
perception:
  spatial_audio_enabled: false
""")

        config = ReachyConfig.from_yaml(config_file)

        assert config.version == "2.0"
        assert config.agent.name == "CustomReachy"
        assert config.agent.max_tokens == 2048
        assert not config.perception.spatial_audio_enabled
        # Defaults should still apply for unspecified values
        assert config.memory.embedding_model == "all-MiniLM-L6-v2"

    def test_to_yaml(self, tmp_path: Path) -> None:
        """Test saving to YAML file."""
        config = ReachyConfig(
            agent=AgentConfig(name="TestBot", max_tokens=512),
        )

        output_path = tmp_path / "output.yaml"
        config.to_yaml(output_path)

        # Reload and verify
        loaded = ReachyConfig.from_yaml(output_path)
        assert loaded.agent.name == "TestBot"
        assert loaded.agent.max_tokens == 512

    def test_nested_path_creation(self, tmp_path: Path) -> None:
        """Test that to_yaml creates parent directories."""
        config = ReachyConfig()
        output_path = tmp_path / "nested" / "path" / "config.yaml"

        config.to_yaml(output_path)

        assert output_path.exists()


class TestLoadConfig:
    """Tests for load_config function."""

    def test_loads_from_explicit_path(self, tmp_path: Path) -> None:
        """Test loading from explicit path."""
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("""
version: "1.0"
agent:
  name: ExplicitConfig
""")

        config = load_config(config_path=config_file)
        assert config.agent.name == "ExplicitConfig"

    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        """Test returns defaults when no config file exists."""
        config = load_config(default_paths=[tmp_path / "nonexistent.yaml"])
        assert config.agent.name == "Reachy"  # Default

    def test_searches_default_paths(self, tmp_path: Path) -> None:
        """Test searching default paths in order."""
        # Create second path (higher priority should be first)
        first_path = tmp_path / "first.yaml"
        second_path = tmp_path / "second.yaml"

        second_path.write_text("""
version: "1.0"
agent:
  name: Second
""")

        config = load_config(default_paths=[first_path, second_path])
        assert config.agent.name == "Second"


class TestEnvSettings:
    """Tests for environment settings."""

    def test_loads_from_environment(self, monkeypatch) -> None:
        """Test loading from environment variables."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        monkeypatch.setenv("REACHY_DEBUG", "true")

        settings = EnvSettings()

        assert settings.anthropic_api_key == "test-key"
        assert settings.debug is True

    def test_default_values(self, monkeypatch) -> None:
        """Test default values when env vars not set."""
        # Clear any existing env vars
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("REACHY_DEBUG", raising=False)

        settings = EnvSettings()

        assert settings.anthropic_api_key is None
        assert settings.debug is False
