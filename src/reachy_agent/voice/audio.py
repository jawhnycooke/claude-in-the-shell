"""Audio I/O manager for Reachy voice pipeline.

Manages hardware audio streams using PyAudio:
- Microphone input from 4-mic array
- Speaker output for TTS playback
- Buffer management for streaming audio
- Device validation and health monitoring
- Retry logic with exponential backoff
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import structlog

from .errors import (
    AudioDeviceError,
    AudioDeviceNotFoundError,
    AudioInitializationError,
    AudioStreamDisconnectedError,
)

if TYPE_CHECKING:
    import pyaudio

logger = structlog.get_logger(__name__)


@dataclass
class AudioConfig:
    """Audio configuration settings.

    Includes resilience settings for production deployments:
    - Retry logic with exponential backoff
    - Configurable health monitoring
    - Buffer tuning for latency optimization
    """

    # Core audio settings
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 512  # Silero VAD requires exactly 512 samples at 16kHz
    format_bits: int = 16
    input_device_index: int | None = None
    output_device_index: int | None = None

    # Resilience settings
    max_init_retries: int = 3
    retry_delay_seconds: float = 1.0
    retry_backoff_factor: float = 2.0

    # Buffer settings
    output_lead_in_ms: int = 200  # Silence before TTS playback (prevents click)
    input_warmup_chunks: int = 5  # Discard first N chunks (mic warmup)

    # Health monitoring
    health_check_interval_seconds: float = 5.0
    max_consecutive_errors: int = 3


@dataclass
class AudioDeviceManager:
    """Validates and manages audio device selection.

    Provides device validation before stream creation to avoid
    runtime failures. Supports fallback to default devices when
    configured devices are unavailable.
    """

    _pyaudio: pyaudio.PyAudio | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize PyAudio for device enumeration."""
        try:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
        except ImportError:
            logger.warning("pyaudio_not_installed")
            self._pyaudio = None

    @property
    def is_available(self) -> bool:
        """Check if audio system is available."""
        return self._pyaudio is not None

    def list_devices(self) -> list[dict]:
        """List all available audio devices with capabilities."""
        if not self._pyaudio:
            return []

        devices = []
        for i in range(self._pyaudio.get_device_count()):
            try:
                info = self._pyaudio.get_device_info_by_index(i)
                devices.append(
                    {
                        "index": i,
                        "name": info.get("name", "Unknown"),
                        "input_channels": info.get("maxInputChannels", 0),
                        "output_channels": info.get("maxOutputChannels", 0),
                        "default_sample_rate": info.get("defaultSampleRate", 0),
                        "host_api": info.get("hostApi", -1),
                    }
                )
            except Exception as e:
                logger.warning("device_enumeration_error", index=i, error=str(e))
        return devices

    def validate_device(
        self,
        device_index: int | None,
        for_input: bool = True,
        sample_rate: int = 16000,
    ) -> bool:
        """Validate that a device exists and supports the required configuration.

        Args:
            device_index: Device index to validate, or None for default
            for_input: True for input device, False for output
            sample_rate: Required sample rate

        Returns:
            True if device is valid and available
        """
        if not self._pyaudio:
            return False

        # None means use default device
        if device_index is None:
            return True

        try:
            info = self._pyaudio.get_device_info_by_index(device_index)

            # Check channel count
            channels_key = "maxInputChannels" if for_input else "maxOutputChannels"
            if info.get(channels_key, 0) < 1:
                logger.warning(
                    "device_insufficient_channels",
                    device_index=device_index,
                    for_input=for_input,
                    channels=info.get(channels_key, 0),
                )
                return False

            # Check sample rate support (PyAudio doesn't expose this directly,
            # but we can catch it during stream creation)
            return True

        except Exception as e:
            logger.warning(
                "device_validation_failed",
                device_index=device_index,
                for_input=for_input,
                error=str(e),
            )
            return False

    def get_fallback_device(self, for_input: bool = True) -> int | None:
        """Get the default device index as fallback.

        Args:
            for_input: True for input device, False for output

        Returns:
            Default device index or None if unavailable
        """
        if not self._pyaudio:
            return None

        try:
            if for_input:
                info = self._pyaudio.get_default_input_device_info()
            else:
                info = self._pyaudio.get_default_output_device_info()
            return info.get("index")
        except Exception as e:
            logger.warning(
                "fallback_device_unavailable",
                for_input=for_input,
                error=str(e),
            )
            return None

    def is_device_available(self, device_index: int | None) -> bool:
        """Quick check if a device is currently available.

        Useful for health monitoring to detect USB device disconnection.

        Args:
            device_index: Device to check, or None for any default

        Returns:
            True if device is available
        """
        if not self._pyaudio:
            return False

        if device_index is None:
            # Check if any default device exists
            try:
                self._pyaudio.get_default_input_device_info()
                return True
            except Exception:
                return False

        try:
            self._pyaudio.get_device_info_by_index(device_index)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """Clean up PyAudio resources."""
        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None


