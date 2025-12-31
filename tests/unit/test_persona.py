"""Unit tests for persona configuration and management.

Tests cover:
- PersonaConfig creation and validation
- PersonaManager registration and lookup
- Factory methods (from_dict, from_config)
- Edge cases and error handling
"""

from __future__ import annotations

import pytest

from reachy_agent.voice.persona import (
    VALID_VOICES,
    OpenAIVoice,
    PersonaConfig,
    PersonaManager,
)


class TestPersonaConfig:
    """Tests for PersonaConfig dataclass."""

    def test_valid_creation(self) -> None:
        """Test creating a valid persona config."""
        config = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        assert config.name == "motoko"
        assert config.wake_word_model == "hey_motoko"
        assert config.voice == "nova"
        assert config.display_name == "Major Kusanagi"
        assert config.prompt_path == "prompts/personas/motoko.md"
        assert config.traits == {}

    def test_valid_creation_with_traits(self) -> None:
        """Test creating a persona config with traits."""
        traits = {"analytical": True, "philosophical": True}
        config = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
            traits=traits,
        )
        assert config.traits == traits

    def test_all_valid_voices(self) -> None:
        """Test that all valid OpenAI voices are accepted."""
        for voice in VALID_VOICES:
            config = PersonaConfig(
                name="test",
                wake_word_model="hey_test",
                voice=voice,
                display_name="Test",
                prompt_path="prompts/test.md",
            )
            assert config.voice == voice

    def test_invalid_voice_raises_error(self) -> None:
        """Test that invalid voice values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid voice 'invalid_voice'"):
            PersonaConfig(
                name="test",
                wake_word_model="hey_test",
                voice="invalid_voice",
                display_name="Test",
                prompt_path="prompts/test.md",
            )

    def test_empty_name_raises_error(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            PersonaConfig(
                name="",
                wake_word_model="hey_test",
                voice="nova",
                display_name="Test",
                prompt_path="prompts/test.md",
            )

    def test_whitespace_name_raises_error(self) -> None:
        """Test that whitespace-only name raises ValueError."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            PersonaConfig(
                name="   ",
                wake_word_model="hey_test",
                voice="nova",
                display_name="Test",
                prompt_path="prompts/test.md",
            )

    def test_empty_wake_word_model_raises_error(self) -> None:
        """Test that empty wake_word_model raises ValueError."""
        with pytest.raises(ValueError, match="wake_word_model cannot be empty"):
            PersonaConfig(
                name="test",
                wake_word_model="",
                voice="nova",
                display_name="Test",
                prompt_path="prompts/test.md",
            )

    def test_empty_display_name_raises_error(self) -> None:
        """Test that empty display_name raises ValueError."""
        with pytest.raises(ValueError, match="display_name cannot be empty"):
            PersonaConfig(
                name="test",
                wake_word_model="hey_test",
                voice="nova",
                display_name="",
                prompt_path="prompts/test.md",
            )

    def test_empty_prompt_path_raises_error(self) -> None:
        """Test that empty prompt_path raises ValueError."""
        with pytest.raises(ValueError, match="prompt_path cannot be empty"):
            PersonaConfig(
                name="test",
                wake_word_model="hey_test",
                voice="nova",
                display_name="Test",
                prompt_path="",
            )

    def test_equality_by_name(self) -> None:
        """Test that personas are compared by name."""
        config1 = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        config2 = PersonaConfig(
            name="motoko",
            wake_word_model="hey_major",
            voice="echo",
            display_name="The Major",
            prompt_path="prompts/different.md",
        )
        assert config1 == config2

    def test_inequality_by_name(self) -> None:
        """Test that personas with different names are not equal."""
        config1 = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        config2 = PersonaConfig(
            name="batou",
            wake_word_model="hey_batou",
            voice="onyx",
            display_name="Batou",
            prompt_path="prompts/personas/batou.md",
        )
        assert config1 != config2

    def test_hash_by_name(self) -> None:
        """Test that hash is based on name for set/dict operations."""
        config1 = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        config2 = PersonaConfig(
            name="motoko",
            wake_word_model="hey_different",
            voice="echo",
            display_name="Different Name",
            prompt_path="prompts/different.md",
        )
        # Same hash for same name
        assert hash(config1) == hash(config2)
        # Can use in set
        persona_set = {config1}
        assert config2 in persona_set


