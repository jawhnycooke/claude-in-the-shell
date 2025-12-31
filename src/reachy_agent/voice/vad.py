"""Voice Activity Detection for Reachy voice pipeline.

Uses Silero VAD to detect when the user starts and stops speaking.
Critical for determining when to send audio to STT.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    import torch

logger = structlog.get_logger(__name__)


class SpeechState(Enum):
    """Current speech state."""

    SILENCE = "silence"
    SPEAKING = "speaking"
    END_OF_SPEECH = "end_of_speech"


@dataclass
class VADConfig:
    """VAD configuration settings.

    Energy-based VAD tuning notes (when Silero VAD unavailable):
    - speech_threshold: Lower = more sensitive (catches quiet speech but also noise)
    - silence_threshold_ms: Higher = waits longer to confirm end-of-speech
    - min_recording_duration_s: Guarantees minimum capture time (prevents early cutoff)

    The energy-based fallback is less accurate than Silero, so we err on the side
    of recording longer to ensure OpenAI Whisper gets complete utterances.
    """

    sample_rate: int = 16000
    chunk_duration_ms: int = 30  # Silero VAD works best with 30ms chunks
    speech_threshold: float = 0.30  # Threshold for speech detection (higher = stricter, less noise)
    silence_threshold_ms: int = 1800  # Wait 1.8s of silence before end-of-speech
    min_speech_duration_ms: int = 250  # Minimum speech duration to be valid
    max_speech_duration_s: float = 30.0  # Maximum speech duration before timeout
    min_recording_duration_s: float = 2.5  # Guarantee at least 2.5s recording for better transcription


@dataclass
class VoiceActivityDetector:
    """Detects voice activity and end-of-speech.

    Uses Silero VAD (PyTorch-based) for accurate speech detection.
    Determines when the user has finished speaking.
    """

    config: VADConfig = field(default_factory=VADConfig)
    on_speech_start: Callable[[], None] | None = None
    on_speech_end: Callable[[float], None] | None = None  # Duration in seconds

    _model: torch.nn.Module | None = field(default=None, repr=False)
    _utils: tuple | None = field(default=None, repr=False)
    _state: SpeechState = field(default=SpeechState.SILENCE, repr=False)
    _speech_start_time: float | None = field(default=None, repr=False)
    _last_speech_time: float = field(default=0.0, repr=False)
    _is_running: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Load the Silero VAD model."""
        self._load_model()

    def _load_model(self) -> None:
        """Load Silero VAD model from torch hub."""
        try:
            import torch

            # Load Silero VAD from torch hub
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,  # Use PyTorch for flexibility
            )
            self._model = model
            self._utils = utils
            logger.info("silero_vad_loaded", sample_rate=self.config.sample_rate)

        except Exception as e:
            logger.warning(
                "silero_vad_load_failed",
                error=str(e),
                msg="VAD unavailable, will use simple energy-based detection",
            )
            self._model = None
            self._utils = None

    @property
    def is_available(self) -> bool:
        """Check if VAD is available."""
        return self._model is not None

    @property
    def state(self) -> SpeechState:
        """Get current speech state."""
        return self._state

    @property
    def chunk_samples(self) -> int:
        """Number of samples per chunk for optimal VAD performance."""
        return int(self.config.sample_rate * self.config.chunk_duration_ms / 1000)

    def process_audio(self, audio_data: bytes) -> SpeechState:
        """Process audio chunk and update speech state.

        Args:
            audio_data: Raw PCM audio bytes (int16, 16kHz, mono)

        Returns:
            Current speech state
        """
        current_time = time.time()

        # Convert bytes to numpy array
        samples = np.frombuffer(audio_data, dtype=np.int16)

        # Get speech probability
        if self._model is not None:
            speech_prob = self._get_speech_probability(samples)
        else:
            # Fallback to simple energy-based detection
            speech_prob = self._get_energy_probability(samples)

        is_speech = speech_prob > self.config.speech_threshold

        # State machine
        if self._state == SpeechState.SILENCE:
            if is_speech:
                self._state = SpeechState.SPEAKING
                self._speech_start_time = current_time
                self._last_speech_time = current_time

                logger.debug("speech_started", prob=speech_prob)
                if self.on_speech_start:
                    self.on_speech_start()

        elif self._state == SpeechState.SPEAKING:
            if is_speech:
                self._last_speech_time = current_time
            else:
                # Check if silence duration exceeds threshold
                silence_duration_ms = (current_time - self._last_speech_time) * 1000

                if silence_duration_ms >= self.config.silence_threshold_ms:
                    # Verify minimum speech duration
                    speech_duration = current_time - self._speech_start_time
                    min_duration_s = self.config.min_speech_duration_ms / 1000

                    # Also check minimum recording duration (prevents early cutoff)
                    if speech_duration < self.config.min_recording_duration_s:
                        # Not enough recording time yet, keep listening
                        logger.debug(
                            "recording_too_short",
                            duration=speech_duration,
                            min_required=self.config.min_recording_duration_s,
                        )
                        # Don't change state - keep waiting for more speech
                    elif speech_duration >= min_duration_s:
                        self._state = SpeechState.END_OF_SPEECH
                        logger.debug(
                            "speech_ended",
                            duration=speech_duration,
                            silence_ms=silence_duration_ms,
                        )

                        if self.on_speech_end:
                            self.on_speech_end(speech_duration)
                    else:
                        # Too short, reset to silence
                        self._state = SpeechState.SILENCE
                        logger.debug("speech_too_short", duration=speech_duration)

            # Check for max duration timeout
            if self._speech_start_time:
                elapsed = current_time - self._speech_start_time
                if elapsed >= self.config.max_speech_duration_s:
                    self._state = SpeechState.END_OF_SPEECH
                    logger.info("speech_timeout", duration=elapsed)

                    if self.on_speech_end:
                        self.on_speech_end(elapsed)

        elif self._state == SpeechState.END_OF_SPEECH:
            # Reset back to silence after end-of-speech is processed
            self._state = SpeechState.SILENCE
            self._speech_start_time = None

        return self._state

    def _get_speech_probability(self, samples: np.ndarray) -> float:
        """Get speech probability using Silero VAD."""
        import torch

        # Normalize to float32 in range [-1, 1]
        audio_float = samples.astype(np.float32) / 32768.0

        # Convert to tensor
        audio_tensor = torch.from_numpy(audio_float)

        # Get speech probability
        with torch.no_grad():
            speech_prob = self._model(audio_tensor, self.config.sample_rate).item()

        return speech_prob

    def _get_energy_probability(self, samples: np.ndarray) -> float:
        """Fallback energy-based speech detection.

        Tuned for detecting end-of-speech reliably when Silero VAD
        is unavailable (e.g., no torchaudio installed on Pi).

        Energy detection parameters:
        - RMS divisor: Controls sensitivity (lower = more sensitive)
        - Typical speech RMS: 1000-4000
        - Ambient noise RMS: 100-500
        - Quiet speech RMS: 500-1000

        With divisor=1200 and threshold=0.20:
        - Loud speech (3000 RMS): 2.5 → 1.0 (capped) - detected
        - Normal speech (1500 RMS): 1.25 → 1.0 - detected
        - Quiet speech (600 RMS): 0.5 - detected
        - Ambient noise (300 RMS): 0.25 - borderline (may trigger)
        - Silence (100 RMS): 0.08 - not detected
        """
        if len(samples) == 0:
            return 0.0

        # Calculate RMS energy
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))

        # Balance between sensitivity and noise rejection:
        # - Divisor 1000: Very sensitive, catches quiet speech but also noise
        # - Divisor 1400: Moderate, good for normal speaking distance
        # - Divisor 1800: Strict, only loud/close speech
        # Using 1400 as a balanced value for robot-distance speaking
        normalized = min(1.0, rms / 1400.0)

        return normalized

    async def detect_speech_segment(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> AsyncIterator[bytes]:
        """Detect and yield speech segment from audio stream.

        Starts yielding when speech is detected.
        Stops when end-of-speech is detected.

        Args:
            audio_stream: Async iterator yielding audio chunks

        Yields:
            Audio chunks during speech
        """
        self._is_running = True
        self._state = SpeechState.SILENCE
        self._speech_start_time = None

        speech_buffer: list[bytes] = []
        pre_speech_buffer: list[bytes] = []
        max_pre_buffer = 10  # Keep ~300ms of pre-speech audio

        try:
            async for chunk in audio_stream:
                if not self._is_running:
                    break

                state = self.process_audio(chunk)

                if state == SpeechState.SILENCE:
                    # Maintain rolling buffer of pre-speech audio
                    pre_speech_buffer.append(chunk)
                    if len(pre_speech_buffer) > max_pre_buffer:
                        pre_speech_buffer.pop(0)

                elif state == SpeechState.SPEAKING:
                    # Start of speech - yield pre-buffer first
                    if not speech_buffer:
                        for pre_chunk in pre_speech_buffer:
                            yield pre_chunk
                        pre_speech_buffer.clear()

                    speech_buffer.append(chunk)
                    yield chunk

                elif state == SpeechState.END_OF_SPEECH:
                    # End of speech - stop yielding
                    break

        finally:
            self._is_running = False

    def reset(self) -> None:
        """Reset VAD state."""
        self._state = SpeechState.SILENCE
        self._speech_start_time = None
        self._last_speech_time = 0.0

        # Reset Silero model state if available
        if self._model is not None:
            self._model.reset_states()

    def stop(self) -> None:
        """Stop VAD processing."""
        self._is_running = False
