"""Persona configuration and management for multi-wake-word support.

Enables different AI personalities tied to different wake words,
with distinct voices and system prompts.

Ghost in the Shell theme:
- "Hey Motoko" → Major Kusanagi (nova voice, analytical)
- "Hey Batou" → Batou (onyx voice, casual)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from reachy_agent.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PersonaConfig:
    """Configuration for a persona tied to a wake word.

    Attributes:
        name: Internal identifier (e.g., "motoko", "batou")
        wake_word_model: OpenWakeWord model name (e.g., "hey_motoko")
        voice: OpenAI TTS voice (alloy, echo, fable, onyx, nova, shimmer)
        display_name: Human-readable name (e.g., "Major Kusanagi")
        prompt_path: Path to the persona's system prompt file
        traits: Optional personality traits for runtime reference
    """

    name: str
    wake_word_model: str
    voice: str
    display_name: str
    prompt_path: str
    traits: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, wake_word_model: str, data: dict[str, Any]) -> PersonaConfig:
        """Create PersonaConfig from dictionary (YAML config).

        Args:
            wake_word_model: The wake word model key (e.g., "hey_motoko")
            data: Configuration dictionary with persona settings

        Returns:
            PersonaConfig instance
        """
        return cls(
            name=data.get("name", wake_word_model.replace("hey_", "")),
            wake_word_model=wake_word_model,
            voice=data.get("voice", "alloy"),
            display_name=data.get("display_name", wake_word_model.title()),
            prompt_path=data.get("prompt_path", f"prompts/personas/{wake_word_model.replace('hey_', '')}.md"),
            traits=data.get("traits", {}),
        )

    def __eq__(self, other: object) -> bool:
        """Compare personas by name."""
        if not isinstance(other, PersonaConfig):
            return False
        return self.name == other.name

    def __hash__(self) -> int:
        """Hash by name for set/dict operations."""
        return hash(self.name)


@dataclass
class PersonaManager:
    """Manages persona registration and lookup.

    Provides a centralized way to manage personas tied to wake words,
    handling registration, lookup, and default persona selection.
    """

    personas: dict[str, PersonaConfig] = field(default_factory=dict)
    current_persona: PersonaConfig | None = None
    default_persona_key: str = ""

    def register_persona(self, config: PersonaConfig) -> None:
        """Register a persona for a wake word model.

        Args:
            config: PersonaConfig to register
        """
        self.personas[config.wake_word_model] = config
        logger.info(
            "persona_registered",
            wake_word=config.wake_word_model,
            persona=config.name,
            voice=config.voice,
            display_name=config.display_name,
        )

    def get_persona(self, wake_word_model: str) -> PersonaConfig | None:
        """Get persona config for a wake word model.

        Args:
            wake_word_model: The wake word model name (e.g., "hey_motoko")

        Returns:
            PersonaConfig if found, None otherwise
        """
        return self.personas.get(wake_word_model)

    def set_default(self, wake_word_model: str) -> bool:
        """Set the default persona.

        Args:
            wake_word_model: The wake word model to use as default

        Returns:
            True if default was set successfully
        """
        if wake_word_model in self.personas:
            self.default_persona_key = wake_word_model
            if self.current_persona is None:
                self.current_persona = self.personas[wake_word_model]
                logger.info(
                    "default_persona_set",
                    persona=self.current_persona.name,
                    voice=self.current_persona.voice,
                )
            return True
        logger.warning(
            "default_persona_not_found",
            requested=wake_word_model,
            available=list(self.personas.keys()),
        )
        return False

    def get_default(self) -> PersonaConfig | None:
        """Get the default persona.

        Returns:
            Default PersonaConfig if set, None otherwise
        """
        return self.personas.get(self.default_persona_key)

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> PersonaManager:
        """Create PersonaManager from voice config dictionary.

        Args:
            config: Voice configuration with 'personas' and 'default_persona' keys

        Returns:
            Configured PersonaManager
        """
        manager = cls()

        personas_config = config.get("personas", {})
        for wake_word_model, persona_data in personas_config.items():
            persona = PersonaConfig.from_dict(wake_word_model, persona_data)
            manager.register_persona(persona)

        default_key = config.get("default_persona", "")
        if default_key:
            manager.set_default(default_key)
        elif personas_config:
            # Use first persona as default if none specified
            first_key = next(iter(personas_config.keys()))
            manager.set_default(first_key)

        return manager