class TestPersonaConfigFromDict:
    """Tests for PersonaConfig.from_dict factory method."""

    def test_from_dict_with_all_fields(self) -> None:
        """Test creating persona from complete dictionary."""
        data = {
            "name": "motoko",
            "voice": "nova",
            "display_name": "Major Kusanagi",
            "prompt_path": "prompts/personas/motoko.md",
            "traits": {"analytical": True},
        }
        config = PersonaConfig.from_dict("hey_motoko", data)
        assert config.name == "motoko"
        assert config.wake_word_model == "hey_motoko"
        assert config.voice == "nova"
        assert config.display_name == "Major Kusanagi"
        assert config.prompt_path == "prompts/personas/motoko.md"
        assert config.traits == {"analytical": True}

    def test_from_dict_with_defaults(self) -> None:
        """Test creating persona with default values."""
        data = {"voice": "nova"}
        config = PersonaConfig.from_dict("hey_motoko", data)
        # Name derived from wake word model (strip "hey_" prefix)
        assert config.name == "motoko"
        assert config.wake_word_model == "hey_motoko"
        assert config.voice == "nova"
        # Display name defaults to title case of wake word model
        assert config.display_name == "Hey_Motoko"
        # Prompt path defaults based on name
        assert config.prompt_path == "prompts/personas/motoko.md"
        assert config.traits == {}

    def test_from_dict_voice_default(self) -> None:
        """Test that missing voice defaults to 'alloy'."""
        data = {"name": "test", "display_name": "Test"}
        config = PersonaConfig.from_dict("hey_test", data)
        assert config.voice == "alloy"

    def test_from_dict_empty_data(self) -> None:
        """Test creating persona from empty dictionary uses all defaults."""
        config = PersonaConfig.from_dict("hey_motoko", {})
        assert config.name == "motoko"
        assert config.voice == "alloy"
        assert config.wake_word_model == "hey_motoko"

    def test_from_dict_invalid_voice_raises_error(self) -> None:
        """Test that invalid voice in dict raises ValueError."""
        data = {"voice": "bad_voice"}
        with pytest.raises(ValueError, match="Invalid voice"):
            PersonaConfig.from_dict("hey_test", data)


class TestPersonaManager:
    """Tests for PersonaManager class."""

    def test_empty_manager(self) -> None:
        """Test creating an empty persona manager."""
        manager = PersonaManager()
        assert manager.personas == {}
        assert manager.current_persona is None
        assert manager.default_persona_key == ""

    def test_register_persona(self) -> None:
        """Test registering a persona."""
        manager = PersonaManager()
        config = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        manager.register_persona(config)
        assert "hey_motoko" in manager.personas
        assert manager.personas["hey_motoko"] == config

    def test_register_multiple_personas(self) -> None:
        """Test registering multiple personas."""
        manager = PersonaManager()
        motoko = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        batou = PersonaConfig(
            name="batou",
            wake_word_model="hey_batou",
            voice="onyx",
            display_name="Batou",
            prompt_path="prompts/personas/batou.md",
        )
        manager.register_persona(motoko)
        manager.register_persona(batou)
        assert len(manager.personas) == 2
        assert manager.get_persona("hey_motoko") == motoko
        assert manager.get_persona("hey_batou") == batou

    def test_get_persona_exists(self) -> None:
        """Test getting an existing persona."""
        manager = PersonaManager()
        config = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        manager.register_persona(config)
        result = manager.get_persona("hey_motoko")
        assert result == config

    def test_get_persona_not_exists(self) -> None:
        """Test getting a non-existent persona returns None."""
        manager = PersonaManager()
        result = manager.get_persona("hey_unknown")
        assert result is None

    def test_set_default_success(self) -> None:
        """Test setting the default persona."""
        manager = PersonaManager()
        config = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        manager.register_persona(config)
        result = manager.set_default("hey_motoko")
        assert result is True
        assert manager.default_persona_key == "hey_motoko"
        assert manager.current_persona == config

    def test_set_default_not_found(self) -> None:
        """Test setting default for non-existent persona returns False."""
        manager = PersonaManager()
        result = manager.set_default("hey_unknown")
        assert result is False
        assert manager.default_persona_key == ""
        assert manager.current_persona is None

    def test_set_default_does_not_override_current(self) -> None:
        """Test that set_default doesn't override existing current_persona."""
        manager = PersonaManager()
        motoko = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        batou = PersonaConfig(
            name="batou",
            wake_word_model="hey_batou",
            voice="onyx",
            display_name="Batou",
            prompt_path="prompts/personas/batou.md",
        )
        manager.register_persona(motoko)
        manager.register_persona(batou)

        # Set motoko as default (sets current_persona)
        manager.set_default("hey_motoko")
        assert manager.current_persona == motoko

        # Setting batou as default should NOT change current_persona
        manager.set_default("hey_batou")
        assert manager.default_persona_key == "hey_batou"
        assert manager.current_persona == motoko  # Still motoko

    def test_get_default(self) -> None:
        """Test getting the default persona."""
        manager = PersonaManager()
        config = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        manager.register_persona(config)
        manager.set_default("hey_motoko")
        assert manager.get_default() == config

    def test_get_default_when_not_set(self) -> None:
        """Test getting default when none is set returns None."""
        manager = PersonaManager()
        assert manager.get_default() is None


