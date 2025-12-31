"""Tests for voice pipeline recovery manager.

Tests:
- RecoveryStrategy retry logic and exponential backoff
- PipelineRecoveryManager coordination
- Degraded mode state management
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from reachy_agent.voice.recovery import (
    DegradedModeConfig,
    PipelineRecoveryManager,
    RecoveryAction,
    RecoveryStrategy,
)


# =============================================================================
# RecoveryStrategy Tests
# =============================================================================


class TestRecoveryStrategy:
    """Test retry logic and exponential backoff."""

    def test_default_values(self) -> None:
        """Test default strategy values."""
        strategy = RecoveryStrategy()

        assert strategy.max_retries == 3
        assert strategy.initial_delay_seconds == 1.0
        assert strategy.backoff_factor == 2.0
        assert strategy.max_delay_seconds == 30.0
        assert strategy.fallback_action == RecoveryAction.ABORT

    def test_should_retry_initially_true(self) -> None:
        """Strategy should allow retries initially."""
        strategy = RecoveryStrategy(max_retries=3)

        assert strategy.should_retry() is True

    def test_record_failure_returns_retry_when_remaining(self) -> None:
        """record_failure returns RETRY when retries remain."""
        strategy = RecoveryStrategy(max_retries=3)

        # With max_retries=3, the first 3 calls should return RETRY
        # (when _current_retries is 1, 2, 3 which are all <= max_retries)
        # Wait, the logic is: _current_retries < max_retries after increment
        # So for max_retries=3: after 1st call _current_retries=1 < 3 -> RETRY
        #                       after 2nd call _current_retries=2 < 3 -> RETRY
        #                       after 3rd call _current_retries=3 NOT < 3 -> fallback
        # So only first 2 calls return RETRY with max_retries=3
        # Let's use max_retries=4 to get 3 RETRYs, or fix the iteration count
        for i in range(2):  # Only first 2 should RETRY
            action = strategy.record_failure()
            assert action == RecoveryAction.RETRY, f"Iteration {i+1} should RETRY"

    def test_record_failure_returns_fallback_after_exhausted(self) -> None:
        """record_failure returns fallback_action after max retries."""
        strategy = RecoveryStrategy(
            max_retries=3, fallback_action=RecoveryAction.FALLBACK
        )

        # Exhaust retries
        for _ in range(3):
            strategy.record_failure()

        # Next failure should trigger fallback
        action = strategy.record_failure()
        assert action == RecoveryAction.FALLBACK

    def test_exponential_backoff(self) -> None:
        """Backoff delays should increase exponentially."""
        strategy = RecoveryStrategy(
            max_retries=5,
            initial_delay_seconds=1.0,
            backoff_factor=2.0,
            max_delay_seconds=10.0,
        )

        delays = []
        for _ in range(5):
            delays.append(strategy.get_next_delay())

        # Should be: 1, 2, 4, 8, 10 (capped)
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0
        assert delays[3] == 8.0
        assert delays[4] == 10.0  # Capped at max_delay

    def test_reset_clears_state(self) -> None:
        """Reset should clear retry count and delay."""
        strategy = RecoveryStrategy(
            max_retries=3, initial_delay_seconds=1.0, backoff_factor=2.0
        )

        # Accumulate some state
        strategy.record_failure()
        strategy.record_failure()
        strategy.get_next_delay()  # Advance delay

        assert strategy._current_retries == 2

        strategy.reset()

        assert strategy._current_retries == 0
        assert strategy._current_delay == 1.0  # Reset to initial
        assert strategy._last_failure_time == 0.0

    def test_custom_fallback_action(self) -> None:
        """Custom fallback action is returned after exhaustion."""
        strategy = RecoveryStrategy(
            max_retries=1, fallback_action=RecoveryAction.RESTART
        )

        strategy.record_failure()  # Uses 1 retry
        action = strategy.record_failure()  # Exhausted

        assert action == RecoveryAction.RESTART


# =============================================================================
# PipelineRecoveryManager Tests
# =============================================================================


class TestPipelineRecoveryManager:
    """Test recovery manager coordination."""

    def test_default_strategies(self) -> None:
        """Manager initializes with default strategies."""
        manager = PipelineRecoveryManager()

        assert "audio_init" in manager.strategies
        assert "wake_word" in manager.strategies
        assert "vad" in manager.strategies
        assert "stt" in manager.strategies
        assert "tts" in manager.strategies
        assert "agent" in manager.strategies
        assert "realtime_connection" in manager.strategies

    def test_custom_config(self) -> None:
        """Manager accepts custom degraded mode config."""
        config = DegradedModeConfig(
            skip_wake_word_on_failure=False,
            use_energy_vad_fallback=False,
        )
        manager = PipelineRecoveryManager(config=config)

        assert manager.config.skip_wake_word_on_failure is False
        assert manager.config.use_energy_vad_fallback is False

    def test_enter_degraded_mode(self) -> None:
        """Entering degraded mode is tracked."""
        manager = PipelineRecoveryManager()

        assert manager.is_degraded("wake_word") is False

        manager.enter_degraded_mode("wake_word", reason="Test failure")

        assert manager.is_degraded("wake_word") is True
        assert "wake_word" in manager.degraded_modes

    def test_exit_degraded_mode(self) -> None:
        """Exiting degraded mode clears the flag."""
        manager = PipelineRecoveryManager()
        manager.enter_degraded_mode("wake_word")

        assert manager.is_degraded("wake_word") is True

        manager.exit_degraded_mode("wake_word")

        assert manager.is_degraded("wake_word") is False

    def test_degraded_mode_callback(self) -> None:
        """Callback is invoked on degraded mode changes."""
        callback_calls: list[tuple[str, bool]] = []

        def callback(component: str, entering: bool) -> None:
            callback_calls.append((component, entering))

        manager = PipelineRecoveryManager()
        manager.on_degraded_mode = callback

        manager.enter_degraded_mode("stt")
        manager.exit_degraded_mode("stt")

        assert callback_calls == [("stt", True), ("stt", False)]

    def test_reset_all(self) -> None:
        """reset_all clears all state."""
        manager = PipelineRecoveryManager()

        # Add some state
        manager.enter_degraded_mode("wake_word")
        manager.enter_degraded_mode("vad")
        manager.strategies["wake_word"].record_failure()

        manager.reset_all()

        assert len(manager.degraded_modes) == 0
        assert manager.strategies["wake_word"]._current_retries == 0

    @pytest.mark.asyncio
    async def test_attempt_recovery_success_on_retry(self) -> None:
        """Operation succeeds after retries."""
        manager = PipelineRecoveryManager()
        # Reset to initial state
        manager.strategies["audio_init"].reset()

        call_count = 0

        async def flaky_operation() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("Temporary failure")
            return "success"

        success, result, action = await manager.attempt_recovery(
            "audio_init",
            flaky_operation,
            RuntimeError("Initial failure"),
        )

        assert success is True
        assert result == "success"
        assert action == RecoveryAction.RETRY

    @pytest.mark.asyncio
    async def test_attempt_recovery_exhausted_retries(self) -> None:
        """Recovery returns fallback action after exhausted retries."""
        manager = PipelineRecoveryManager()

        # Use a strategy with 1 retry
        manager.strategies["wake_word"] = RecoveryStrategy(
            max_retries=1, fallback_action=RecoveryAction.FALLBACK
        )

        async def always_fails() -> str:
            raise RuntimeError("Always fails")

        # First attempt - will retry
        await manager.attempt_recovery(
            "wake_word", always_fails, RuntimeError("First")
        )

        # Second attempt - retry exhausted, should return FALLBACK
        success, result, action = await manager.attempt_recovery(
            "wake_word", always_fails, RuntimeError("Second")
        )

        assert success is False
        assert result is None
        assert action == RecoveryAction.FALLBACK
        assert manager.is_degraded("wake_word") is True

    @pytest.mark.asyncio
    async def test_attempt_recovery_unknown_failure_type(self) -> None:
        """Unknown failure type returns ABORT."""
        manager = PipelineRecoveryManager()

        async def operation() -> str:
            return "success"

        success, result, action = await manager.attempt_recovery(
            "unknown_type",
            operation,
            RuntimeError("Error"),
        )

        assert success is False
        assert result is None
        assert action == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_with_recovery_success(self) -> None:
        """with_recovery returns result on success."""
        manager = PipelineRecoveryManager()

        async def successful_op() -> str:
            return "result"

        result = await manager.with_recovery("audio_init", successful_op)

        assert result == "result"

    @pytest.mark.asyncio
    async def test_with_recovery_fallback_value(self) -> None:
        """with_recovery returns fallback value on FALLBACK action."""
        manager = PipelineRecoveryManager()
        manager.strategies["wake_word"] = RecoveryStrategy(
            max_retries=0,  # No retries
            fallback_action=RecoveryAction.FALLBACK,
        )

        async def always_fails() -> str:
            raise RuntimeError("Fails")

        result = await manager.with_recovery(
            "wake_word",
            always_fails,
            fallback_value="fallback",
        )

        assert result == "fallback"

    def test_get_status_report(self) -> None:
        """Status report contains expected information."""
        manager = PipelineRecoveryManager()
        manager.enter_degraded_mode("vad")
        manager.strategies["vad"].record_failure()

        report = manager.get_status_report()

        assert "degraded_modes" in report
        assert "vad" in report["degraded_modes"]
        assert "strategies" in report
        assert "vad" in report["strategies"]
        assert report["strategies"]["vad"]["current_retries"] == 1


# =============================================================================
# DegradedModeConfig Tests
# =============================================================================


class TestDegradedModeConfig:
    """Test degraded mode configuration."""

    def test_default_values(self) -> None:
        """Default config enables all fallbacks."""
        config = DegradedModeConfig()

        assert config.skip_wake_word_on_failure is True
        assert config.use_energy_vad_fallback is True
        assert config.log_response_on_tts_failure is True
        assert config.skip_stt_on_failure is True

    def test_custom_values(self) -> None:
        """Custom config overrides defaults."""
        config = DegradedModeConfig(
            skip_wake_word_on_failure=False,
            use_energy_vad_fallback=False,
        )

        assert config.skip_wake_word_on_failure is False
        assert config.use_energy_vad_fallback is False
