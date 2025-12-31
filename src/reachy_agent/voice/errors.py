"""Exception hierarchy for Reachy voice pipeline.

Provides structured error types for:
- Audio device failures (initialization, disconnection)
- STT/TTS API errors
- State machine violations
- Recovery coordination

These exceptions enable graceful degradation and targeted recovery
strategies in the voice pipeline.
"""

from __future__ import annotations


class VoicePipelineError(Exception):
    """Base exception for all voice pipeline errors.

    All voice pipeline exceptions inherit from this class,
    allowing for catch-all error handling when needed.
    """

    def __init__(self, message: str, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable


# ─────────────────────────────────────────────────────────────────────────────
# Audio Device Errors
# ─────────────────────────────────────────────────────────────────────────────


class AudioDeviceError(VoicePipelineError):
    """Base class for audio device-related errors.

    Raised when there are issues with PyAudio, audio hardware,
    or stream management.
    """

    def __init__(
        self,
        message: str,
        device_index: int | None = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message, recoverable)
        self.device_index = device_index


class AudioDeviceNotFoundError(AudioDeviceError):
    """Raised when a specified audio device cannot be found.

    This typically occurs when:
    - The configured device index doesn't exist
    - USB audio device was unplugged
    - Device permissions are incorrect
    """

    def __init__(self, device_index: int | None, for_input: bool = True) -> None:
        device_type = "input" if for_input else "output"
        message = f"Audio {device_type} device not found: index={device_index}"
        super().__init__(message, device_index=device_index, recoverable=True)
        self.for_input = for_input


class AudioStreamDisconnectedError(AudioDeviceError):
    """Raised when an active audio stream unexpectedly disconnects.

    This can happen when:
    - USB audio device is unplugged during operation
    - Hardware malfunction occurs
    - Driver issues arise mid-stream
    """

    def __init__(
        self,
        device_index: int | None = None,
        stream_type: str = "input",
    ) -> None:
        message = f"Audio {stream_type} stream disconnected: device={device_index}"
        super().__init__(message, device_index=device_index, recoverable=True)
        self.stream_type = stream_type


class AudioInitializationError(AudioDeviceError):
    """Raised when audio system initialization fails.

    This includes:
    - PyAudio initialization failures
    - Stream opening failures after retries exhausted
    - Invalid configuration parameters
    """

    def __init__(
        self,
        message: str,
        device_index: int | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, device_index=device_index, recoverable=False)
        self.original_error = original_error


# ─────────────────────────────────────────────────────────────────────────────
# State Machine Errors
# ─────────────────────────────────────────────────────────────────────────────


class StateTransitionError(VoicePipelineError):
    """Raised when an invalid state transition is attempted.

    The voice pipeline uses a state machine to manage its lifecycle.
    This error indicates a programming error or race condition.
    """

    def __init__(self, from_state: str, to_state: str) -> None:
        message = f"Invalid state transition: {from_state} → {to_state}"
        super().__init__(message, recoverable=False)
        self.from_state = from_state
        self.to_state = to_state


class StateTimeoutError(VoicePipelineError):
    """Raised when a state times out.

    Certain states have maximum durations to prevent stuck pipelines.
    When a timeout occurs, the pipeline should transition to ERROR state.
    """

    def __init__(self, state: str, timeout_seconds: float) -> None:
        message = f"State '{state}' timed out after {timeout_seconds:.1f}s"
        super().__init__(message, recoverable=True)
        self.state = state
        self.timeout_seconds = timeout_seconds


# ─────────────────────────────────────────────────────────────────────────────
# API Errors (STT/TTS)
# ─────────────────────────────────────────────────────────────────────────────


class STTError(VoicePipelineError):
    """Raised when speech-to-text fails.

    This can be due to:
    - Network issues with OpenAI API
    - Rate limiting
    - Invalid audio format
    - API quota exceeded
    """

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, recoverable=True)
        self.original_error = original_error


class TTSError(VoicePipelineError):
    """Raised when text-to-speech fails.

    This can be due to:
    - Network issues with OpenAI API
    - Rate limiting
    - Invalid text input
    - API quota exceeded
    """

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, recoverable=True)
        self.original_error = original_error


# ─────────────────────────────────────────────────────────────────────────────
# Component Errors
# ─────────────────────────────────────────────────────────────────────────────


class WakeWordError(VoicePipelineError):
    """Raised when wake word detection fails.

    If wake word detection is unavailable, the pipeline can
    fall back to direct speech mode (always listening).
    """

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, recoverable=True)
        self.original_error = original_error


class VADError(VoicePipelineError):
    """Raised when voice activity detection fails.

    If Silero VAD fails, the pipeline can fall back to
    energy-based speech detection (less accurate but reliable).
    """

    def __init__(
        self,
        message: str,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message, recoverable=True)
        self.original_error = original_error
