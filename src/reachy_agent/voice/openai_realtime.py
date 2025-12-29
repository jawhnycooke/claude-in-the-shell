"""OpenAI Realtime API client for Reachy voice pipeline.

Handles speech-to-text and text-to-speech using OpenAI's Realtime API
with the gpt-realtime-mini model for low-latency voice interactions.
"""

from __future__ import annotations

import base64
import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from openai.resources.beta.realtime import AsyncRealtimeConnection

logger = structlog.get_logger(__name__)


class RealtimeEvent(Enum):
    """Realtime API event types we care about."""

    SESSION_CREATED = "session.created"
    SESSION_UPDATED = "session.updated"
    SPEECH_STARTED = "input_audio_buffer.speech_started"
    SPEECH_STOPPED = "input_audio_buffer.speech_stopped"
    TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"
    RESPONSE_AUDIO_DELTA = "response.audio.delta"
    RESPONSE_AUDIO_DONE = "response.audio.done"
    RESPONSE_AUDIO_TRANSCRIPT_DELTA = "response.audio_transcript.delta"
    RESPONSE_AUDIO_TRANSCRIPT_DONE = "response.audio_transcript.done"
    RESPONSE_TEXT_DELTA = "response.output_text.delta"
    RESPONSE_TEXT_DONE = "response.output_text.done"
    RESPONSE_DONE = "response.done"
    ERROR = "error"


@dataclass
class RealtimeConfig:
    """Configuration for OpenAI Realtime API."""

    model: str = "gpt-realtime-mini"  # Cost-efficient, low latency
    voice: str = "alloy"  # Options: alloy, echo, fable, onyx, nova, shimmer
    sample_rate: int = 24000  # OpenAI Realtime uses 24kHz
    input_sample_rate: int = 16000  # Our microphone sample rate
    temperature: float = 0.8
    max_response_tokens: int = 4096
    turn_detection_threshold: float = 0.5
    turn_detection_silence_ms: int = 500


@dataclass
class TranscriptionResult:
    """Result from speech-to-text."""

    text: str
    confidence: float = 1.0
    duration_seconds: float = 0.0


