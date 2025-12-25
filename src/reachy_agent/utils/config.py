"""Configuration management for Reachy Agent.

Loads configuration from YAML files and validates against Pydantic models.
Follows the schema defined in TECH_REQ.md.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WakeWordEngine(str, Enum):
    """Supported wake word detection engines."""

    OPENWAKEWORD = "openwakeword"
    PORCUPINE = "porcupine"
    VOSK = "vosk"


class ClaudeModel(str, Enum):
    """Supported Claude models."""

    SONNET = "claude-sonnet-4-5-20250929"
    HAIKU = "claude-3-5-haiku-20241022"


class AgentConfig(BaseModel):
    """Agent-specific configuration."""

    name: str = Field(default="Reachy", description="Robot's display name")
    wake_word: str = Field(default="hey reachy", description="Wake word phrase")
    model: ClaudeModel = Field(
        default=ClaudeModel.SONNET, description="Claude model to use"
    )
    max_tokens: int = Field(default=1024, ge=1, le=4096)


class PerceptionConfig(BaseModel):
    """Perception system configuration."""

    wake_word_engine: WakeWordEngine = Field(default=WakeWordEngine.OPENWAKEWORD)
    wake_word_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    spatial_audio_enabled: bool = Field(default=True)
    vision_enabled: bool = Field(default=True)
    face_detection_enabled: bool = Field(default=True)


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    chroma_path: str = Field(default="~/.reachy/memory/chroma")
    sqlite_path: str = Field(default="~/.reachy/memory/reachy.db")
    embedding_model: str = Field(default="all-MiniLM-L6-v2")
    max_memories: int = Field(default=10000, ge=100)
    retention_days: int = Field(default=90, ge=1)


class AttentionConfig(BaseModel):
    """Attention state machine configuration."""

    passive_to_alert_motion_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    alert_to_passive_timeout_minutes: int = Field(default=5, ge=1)
    engaged_to_alert_silence_seconds: int = Field(default=30, ge=5)


class ResilienceConfig(BaseModel):
    """Resilience and degradation configuration."""

    thermal_threshold_celsius: float = Field(default=80.0, ge=50.0, le=100.0)
    api_timeout_seconds: float = Field(default=30.0, ge=1.0)
    max_retries: int = Field(default=3, ge=0, le=10)
    offline_llm_model: str = Field(default="llama3.2:3b")


class PrivacyConfig(BaseModel):
    """Privacy and audit configuration."""

    audit_logging_enabled: bool = Field(default=True)
    audit_retention_days: int = Field(default=7, ge=1)
    store_audio: bool = Field(default=False)
    store_images: bool = Field(default=False)


class HomeAssistantConfig(BaseModel):
    """Home Assistant integration configuration."""

    enabled: bool = Field(default=False)
    url: str | None = Field(default=None)
    token_env_var: str = Field(default="HA_TOKEN")


class GoogleCalendarConfig(BaseModel):
    """Google Calendar integration configuration."""

    enabled: bool = Field(default=False)
    credentials_path: str | None = Field(default=None)


class GitHubConfig(BaseModel):
    """GitHub integration configuration."""

    enabled: bool = Field(default=False)
    token_env_var: str = Field(default="GITHUB_TOKEN")
    repos: list[str] = Field(default_factory=list)


class IntegrationsConfig(BaseModel):
    """External integrations configuration."""

    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)
    google_calendar: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)


class ReachyConfig(BaseModel):
    """Main Reachy Agent configuration.

    Corresponds to the main configuration schema in TECH_REQ.md.
    """

    version: str = Field(default="1.0", pattern=r"^\d+\.\d+$")
    agent: AgentConfig = Field(default_factory=AgentConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    attention: AttentionConfig = Field(default_factory=AttentionConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> ReachyConfig:
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            Validated ReachyConfig instance.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            yaml.YAMLError: If the YAML is malformed.
            pydantic.ValidationError: If validation fails.
        """
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    def to_yaml(self, path: Path) -> None:
        """Save configuration to a YAML file.

        Args:
            path: Path to write the YAML configuration file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(
                self.model_dump(mode="json"),
                f,
                default_flow_style=False,
                sort_keys=False,
            )


class EnvSettings(BaseSettings):
    """Environment variable settings.

    API keys and secrets loaded from environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="REACHY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
        description="Anthropic API key for Claude",
    )
    ha_token: str | None = Field(
        default=None,
        alias="HA_TOKEN",
        description="Home Assistant long-lived access token",
    )
    github_token: str | None = Field(
        default=None,
        alias="GITHUB_TOKEN",
        description="GitHub personal access token",
    )
    debug: bool = Field(
        default=False,
        alias="REACHY_DEBUG",
        description="Enable debug logging",
    )


def load_config(
    config_path: Path | None = None,
    default_paths: list[Path] | None = None,
) -> ReachyConfig:
    """Load configuration from file or use defaults.

    Search order:
    1. Explicit config_path if provided
    2. Default paths in order: ./config/default.yaml, ~/.reachy/config.yaml
    3. Built-in defaults if no file found

    Args:
        config_path: Explicit path to config file.
        default_paths: List of paths to search for config.

    Returns:
        Validated ReachyConfig instance.
    """
    if default_paths is None:
        default_paths = [
            Path("config/default.yaml"),
            Path.home() / ".reachy" / "config.yaml",
        ]

    if config_path is not None:
        return ReachyConfig.from_yaml(config_path)

    for path in default_paths:
        if path.exists():
            return ReachyConfig.from_yaml(path)

    # Return defaults if no config file found
    return ReachyConfig()


def get_env_settings() -> EnvSettings:
    """Load environment settings.

    Returns:
        EnvSettings instance with values from environment.
    """
    return EnvSettings()
