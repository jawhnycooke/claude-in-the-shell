"""Audio I/O manager for Reachy voice pipeline.

Manages hardware audio streams using PyAudio:
- Microphone input from 4-mic array
- Speaker output for TTS playback
- Buffer management for streaming audio
"""

from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    import pyaudio

logger = structlog.get_logger(__name__)


@dataclass
class AudioConfig:
    """Audio configuration settings."""

    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 512  # Silero VAD requires exactly 512 samples at 16kHz
    format_bits: int = 16
    input_device_index: int | None = None
    output_device_index: int | None = None


@dataclass
class AudioManager:
    """Manages audio input/output streams.

    Provides async interfaces for microphone capture and speaker playback.
    Uses PyAudio for cross-platform audio device access.
    """

    config: AudioConfig = field(default_factory=AudioConfig)
    _pyaudio: pyaudio.PyAudio | None = field(default=None, repr=False)
    _input_stream: pyaudio.Stream | None = field(default=None, repr=False)
    _output_stream: pyaudio.Stream | None = field(default=None, repr=False)
    _audio_queue: queue.Queue[bytes] = field(
        default_factory=lambda: queue.Queue(maxsize=100), repr=False
    )
    _is_recording: bool = field(default=False, repr=False)
    _is_playing: bool = field(default=False, repr=False)
    _record_thread: threading.Thread | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize PyAudio instance."""
        try:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
            logger.info(
                "audio_manager_initialized",
                sample_rate=self.config.sample_rate,
                channels=self.config.channels,
            )
        except ImportError:
            logger.warning("pyaudio_not_installed", msg="Audio features unavailable")
            self._pyaudio = None

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
        if not self._pyaudio:
            return []

        devices = []
        for i in range(self._pyaudio.get_device_count()):
            info = self._pyaudio.get_device_info_by_index(i)
            devices.append(
                {
                    "index": i,
                    "name": info.get("name", "Unknown"),
                    "input_channels": info.get("maxInputChannels", 0),
                    "output_channels": info.get("maxOutputChannels", 0),
                    "default_sample_rate": info.get("defaultSampleRate", 0),
                }
            )
        return devices

    def _audio_callback(
        self,
        in_data: bytes | None,
        _frame_count: int,
        _time_info: dict,
        _status: int,
    ) -> tuple[None, int]:
        """Callback for audio stream - runs in separate thread."""
        import pyaudio

        if in_data and self._is_recording:
            try:
                self._audio_queue.put_nowait(in_data)
            except queue.Full:
                logger.warning("audio_queue_full", msg="Dropping audio frame")
        return (None, pyaudio.paContinue)

    async def start_recording(self) -> None:
        """Start recording audio from microphone."""
        if not self._pyaudio:
            raise RuntimeError("PyAudio not available")

        if self._is_recording:
            logger.warning("already_recording")
            return


        # Clear any stale audio
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        self._input_stream = self._pyaudio.open(
            format=self.pyaudio_format,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            input=True,
            input_device_index=self.config.input_device_index,
            frames_per_buffer=self.config.chunk_size,
            stream_callback=self._audio_callback,
        )

        self._is_recording = True
        self._input_stream.start_stream()
        logger.info("recording_started", sample_rate=self.config.sample_rate)

    async def stop_recording(self) -> None:
        """Stop recording audio."""
        self._is_recording = False
        if self._input_stream:
            self._input_stream.stop_stream()
            self._input_stream.close()
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

    async def play_audio(self, audio_data: bytes) -> None:
        """Play audio through the speaker.

        Args:
            audio_data: Raw PCM audio bytes to play
        """
        if not self._pyaudio:
            raise RuntimeError("PyAudio not available")

        def _play() -> None:
            stream = self._pyaudio.open(
                format=self.pyaudio_format,
                channels=self.config.channels,
                rate=self.config.sample_rate,
                output=True,
                output_device_index=self.config.output_device_index,
            )
            try:
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
        """
        if not self._pyaudio:
            raise RuntimeError("PyAudio not available")

        stream = self._pyaudio.open(
            format=self.pyaudio_format,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            output=True,
            output_device_index=self.config.output_device_index,
        )

        self._is_playing = True
        try:
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

    async def close(self) -> None:
        """Clean up audio resources."""
        await self.stop_recording()
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