@dataclass
class OpenAIRealtimeClient:
    """Client for OpenAI Realtime API.

    Provides STT and TTS capabilities using gpt-realtime-mini model.
    Designed to work with the voice pipeline for Reachy.
    """

    config: RealtimeConfig = field(default_factory=RealtimeConfig)
    on_audio_amplitude: Callable[[float], None] | None = None
    on_transcription: Callable[[str], None] | None = None

    _client: AsyncOpenAI | None = field(default=None, repr=False)
    _connection: AsyncRealtimeConnection | None = field(default=None, repr=False)
    _is_connected: bool = field(default=False, repr=False)
    _audio_buffer: list[bytes] = field(default_factory=list, repr=False)
    _response_audio_chunks: list[bytes] = field(default_factory=list, repr=False)
    _current_transcript: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """Initialize the OpenAI client."""
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the AsyncOpenAI client."""
        try:
            from openai import AsyncOpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                logger.warning(
                    "openai_api_key_missing",
                    msg="Set OPENAI_API_KEY environment variable",
                )
                return

            self._client = AsyncOpenAI(api_key=api_key)
            logger.info(
                "openai_client_initialized",
                model=self.config.model,
                voice=self.config.voice,
            )

        except ImportError:
            logger.warning("openai_not_installed", msg="pip install openai")
            self._client = None

    @property
    def is_available(self) -> bool:
        """Check if the client is available."""
        return self._client is not None

    @property
    def is_connected(self) -> bool:
        """Check if connected to Realtime API."""
        return self._is_connected

    async def connect(self) -> bool:
        """Connect to the Realtime API.

        Returns:
            True if connection successful
        """
        if not self._client:
            logger.error("openai_client_not_initialized")
            return False

        try:
            # The OpenAI SDK handles the WebSocket connection
            self._connection = await self._client.beta.realtime.connect(
                model=self.config.model
            ).__aenter__()

            # Configure the session for audio I/O
            await self._connection.session.update(
                session={
                    "modalities": ["audio", "text"],
                    "voice": self.config.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "whisper-1"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": self.config.turn_detection_threshold,
                        "silence_duration_ms": self.config.turn_detection_silence_ms,
                    },
                    "temperature": self.config.temperature,
                    "max_response_output_tokens": self.config.max_response_tokens,
                }
            )

            self._is_connected = True
            logger.info("realtime_connected", model=self.config.model)
            return True

        except Exception as e:
            logger.error("realtime_connection_failed", error=str(e))
            self._is_connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from the Realtime API."""
        if self._connection:
            try:
                await self._connection.__aexit__(None, None, None)
            except Exception as e:
                logger.debug("realtime_disconnect_error", error=str(e))
            finally:
                self._connection = None
                self._is_connected = False
                logger.info("realtime_disconnected")

    async def send_audio(self, audio_data: bytes) -> None:
        """Send audio chunk to the Realtime API.

        Args:
            audio_data: Raw PCM audio bytes (int16, mono)
        """
        if not self._connection:
            return

        # Resample from 16kHz to 24kHz if needed
        if self.config.input_sample_rate != self.config.sample_rate:
            audio_data = self._resample_audio(
                audio_data,
                self.config.input_sample_rate,
                self.config.sample_rate,
            )

        # Encode as base64 for the API
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        try:
            await self._connection.input_audio_buffer.append(audio=audio_b64)
        except Exception as e:
            logger.warning("send_audio_failed", error=str(e))

    async def commit_audio(self) -> None:
        """Commit the audio buffer to trigger transcription."""
        if not self._connection:
            return

        try:
            await self._connection.input_audio_buffer.commit()
            logger.debug("audio_buffer_committed")
        except Exception as e:
            logger.warning("commit_audio_failed", error=str(e))

    async def clear_audio_buffer(self) -> None:
        """Clear the input audio buffer."""
        if not self._connection:
            return

        try:
            await self._connection.input_audio_buffer.clear()
            logger.debug("audio_buffer_cleared")
        except Exception as e:
            logger.warning("clear_audio_failed", error=str(e))

    async def request_response(self) -> None:
        """Request a response from the model."""
        if not self._connection:
            return

        try:
            await self._connection.response.create()
            logger.debug("response_requested")
        except Exception as e:
            logger.warning("request_response_failed", error=str(e))

    async def send_text(self, text: str) -> None:
        """Send a text message to the model.

        Args:
            text: Text message to send
        """
        if not self._connection:
            return

        try:
            await self._connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                }
            )
            await self._connection.response.create()
            logger.debug("text_sent", text_length=len(text))
        except Exception as e:
            logger.warning("send_text_failed", error=str(e))

    async def process_events(self) -> AsyncIterator[tuple[str, bytes | str | None]]:
        """Process events from the Realtime API.

        Yields:
            Tuple of (event_type, data) where:
            - For audio events: data is audio bytes
            - For text events: data is transcript string
            - For other events: data is None
        """
        if not self._connection:
            return

        self._response_audio_chunks.clear()
        self._current_transcript = ""

        try:
            async for event in self._connection:
                event_type = event.type

                if event_type == "response.audio.delta":
                    # Decode audio chunk
                    audio_b64 = event.delta
                    audio_bytes = base64.b64decode(audio_b64)

                    # Calculate amplitude for HeadWobble
                    if self.on_audio_amplitude:
                        amplitude = self._calculate_amplitude(audio_bytes)
                        self.on_audio_amplitude(amplitude)

                    self._response_audio_chunks.append(audio_bytes)
                    yield ("audio_delta", audio_bytes)

                elif event_type == "response.audio.done":
                    if self.on_audio_amplitude:
                        self.on_audio_amplitude(0.0)
                    yield ("audio_done", None)

                elif event_type == "response.audio_transcript.delta":
                    self._current_transcript += event.delta
                    yield ("transcript_delta", event.delta)

                elif event_type == "response.audio_transcript.done":
                    yield ("transcript_done", self._current_transcript)

                elif event_type == "response.output_text.delta":
                    yield ("text_delta", event.delta)

                elif event_type == "response.output_text.done":
                    yield ("text_done", None)

                elif event_type == "response.done":
                    yield ("response_done", None)
                    break

                elif event_type == "input_audio_buffer.speech_started":
                    yield ("speech_started", None)

                elif event_type == "input_audio_buffer.speech_stopped":
                    yield ("speech_stopped", None)

                elif event_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.transcript
                    if self.on_transcription:
                        self.on_transcription(transcript)
                    yield ("transcription", transcript)

                elif event_type == "error":
                    logger.error(
                        "realtime_error",
                        error_type=getattr(event, "error", {}).get("type", "unknown"),
                        message=getattr(event, "error", {}).get("message", ""),
                    )
                    yield ("error", str(event.error.message if hasattr(event, "error") else event))

        except Exception as e:
            logger.error("process_events_failed", error=str(e))
            yield ("error", str(e))

    async def transcribe_audio_stream(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> TranscriptionResult:
        """Transcribe audio stream to text.

        Args:
            audio_stream: Async iterator of audio chunks

        Returns:
            Transcription result with text
        """
        if not self._connection:
            return TranscriptionResult(text="", confidence=0.0)

        # Send all audio chunks
        async for chunk in audio_stream:
            await self.send_audio(chunk)

        # Commit and wait for transcription
        await self.commit_audio()

        transcript = ""
        async for event_type, data in self.process_events():
            if event_type == "transcription":
                transcript = data or ""
                break
            elif event_type == "error":
                logger.error("transcription_error", error=data)
                break

        return TranscriptionResult(text=transcript)

    async def speak(
        self,
        text: str,
    ) -> AsyncIterator[bytes]:
        """Convert text to speech audio stream.

        Args:
            text: Text to speak

        Yields:
            Audio chunks (PCM16, 24kHz)
        """
        if not self._connection:
            return

        await self.send_text(text)

        async for event_type, data in self.process_events():
            if event_type == "audio_delta" and data:
                yield data
            elif event_type == "response_done":
                break
            elif event_type == "error":
                logger.error("speak_error", error=data)
                break

    def get_response_audio(self) -> bytes:
        """Get all collected response audio as a single buffer."""
        return b"".join(self._response_audio_chunks)

    def _resample_audio(
        self,
        audio_data: bytes,
        from_rate: int,
        to_rate: int,
    ) -> bytes:
        """Resample audio to a different sample rate.

        Args:
            audio_data: Input audio bytes (int16)
            from_rate: Original sample rate
            to_rate: Target sample rate

        Returns:
            Resampled audio bytes
        """
        if from_rate == to_rate:
            return audio_data

        samples = np.frombuffer(audio_data, dtype=np.int16)

        # Simple linear interpolation resampling
        ratio = to_rate / from_rate
        new_length = int(len(samples) * ratio)

        indices = np.linspace(0, len(samples) - 1, new_length)
        resampled = np.interp(indices, np.arange(len(samples)), samples)

        return resampled.astype(np.int16).tobytes()

    def _calculate_amplitude(self, audio_data: bytes) -> float:
        """Calculate RMS amplitude of audio chunk (0.0-1.0)."""
        samples = np.frombuffer(audio_data, dtype=np.int16)
        if len(samples) == 0:
            return 0.0

        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        # Normalize to 0-1 range, scaled for visibility
        amplitude = min(1.0, rms / 32767.0 * 3.0)
        return amplitude

    async def __aenter__(self) -> OpenAIRealtimeClient:
        """Async context manager entry - connects to API."""
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit - disconnects from API."""
        await self.disconnect()