@dataclass
class AudioManager:
    """Manages audio input/output streams with resilience.

    Provides async interfaces for microphone capture and speaker playback.
    Uses PyAudio for cross-platform audio device access.

    Resilience features:
    - Automatic retry with exponential backoff on initialization
    - Device validation before stream creation
    - Health monitoring for stream disconnection detection
    - Configurable fallback behavior
    """

    config: AudioConfig = field(default_factory=AudioConfig)

    # Callbacks for pipeline integration
    on_device_error: Callable[[AudioDeviceError], None] | None = None
    on_stream_recovered: Callable[[], None] | None = None

    # Internal state
    _pyaudio: pyaudio.PyAudio | None = field(default=None, repr=False)
    _device_manager: AudioDeviceManager | None = field(default=None, repr=False)
    _input_stream: pyaudio.Stream | None = field(default=None, repr=False)
    _output_stream: pyaudio.Stream | None = field(default=None, repr=False)
    _audio_queue: queue.Queue[bytes] = field(
        default_factory=lambda: queue.Queue(maxsize=100), repr=False
    )
    _is_recording: bool = field(default=False, repr=False)
    _is_playing: bool = field(default=False, repr=False)
    _record_thread: threading.Thread | None = field(default=None, repr=False)

    # Health monitoring state
    _consecutive_errors: int = field(default=0, repr=False)
    _last_successful_read: float = field(default=0.0, repr=False)
    _health_check_task: asyncio.Task | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize PyAudio with retry logic."""
        self._init_with_retry()

    def _init_with_retry(self) -> None:
        """Initialize PyAudio with exponential backoff retry.

        Raises:
            AudioInitializationError: If all retries exhausted
        """
        delay = self.config.retry_delay_seconds
        last_error: Exception | None = None

        for attempt in range(self.config.max_init_retries):
            try:
                import pyaudio

                self._pyaudio = pyaudio.PyAudio()
                self._device_manager = AudioDeviceManager()
                self._device_manager._pyaudio = self._pyaudio

                logger.info(
                    "audio_manager_initialized",
                    sample_rate=self.config.sample_rate,
                    channels=self.config.channels,
                    attempt=attempt + 1,
                )
                return

            except ImportError:
                logger.warning("pyaudio_not_installed", msg="Audio features unavailable")
                self._pyaudio = None
                self._device_manager = None
                return

            except Exception as e:
                last_error = e
                logger.warning(
                    "audio_init_retry",
                    attempt=attempt + 1,
                    max_attempts=self.config.max_init_retries,
                    delay=delay,
                    error=str(e),
                )
                if attempt < self.config.max_init_retries - 1:
                    time.sleep(delay)
                    delay *= self.config.retry_backoff_factor

        # All retries exhausted
        raise AudioInitializationError(
            f"Failed to initialize audio after {self.config.max_init_retries} attempts",
            original_error=last_error,
        )

    @property
    def is_available(self) -> bool:
        """Check if audio hardware is available."""
        return self._pyaudio is not None

    @property
    def pyaudio_format(self) -> int:
        """Get PyAudio format constant for configured bit depth."""
        import pyaudio

        format_map = {
            8: pyaudio.paInt8,
            16: pyaudio.paInt16,
            24: pyaudio.paInt24,
            32: pyaudio.paInt32,
        }
        return format_map.get(self.config.format_bits, pyaudio.paInt16)

    def list_devices(self) -> list[dict[str, str | int]]:
        """List available audio devices."""
        if self._device_manager:
            return self._device_manager.list_devices()
        return []

    def _validate_and_get_device(self, for_input: bool = True) -> int | None:
        """Validate configured device or get fallback.

        Args:
            for_input: True for input device, False for output

        Returns:
            Valid device index

        Raises:
            AudioDeviceNotFoundError: If no valid device available
        """
        if not self._device_manager:
            raise AudioDeviceNotFoundError(None, for_input)

        configured_index = (
            self.config.input_device_index
            if for_input
            else self.config.output_device_index
        )

        # Validate configured device
        if self._device_manager.validate_device(
            configured_index, for_input, self.config.sample_rate
        ):
            return configured_index

        # Try fallback
        logger.warning(
            "using_fallback_device",
            configured=configured_index,
            for_input=for_input,
        )
        fallback = self._device_manager.get_fallback_device(for_input)

        if fallback is not None and self._device_manager.validate_device(
            fallback, for_input, self.config.sample_rate
        ):
            return fallback

        raise AudioDeviceNotFoundError(configured_index, for_input)

    def _audio_callback(
        self,
        in_data: bytes | None,
        _frame_count: int,
        _time_info: dict,
        status: int,
    ) -> tuple[None, int]:
        """Callback for audio stream - runs in separate thread."""
        import pyaudio

        # Check for stream errors
        if status:
            self._consecutive_errors += 1
            logger.warning(
                "audio_callback_status",
                status=status,
                consecutive_errors=self._consecutive_errors,
            )

            if self._consecutive_errors >= self.config.max_consecutive_errors:
                # Trigger error callback in main thread
                if self.on_device_error:
                    error = AudioStreamDisconnectedError(
                        self.config.input_device_index, "input"
                    )
                    # Can't call async from callback, so just log
                    logger.error(
                        "stream_disconnected",
                        device=self.config.input_device_index,
                        consecutive_errors=self._consecutive_errors,
                    )
        else:
            self._consecutive_errors = 0
            self._last_successful_read = time.time()

        if in_data and self._is_recording:
            try:
                self._audio_queue.put_nowait(in_data)
            except queue.Full:
                logger.warning("audio_queue_full", msg="Dropping audio frame")

        return (None, pyaudio.paContinue)

    async def start_recording(self) -> None:
        """Start recording audio from microphone.

        Raises:
            AudioDeviceNotFoundError: If input device unavailable
            AudioInitializationError: If stream creation fails
        """
        if not self._pyaudio:
            raise AudioInitializationError("PyAudio not available")

        if self._is_recording:
            logger.warning("already_recording")
            return

        # Validate device before opening stream
        device_index = self._validate_and_get_device(for_input=True)

        # Clear any stale audio
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        # Reset health monitoring
        self._consecutive_errors = 0
        self._last_successful_read = time.time()

        try:
            self._input_stream = self._pyaudio.open(
                format=self.pyaudio_format,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.config.chunk_size,
                stream_callback=self._audio_callback,
            )

            self._is_recording = True
            self._input_stream.start_stream()

            # Discard warmup chunks (mic settling)
            for _ in range(self.config.input_warmup_chunks):
                try:
                    self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    break

            logger.info(
                "recording_started",
                sample_rate=self.config.sample_rate,
                device=device_index,
            )

        except Exception as e:
            raise AudioInitializationError(
                f"Failed to open input stream: {e}",
                device_index=device_index,
                original_error=e,
            )

    async def stop_recording(self) -> None:
        """Stop recording audio."""
        self._is_recording = False
        if self._input_stream:
            try:
                self._input_stream.stop_stream()
                self._input_stream.close()
            except Exception as e:
                logger.warning("stream_close_error", error=str(e))
            self._input_stream = None
        logger.info("recording_stopped")

    async def read_audio(self, timeout: float = 0.1) -> bytes | None:
        """Read a chunk of audio from the recording buffer.

        Args:
            timeout: Maximum time to wait for audio data

        Returns:
            Audio bytes or None if timeout
        """
        try:
            return await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._audio_queue.get(timeout=timeout)
            )
        except queue.Empty:
            return None

    async def read_audio_stream(self) -> AsyncIterator[bytes]:
        """Async generator yielding audio chunks while recording."""
        while self._is_recording:
            chunk = await self.read_audio(timeout=0.1)
            if chunk:
                yield chunk

    def _generate_silence(self, duration_ms: int) -> bytes:
        """Generate silence audio for lead-in.

        Args:
            duration_ms: Duration of silence in milliseconds

        Returns:
            Silent PCM audio bytes
        """
        num_samples = int(self.config.sample_rate * duration_ms / 1000)
        silence = np.zeros(num_samples, dtype=np.int16)
        return silence.tobytes()

    async def play_audio(self, audio_data: bytes) -> None:
        """Play audio through the speaker.

        Args:
            audio_data: Raw PCM audio bytes to play

        Raises:
            AudioDeviceNotFoundError: If output device unavailable
        """
        if not self._pyaudio:
            raise AudioInitializationError("PyAudio not available")

        # Validate device before playing
        device_index = self._validate_and_get_device(for_input=False)

        def _play() -> None:
            stream = self._pyaudio.open(
                format=self.pyaudio_format,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                output=True,
                output_device_index=device_index,
            )
            try:
                # Add lead-in silence to prevent click/pop
                if self.config.output_lead_in_ms > 0:
                    silence = self._generate_silence(self.config.output_lead_in_ms)
                    stream.write(silence)
                stream.write(audio_data)
            finally:
                stream.stop_stream()
                stream.close()

        self._is_playing = True
        try:
            await asyncio.get_event_loop().run_in_executor(None, _play)
        finally:
            self._is_playing = False

    async def play_audio_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        on_amplitude: Callable[[float], None] | None = None,
    ) -> None:
        """Stream audio chunks to the speaker.

        Args:
            audio_chunks: Async iterator of audio bytes
            on_amplitude: Optional callback with audio amplitude (0.0-1.0)

        Raises:
            AudioDeviceNotFoundError: If output device unavailable
        """
        if not self._pyaudio:
            raise AudioInitializationError("PyAudio not available")

        # Validate device before streaming
        device_index = self._validate_and_get_device(for_input=False)

        stream = self._pyaudio.open(
            format=self.pyaudio_format,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            output=True,
            output_device_index=device_index,
        )

        self._is_playing = True
        try:
            # Add lead-in silence to prevent click/pop
            if self.config.output_lead_in_ms > 0:
                silence = self._generate_silence(self.config.output_lead_in_ms)
                await asyncio.get_event_loop().run_in_executor(
                    None, stream.write, silence
                )

            async for chunk in audio_chunks:
                if on_amplitude:
                    amplitude = self._calculate_amplitude(chunk)
                    on_amplitude(amplitude)

                await asyncio.get_event_loop().run_in_executor(
                    None, stream.write, chunk
                )
        finally:
            if on_amplitude:
                on_amplitude(0.0)  # Reset amplitude when done
            stream.stop_stream()
            stream.close()
            self._is_playing = False

    def _calculate_amplitude(self, audio_data: bytes) -> float:
        """Calculate RMS amplitude of audio chunk (0.0-1.0)."""
        samples = np.frombuffer(audio_data, dtype=np.int16)
        if len(samples) == 0:
            return 0.0

        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        # Normalize to 0-1 range (int16 max is 32767)
        amplitude = min(1.0, rms / 32767.0 * 3.0)  # Scale up for visibility
        return amplitude

    def stop_playback(self) -> None:
        """Stop any ongoing audio playback."""
        self._is_playing = False

    def check_health(self) -> bool:
        """Check if audio streams are healthy.

        Returns:
            True if healthy, False if issues detected
        """
        if not self._is_recording:
            return True

        # Check for stale reads (no audio for too long)
        if self._last_successful_read > 0:
            elapsed = time.time() - self._last_successful_read
            if elapsed > self.config.health_check_interval_seconds:
                logger.warning(
                    "audio_health_check_failed",
                    seconds_since_read=elapsed,
                    threshold=self.config.health_check_interval_seconds,
                )
                return False

        # Check consecutive error count
        if self._consecutive_errors >= self.config.max_consecutive_errors:
            logger.warning(
                "audio_health_check_failed",
                consecutive_errors=self._consecutive_errors,
                threshold=self.config.max_consecutive_errors,
            )
            return False

        return True

    async def close(self) -> None:
        """Clean up audio resources."""
        await self.stop_recording()
        if self._device_manager:
            self._device_manager.close()
            self._device_manager = None
        if self._pyaudio:
            self._pyaudio.terminate()
            self._pyaudio = None
        logger.info("audio_manager_closed")

    async def __aenter__(self) -> AudioManager:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()
