"""Error recovery manager for voice pipeline.

Implements retry logic with exponential backoff and graceful degradation
strategies when components fail. Each failure type has configurable
recovery behavior.

Recovery strategies:
- RETRY: Attempt the operation again with backoff
- RESTART: Restart the affected component
- FALLBACK: Switch to degraded mode
- ABORT: Stop and report failure
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

import structlog

from .errors import VoicePipelineError

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class RecoveryAction(Enum):
    """Action to take when recovery fails."""

    RETRY = "retry"  # Retry the operation
    RESTART = "restart"  # Restart the component
    FALLBACK = "fallback"  # Switch to degraded mode
    ABORT = "abort"  # Give up


@dataclass
class RecoveryStrategy:
    """Configuration for recovering from a specific failure type."""

    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 30.0
    fallback_action: RecoveryAction = RecoveryAction.ABORT

    # Track retry state
    _current_retries: int = field(default=0, repr=False)
    _current_delay: float = field(default=0.0, repr=False)
    _last_failure_time: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        self._current_delay = self.initial_delay_seconds

    def reset(self) -> None:
        """Reset retry state after successful recovery or timeout."""
        self._current_retries = 0
        self._current_delay = self.initial_delay_seconds
        self._last_failure_time = 0.0

    def should_retry(self) -> bool:
        """Check if we should attempt another retry."""
        return self._current_retries < self.max_retries

    def get_next_delay(self) -> float:
        """Get delay before next retry, applying backoff."""
        delay = self._current_delay
        self._current_delay = min(
            self._current_delay * self.backoff_factor,
            self.max_delay_seconds,
        )
        return delay

    def record_failure(self) -> RecoveryAction:
        """Record a failure and return the recommended action.

        Returns:
            RETRY if retries remaining, else fallback_action
        """
        self._current_retries += 1
        self._last_failure_time = time.time()

        if self.should_retry():
            return RecoveryAction.RETRY
        return self.fallback_action


@dataclass
class DegradedModeConfig:
    """Configuration for graceful degradation when components fail."""

    # Wake word failure: switch to always-listening mode
    skip_wake_word_on_failure: bool = True

    # VAD failure: use energy-based fallback (already in VoiceActivityDetector)
    use_energy_vad_fallback: bool = True

    # TTS failure: log response text instead of speaking
    log_response_on_tts_failure: bool = True

    # STT failure: skip transcription and restart listening
    skip_stt_on_failure: bool = True


@dataclass
class PipelineRecoveryManager:
    """Manages recovery strategies for voice pipeline failures.

    Coordinates retry logic, backoff timing, and degraded mode transitions
    for different failure types.
    """

    config: DegradedModeConfig = field(default_factory=DegradedModeConfig)

    # Recovery strategies per failure type
    strategies: dict[str, RecoveryStrategy] = field(default_factory=dict)

    # Currently active degraded modes
    _degraded_modes: set[str] = field(default_factory=set, repr=False)

    # Callbacks for degraded mode notifications
    on_degraded_mode: Callable[[str, bool], None] | None = None

    def __post_init__(self) -> None:
        """Initialize default recovery strategies."""
        # Default strategies for each failure type
        defaults = {
            "audio_init": RecoveryStrategy(
                max_retries=3,
                initial_delay_seconds=1.0,
                backoff_factor=2.0,
                fallback_action=RecoveryAction.ABORT,
            ),
            "audio_stream": RecoveryStrategy(
                max_retries=2,
                initial_delay_seconds=0.5,
                backoff_factor=2.0,
                fallback_action=RecoveryAction.RESTART,
            ),
            "wake_word": RecoveryStrategy(
                max_retries=1,
                initial_delay_seconds=1.0,
                fallback_action=RecoveryAction.FALLBACK,
            ),
            "vad": RecoveryStrategy(
                max_retries=1,
                initial_delay_seconds=0.5,
                fallback_action=RecoveryAction.FALLBACK,
            ),
            "stt": RecoveryStrategy(
                max_retries=2,
                initial_delay_seconds=1.0,
                backoff_factor=1.5,
                fallback_action=RecoveryAction.FALLBACK,
            ),
            "tts": RecoveryStrategy(
                max_retries=2,
                initial_delay_seconds=1.0,
                backoff_factor=1.5,
                fallback_action=RecoveryAction.FALLBACK,
            ),
            "agent": RecoveryStrategy(
                max_retries=2,
                initial_delay_seconds=2.0,
                backoff_factor=2.0,
                fallback_action=RecoveryAction.ABORT,
            ),
            "realtime_connection": RecoveryStrategy(
                max_retries=3,
                initial_delay_seconds=1.0,
                backoff_factor=2.0,
                fallback_action=RecoveryAction.ABORT,
            ),
        }

        # Merge with any user-provided strategies
        for key, strategy in defaults.items():
            if key not in self.strategies:
                self.strategies[key] = strategy

    @property
    def degraded_modes(self) -> set[str]:
        """Get currently active degraded modes."""
        return self._degraded_modes.copy()

    def is_degraded(self, component: str) -> bool:
        """Check if a component is in degraded mode."""
        return component in self._degraded_modes

    def enter_degraded_mode(self, component: str, reason: str = "") -> None:
        """Enter degraded mode for a component.

        Args:
            component: Component name (wake_word, vad, stt, tts)
            reason: Optional reason for degradation
        """
        if component not in self._degraded_modes:
            self._degraded_modes.add(component)
            logger.warning(
                "degraded_mode_entered",
                component=component,
                reason=reason,
                active_degraded_modes=list(self._degraded_modes),
            )

            if self.on_degraded_mode:
                self.on_degraded_mode(component, True)

    def exit_degraded_mode(self, component: str) -> None:
        """Exit degraded mode for a component."""
        if component in self._degraded_modes:
            self._degraded_modes.discard(component)
            logger.info(
                "degraded_mode_exited",
                component=component,
                active_degraded_modes=list(self._degraded_modes),
            )

            if self.on_degraded_mode:
                self.on_degraded_mode(component, False)

    def reset_all(self) -> None:
        """Reset all recovery strategies and exit all degraded modes."""
        for strategy in self.strategies.values():
            strategy.reset()

        for component in list(self._degraded_modes):
            self.exit_degraded_mode(component)

    async def attempt_recovery(
        self,
        failure_type: str,
        operation: Callable[[], Coroutine[Any, Any, T]],
        error: Exception | None = None,
    ) -> tuple[bool, T | None, RecoveryAction]:
        """Attempt to recover from a failure using the configured strategy.

        This method:
        1. Records the failure in the strategy
        2. Determines if we should retry
        3. If retrying, waits with backoff and calls the operation
        4. Returns success/failure, result, and final action taken

        Args:
            failure_type: Key into strategies dict
            operation: Async callable to retry
            error: The exception that caused the failure

        Returns:
            Tuple of (success, result, action_taken)
        """
        strategy = self.strategies.get(failure_type)
        if not strategy:
            logger.error("unknown_failure_type", failure_type=failure_type)
            return False, None, RecoveryAction.ABORT

        # Record failure and get recommended action
        action = strategy.record_failure()

        logger.info(
            "recovery_attempt",
            failure_type=failure_type,
            action=action.value,
            retry_count=strategy._current_retries,
            max_retries=strategy.max_retries,
            error=str(error) if error else None,
        )

        if action == RecoveryAction.RETRY:
            # Wait with backoff
            delay = strategy.get_next_delay()
            logger.debug(
                "recovery_backoff",
                failure_type=failure_type,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

            # Attempt retry
            try:
                result = await operation()
                strategy.reset()  # Success - reset retry state
                logger.info(
                    "recovery_succeeded",
                    failure_type=failure_type,
                    after_retries=strategy._current_retries,
                )
                return True, result, RecoveryAction.RETRY
            except Exception as retry_error:
                logger.warning(
                    "recovery_retry_failed",
                    failure_type=failure_type,
                    error=str(retry_error),
                )
                # Recursive retry until exhausted
                return await self.attempt_recovery(failure_type, operation, retry_error)

        elif action == RecoveryAction.FALLBACK:
            # Enter degraded mode
            self.enter_degraded_mode(
                failure_type,
                reason=str(error) if error else "Unknown failure",
            )
            return False, None, RecoveryAction.FALLBACK

        elif action == RecoveryAction.RESTART:
            # Signal that component should be restarted
            logger.info("recovery_restart_requested", failure_type=failure_type)
            return False, None, RecoveryAction.RESTART

        else:  # ABORT
            logger.error(
                "recovery_aborted",
                failure_type=failure_type,
                error=str(error) if error else None,
            )
            return False, None, RecoveryAction.ABORT

    async def with_recovery(
        self,
        failure_type: str,
        operation: Callable[[], Coroutine[Any, Any, T]],
        fallback_value: T | None = None,
    ) -> T | None:
        """Execute an operation with automatic recovery on failure.

        This is a convenience wrapper around attempt_recovery that
        handles the retry loop and returns either the result or
        a fallback value.

        Args:
            failure_type: Key into strategies dict
            operation: Async callable to execute
            fallback_value: Value to return if recovery fails

        Returns:
            Operation result or fallback_value
        """
        try:
            return await operation()
        except Exception as e:
            success, result, action = await self.attempt_recovery(
                failure_type, operation, e
            )

            if success:
                return result

            if action == RecoveryAction.FALLBACK:
                # Return fallback value when in degraded mode
                return fallback_value

            # For ABORT or RESTART, re-raise the exception
            raise VoicePipelineError(
                f"Recovery failed for {failure_type}: {e}",
                recoverable=action == RecoveryAction.RESTART,
            ) from e

    def get_status_report(self) -> dict[str, Any]:
        """Get a status report of recovery state.

        Returns:
            Dict with degraded modes and retry states
        """
        return {
            "degraded_modes": list(self._degraded_modes),
            "strategies": {
                name: {
                    "current_retries": s._current_retries,
                    "max_retries": s.max_retries,
                    "last_failure": s._last_failure_time,
                }
                for name, s in self.strategies.items()
            },
        }
