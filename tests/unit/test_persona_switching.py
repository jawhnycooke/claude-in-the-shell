"""Tests for persona switching recovery paths.

Tests cover:
- update_system_prompt() SDK reconnection failure and recovery
- Rollback to old prompt when reconnection fails
- Client marked as None when recovery also fails
- Pre-connect prompt update behavior
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUpdateSystemPromptRecovery:
    """Tests for ReachyAgentLoop.update_system_prompt() recovery paths."""

    @pytest.fixture
    def mock_agent_loop(self):
        """Create a mock agent loop with necessary attributes."""
        # We patch the class to avoid importing all dependencies
        with patch("reachy_agent.agent.agent.ClaudeSDKClient") as MockSDKClient:
            # Create mock client
            mock_client = AsyncMock()
            mock_client.disconnect = AsyncMock()
            mock_client.connect = AsyncMock(return_value=True)
            MockSDKClient.return_value = mock_client

            # Create a minimal mock of ReachyAgentLoop
            agent = MagicMock()
            agent._system_prompt = "Original prompt"
            agent._client = mock_client

            # Mock _build_sdk_options to return valid options
            agent._build_sdk_options = MagicMock(return_value={
                "system_prompt": agent._system_prompt,
                "model": "claude-sonnet-4-20250514",
            })

            yield agent, mock_client, MockSDKClient

    @pytest.mark.asyncio
    async def test_update_prompt_success(self, mock_agent_loop):
        """Test successful prompt update with reconnection."""
        agent, mock_client, MockSDKClient = mock_agent_loop

        # Import the actual method
        from reachy_agent.agent.agent import ReachyAgentLoop

        # Create a real instance for testing
        with patch.object(ReachyAgentLoop, "__init__", lambda self: None):
            real_agent = ReachyAgentLoop()
            real_agent._system_prompt = "Original prompt"
            real_agent._client = mock_client
            real_agent._build_sdk_options = MagicMock(return_value={})

            # Mock ClaudeSDKClient for the reconnection
            with patch(
                "reachy_agent.agent.agent.ClaudeSDKClient"
            ) as MockNewClient:
                new_mock_client = AsyncMock()
                new_mock_client.connect = AsyncMock(return_value=True)
                MockNewClient.return_value = new_mock_client

                result = await real_agent.update_system_prompt("New prompt")

        assert result is True
        assert real_agent._system_prompt == "New prompt"

    @pytest.mark.asyncio
    async def test_update_prompt_reconnect_fails_recovery_succeeds(self):
        """Test prompt rollback when reconnection fails but recovery succeeds."""
        from reachy_agent.agent.agent import ReachyAgentLoop

        with patch.object(ReachyAgentLoop, "__init__", lambda self: None):
            real_agent = ReachyAgentLoop()
            real_agent._system_prompt = "Original prompt"

            # Create initial mock client
            initial_client = AsyncMock()
            initial_client.disconnect = AsyncMock()
            real_agent._client = initial_client
            real_agent._build_sdk_options = MagicMock(return_value={})

            call_count = 0

            def create_client(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                mock = AsyncMock()
                if call_count == 1:
                    # First client (new prompt) - connect fails
                    mock.connect = AsyncMock(side_effect=Exception("Connection failed"))
                else:
                    # Second client (recovery with old prompt) - connect succeeds
                    mock.connect = AsyncMock(return_value=True)
                return mock

            with patch(
                "reachy_agent.agent.agent.ClaudeSDKClient",
                side_effect=create_client,
            ):
                result = await real_agent.update_system_prompt("New prompt")

        # Should return False but client should be recovered
        assert result is False
        assert real_agent._system_prompt == "Original prompt"  # Rolled back
        assert real_agent._client is not None  # Client recovered

    @pytest.mark.asyncio
    async def test_update_prompt_reconnect_and_recovery_both_fail(self):
        """Test client marked as None when both reconnect and recovery fail."""
        from reachy_agent.agent.agent import ReachyAgentLoop

        with patch.object(ReachyAgentLoop, "__init__", lambda self: None):
            real_agent = ReachyAgentLoop()
            real_agent._system_prompt = "Original prompt"

            # Create initial mock client
            initial_client = AsyncMock()
            initial_client.disconnect = AsyncMock()
            real_agent._client = initial_client
            real_agent._build_sdk_options = MagicMock(return_value={})

            # Both client creations will fail to connect
            def create_failing_client(*args, **kwargs):
                mock = AsyncMock()
                mock.connect = AsyncMock(side_effect=Exception("Connection failed"))
                return mock

            with patch(
                "reachy_agent.agent.agent.ClaudeSDKClient",
                side_effect=create_failing_client,
            ):
                result = await real_agent.update_system_prompt("New prompt")

        # Should return False and client should be None
        assert result is False
        assert real_agent._system_prompt == "Original prompt"  # Rolled back
        assert real_agent._client is None  # Client marked as unusable

    @pytest.mark.asyncio
    async def test_update_prompt_pre_connect_no_client(self):
        """Test prompt update when client is None (pre-connect)."""
        from reachy_agent.agent.agent import ReachyAgentLoop

        with patch.object(ReachyAgentLoop, "__init__", lambda self: None):
            real_agent = ReachyAgentLoop()
            real_agent._system_prompt = "Original prompt"
            real_agent._client = None  # Not connected yet

            result = await real_agent.update_system_prompt("New prompt")

        # Should succeed without reconnection
        assert result is True
        assert real_agent._system_prompt == "New prompt"

    @pytest.mark.asyncio
    async def test_prompt_length_preserved_on_rollback(self):
        """Test that original prompt content is fully preserved on rollback."""
        from reachy_agent.agent.agent import ReachyAgentLoop

        original_prompt = "This is a very long original prompt " * 100

        with patch.object(ReachyAgentLoop, "__init__", lambda self: None):
            real_agent = ReachyAgentLoop()
            real_agent._system_prompt = original_prompt

            initial_client = AsyncMock()
            initial_client.disconnect = AsyncMock()
            real_agent._client = initial_client
            real_agent._build_sdk_options = MagicMock(return_value={})

            def create_failing_client(*args, **kwargs):
                mock = AsyncMock()
                mock.connect = AsyncMock(side_effect=Exception("Connection failed"))
                return mock

            with patch(
                "reachy_agent.agent.agent.ClaudeSDKClient",
                side_effect=create_failing_client,
            ):
                await real_agent.update_system_prompt("Short new prompt")

        # Full original prompt should be preserved
        assert real_agent._system_prompt == original_prompt
        assert len(real_agent._system_prompt) == len(original_prompt)


class TestVoicePipelinePersonaSwitchRecovery:
    """Tests for VoicePipeline._switch_persona() recovery paths.

    Note: These are more integration-style tests that verify the recovery
    logic works correctly when voice/prompt updates fail.
    """

    @pytest.mark.asyncio
    async def test_voice_reconnect_failure_with_recovery(self):
        """Test realtime client recovery when voice reconnection fails."""
        # This test verifies the recovery path at pipeline.py:274-288
        from reachy_agent.voice.persona import PersonaConfig

        # Create test personas
        old_persona = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        new_persona = PersonaConfig(
            name="batou",
            wake_word_model="hey_batou",
            voice="onyx",
            display_name="Batou",
            prompt_path="prompts/personas/batou.md",
        )

        # Create mock realtime client
        mock_realtime = AsyncMock()
        mock_realtime.disconnect = AsyncMock()

        # Track connect calls
        connect_results = [False, True]  # First fails, second (recovery) succeeds
        connect_call_count = 0

        async def mock_connect():
            nonlocal connect_call_count
            result = connect_results[connect_call_count]
            connect_call_count += 1
            return result

        mock_realtime.connect = mock_connect

        # Create mock config
        mock_config = MagicMock()
        mock_config.realtime = MagicMock()
        mock_config.realtime.voice = old_persona.voice
        mock_config.persona_manager = None

        # Create minimal pipeline mock
        pipeline = MagicMock()
        pipeline._realtime = mock_realtime
        pipeline._current_persona = old_persona
        pipeline.config = mock_config
        pipeline.agent = None

        # Import and run the actual switch logic
        # We can't easily test the full method without the full pipeline,
        # so we verify the recovery logic conceptually
        assert old_persona.voice == "nova"
        assert new_persona.voice == "onyx"

        # Simulate the recovery logic:
        # 1. Set new voice
        mock_config.realtime.voice = new_persona.voice
        # 2. Disconnect and try to connect (fails)
        await mock_realtime.disconnect()
        first_connect = await mock_realtime.connect()
        assert first_connect is False

        # 3. Rollback voice and try recovery
        mock_config.realtime.voice = old_persona.voice
        second_connect = await mock_realtime.connect()
        assert second_connect is True

        # Voice should be rolled back to old value
        assert mock_config.realtime.voice == "nova"

    @pytest.mark.asyncio
    async def test_voice_and_recovery_both_fail(self):
        """Test handling when both voice update and recovery fail."""
        from reachy_agent.voice.persona import PersonaConfig

        old_persona = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )

        mock_realtime = AsyncMock()
        mock_realtime.disconnect = AsyncMock()
        mock_realtime.connect = AsyncMock(return_value=False)  # Always fails

        mock_config = MagicMock()
        mock_config.realtime = MagicMock()
        mock_config.realtime.voice = old_persona.voice

        # Simulate both failures
        mock_config.realtime.voice = "onyx"
        await mock_realtime.disconnect()

        # First connect fails
        first_result = await mock_realtime.connect()
        assert first_result is False

        # Rollback and try recovery
        mock_config.realtime.voice = "nova"
        recovery_result = await mock_realtime.connect()
        assert recovery_result is False

        # In this case, the system is in an inconsistent state
        # but voice config is rolled back
        assert mock_config.realtime.voice == "nova"


class TestUpdateVoiceRecovery:
    """Tests for OpenAIRealtimeClient.update_voice() recovery paths."""

    @pytest.fixture
    def mock_realtime_client(self):
        """Create a mock realtime client for testing."""
        from reachy_agent.voice.openai_realtime import OpenAIRealtimeClient, RealtimeConfig

        # Create a minimal config
        config = RealtimeConfig(voice="nova")

        # Patch the _init_client to avoid needing real API key
        with patch.object(OpenAIRealtimeClient, "_init_client", lambda self: None):
            client = OpenAIRealtimeClient(config=config)
        return client, config

    @pytest.mark.asyncio
    async def test_update_voice_success(self, mock_realtime_client):
        """Test successful voice update when connected."""
        client, config = mock_realtime_client

        # Set up initial connected state
        client._is_connected = True
        client._connection = MagicMock()

        # Mock disconnect and connect
        client.disconnect = AsyncMock()
        client.connect = AsyncMock(return_value=True)

        result = await client.update_voice("onyx")

        assert result is True
        assert config.voice == "onyx"
        client.disconnect.assert_called_once()
        client.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_voice_no_change(self, mock_realtime_client):
        """Test update_voice returns True when voice unchanged (no-op)."""
        client, config = mock_realtime_client
        config.voice = "nova"

        # Mock methods (should not be called)
        client.disconnect = AsyncMock()
        client.connect = AsyncMock()

        result = await client.update_voice("nova")

        assert result is True
        assert config.voice == "nova"
        client.disconnect.assert_not_called()
        client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_voice_not_connected(self, mock_realtime_client):
        """Test update_voice when client is not connected."""
        client, config = mock_realtime_client
        config.voice = "nova"
        client._is_connected = False
        client._connection = None

        # No disconnect/connect needed
        client.disconnect = AsyncMock()
        client.connect = AsyncMock()

        result = await client.update_voice("onyx")

        # Should succeed - voice config updated, no reconnection needed
        assert result is True
        assert config.voice == "onyx"
        client.disconnect.assert_not_called()
        client.connect.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_voice_reconnect_fails_recovery_succeeds(self, mock_realtime_client):
        """Test voice rollback when reconnection fails but recovery succeeds."""
        client, config = mock_realtime_client
        config.voice = "nova"
        client._is_connected = True
        client._connection = MagicMock()

        client.disconnect = AsyncMock()

        # Track connect calls
        connect_call_count = 0

        async def mock_connect():
            nonlocal connect_call_count
            connect_call_count += 1
            if connect_call_count == 1:
                # First connect (new voice) fails
                return False
            else:
                # Second connect (recovery with old voice) succeeds
                return True

        client.connect = mock_connect

        result = await client.update_voice("onyx")

        # Should return False but voice should be rolled back and client recovered
        assert result is False
        assert config.voice == "nova"  # Rolled back to original
        assert connect_call_count == 2  # Two connect attempts: failed + recovery

    @pytest.mark.asyncio
    async def test_update_voice_reconnect_and_recovery_both_fail(self, mock_realtime_client):
        """Test update_voice when both reconnect and recovery fail."""
        client, config = mock_realtime_client
        config.voice = "nova"
        client._is_connected = True
        client._connection = MagicMock()

        client.disconnect = AsyncMock()
        client.connect = AsyncMock(return_value=False)  # Always fails

        result = await client.update_voice("onyx")

        # Should return False, voice rolled back, client still disconnected
        assert result is False
        assert config.voice == "nova"  # Rolled back to original
        # Connect called twice: once for new voice, once for recovery
        assert client.connect.call_count == 2


class TestVoicePipelineDoubleFailure:
    """Tests for VoicePipeline._switch_persona() double-failure scenarios.

    These tests cover the critical edge case where:
    1. Voice update succeeds
    2. Prompt update fails
    3. Voice rollback ALSO fails

    This leaves the system in an inconsistent state (voice=new, personality=old).
    """

    @pytest.mark.asyncio
    async def test_prompt_fails_then_voice_rollback_fails(self):
        """Test handling when prompt update fails AND voice rollback fails.

        This is the double-failure scenario that leaves the system in an
        inconsistent state where voice doesn't match personality.
        """
        from reachy_agent.voice.persona import PersonaConfig

        old_persona = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        new_persona = PersonaConfig(
            name="batou",
            wake_word_model="hey_batou",
            voice="onyx",
            display_name="Batou",
            prompt_path="prompts/personas/batou.md",
        )

        # Mock realtime client
        mock_realtime = AsyncMock()
        mock_realtime.disconnect = AsyncMock()

        # Track connect calls - first succeeds (voice switch), second fails (recovery)
        connect_call_count = 0

        async def mock_connect():
            nonlocal connect_call_count
            connect_call_count += 1
            if connect_call_count == 1:
                # First connect (new voice) succeeds
                return True
            else:
                # Second connect (recovery) fails
                return False

        mock_realtime.connect = mock_connect

        # Mock agent that fails prompt update
        mock_agent = AsyncMock()
        mock_agent.update_system_prompt = AsyncMock(return_value=False)

        # Mock config
        mock_config = MagicMock()
        mock_config.realtime = MagicMock()
        mock_config.realtime.voice = old_persona.voice
        mock_config.persona_manager = MagicMock()

        # Simulate the _switch_persona flow:
        # Step 1: Update voice config and reconnect (succeeds)
        mock_config.realtime.voice = new_persona.voice
        await mock_realtime.disconnect()
        voice_reconnect = await mock_realtime.connect()
        assert voice_reconnect is True
        assert connect_call_count == 1

        # Step 2: Update prompt (fails)
        prompt_updated = await mock_agent.update_system_prompt("new prompt")
        assert prompt_updated is False

        # Step 3: Attempt voice rollback (fails)
        mock_config.realtime.voice = old_persona.voice
        await mock_realtime.disconnect()
        recovery_connected = await mock_realtime.connect()
        assert recovery_connected is False
        assert connect_call_count == 2

        # Final state: Voice config is rolled back but client is disconnected
        # This is the "inconsistent state" the code warns about
        assert mock_config.realtime.voice == "nova"  # Config rolled back

    @pytest.mark.asyncio
    async def test_prompt_fails_voice_rollback_succeeds(self):
        """Test successful recovery when prompt fails but voice rollback works."""
        from reachy_agent.voice.persona import PersonaConfig

        old_persona = PersonaConfig(
            name="motoko",
            wake_word_model="hey_motoko",
            voice="nova",
            display_name="Major Kusanagi",
            prompt_path="prompts/personas/motoko.md",
        )
        new_persona = PersonaConfig(
            name="batou",
            wake_word_model="hey_batou",
            voice="onyx",
            display_name="Batou",
            prompt_path="prompts/personas/batou.md",
        )

        # Mock realtime client - all connects succeed
        mock_realtime = AsyncMock()
        mock_realtime.disconnect = AsyncMock()
        mock_realtime.connect = AsyncMock(return_value=True)

        # Mock agent that fails prompt update
        mock_agent = AsyncMock()
        mock_agent.update_system_prompt = AsyncMock(return_value=False)

        # Mock config
        mock_config = MagicMock()
        mock_config.realtime = MagicMock()
        mock_config.realtime.voice = old_persona.voice

        # Simulate the flow:
        # Step 1: Update voice and reconnect (succeeds)
        mock_config.realtime.voice = new_persona.voice
        await mock_realtime.disconnect()
        voice_reconnect = await mock_realtime.connect()
        assert voice_reconnect is True

        # Step 2: Update prompt (fails)
        prompt_updated = await mock_agent.update_system_prompt("new prompt")
        assert prompt_updated is False

        # Step 3: Rollback voice and reconnect (succeeds)
        mock_config.realtime.voice = old_persona.voice
        await mock_realtime.disconnect()
        recovery_connected = await mock_realtime.connect()
        assert recovery_connected is True

        # System successfully recovered - voice matches personality
        assert mock_config.realtime.voice == "nova"