class TestPersonaManagerFromConfig:
    """Tests for PersonaManager.from_config factory method."""

    def test_from_config_with_personas(self) -> None:
        """Test creating manager from config with personas."""
        config = {
            "personas": {
                "hey_motoko": {
                    "name": "motoko",
                    "voice": "nova",
                    "display_name": "Major Kusanagi",
                    "prompt_path": "prompts/personas/motoko.md",
                },
                "hey_batou": {
                    "name": "batou",
                    "voice": "onyx",
                    "display_name": "Batou",
                    "prompt_path": "prompts/personas/batou.md",
                },
            },
            "default_persona": "hey_motoko",
        }
        manager = PersonaManager.from_config(config)
        assert len(manager.personas) == 2
        assert manager.default_persona_key == "hey_motoko"
        assert manager.current_persona is not None
        assert manager.current_persona.name == "motoko"
        assert manager.current_persona.voice == "nova"

    def test_from_config_uses_first_as_default(self) -> None:
        """Test that first persona is used as default when not specified."""
        config = {
            "personas": {
                "hey_motoko": {
                    "name": "motoko",
                    "voice": "nova",
                    "display_name": "Major Kusanagi",
                    "prompt_path": "prompts/personas/motoko.md",
                },
            },
        }
        manager = PersonaManager.from_config(config)
        assert manager.current_persona is not None
        assert manager.current_persona.name == "motoko"

    def test_from_config_empty(self) -> None:
        """Test creating manager from empty config."""
        manager = PersonaManager.from_config({})
        assert len(manager.personas) == 0
        assert manager.current_persona is None

    def test_from_config_no_personas_key(self) -> None:
        """Test creating manager when 'personas' key is missing."""
        config = {"default_persona": "hey_motoko"}
        manager = PersonaManager.from_config(config)
        assert len(manager.personas) == 0
        assert manager.current_persona is None

    def test_from_config_invalid_default(self) -> None:
        """Test that invalid default_persona doesn't crash and falls back."""
        config = {
            "personas": {
                "hey_motoko": {
                    "name": "motoko",
                    "voice": "nova",
                    "display_name": "Major Kusanagi",
                    "prompt_path": "prompts/personas/motoko.md",
                },
            },
            "default_persona": "hey_unknown",  # Not in personas
        }
        manager = PersonaManager.from_config(config)
        # Should not crash - invalid default is ignored, no fallback to first
        assert len(manager.personas) == 1
        # The set_default fails, current_persona remains None
        assert manager.current_persona is None


class TestValidVoicesConstant:
    """Tests for VALID_VOICES constant."""

    def test_valid_voices_is_frozenset(self) -> None:
        """Test that VALID_VOICES is immutable."""
        assert isinstance(VALID_VOICES, frozenset)

    def test_valid_voices_contains_expected(self) -> None:
        """Test that all expected voices are in VALID_VOICES."""
        expected = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        assert VALID_VOICES == expected

    def test_valid_voices_count(self) -> None:
        """Test that there are exactly 6 valid voices."""
        assert len(VALID_VOICES) == 6
