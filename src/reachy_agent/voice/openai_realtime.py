"""OpenAI Realtime API client for Reachy voice pipeline.

Handles speech-to-text and text-to-speech using OpenAI's Realtime API
with the gpt-realtime-mini model for low-latency voice interactions.
"""

from __future__ import annotations

import base64
import os
import time
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

# OpenAI Realtime API WebSocket timeout is around 30 seconds of inactivity.
# We use a conservative threshold to proactively reconnect before timeout.
CONNECTION_IDLE_TIMEOUT_SECONDS = 25.0


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
    # Note: We use local VAD (not server VAD), so no turn_detection config here


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
    _last_activity_time: float = field(default=0.0, repr=False)
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
        return self._is_connected and self._connection is not None

    async def update_voice(self, new_voice: str) -> bool:
        """Update the TTS voice, reconnecting if necessary.

        Used for persona switching - changes the voice used for TTS responses.
        Requires a session reconnect because voice is set at session creation.

        Args:
            new_voice: New voice to use (alloy, echo, fable, onyx, nova, shimmer)

        Returns:
            True if voice update succeeded
        """
        if self.config.voice == new_voice:
            logger.debug("update_voice_already_set", voice=new_voice)
            return True

        old_voice = self.config.voice
        self.config.voice = new_voice

        logger.info(
            "update_voice_changing",
            from_voice=old_voice,
            to_voice=new_voice,
        )

        # Must reconnect to apply the new voice
        if self._is_connected:
            await self.disconnect()
            success = await self.connect()
            if not success:
                # Restore old voice on failure
                self.config.voice = old_voice
                logger.error("update_voice_reconnect_failed", voice=new_voice)
                return False

        logger.info("update_voice_changed", voice=new_voice)
        return True

    async def ensure_connected(self) -> bool:
        """Ensure connection is active, reconnecting if needed.

        The WebSocket can timeout during long Claude processing periods.
        This method detects stale connections and reconnects automatically
        before the timeout occurs.

        Returns:
            True if connected (possibly after reconnection)
        """
        if self._is_connected and self._connection is not None:
            # Check if connection has been idle too long
            idle_time = time.monotonic() - self._last_activity_time
            if idle_time > CONNECTION_IDLE_TIMEOUT_SECONDS:
                # Connection is likely dead or about to timeout, reconnect proactively
                logger.info(
                    "realtime_reconnecting_stale",
                    idle_seconds=round(idle_time, 1),
                    threshold=CONNECTION_IDLE_TIMEOUT_SECONDS,
                )
                await self.disconnect()
                return await self.connect()
            return True

        # Need to reconnect
        logger.info("realtime_reconnecting", reason="connection_lost_or_timeout")
        self._is_connected = False
        self._connection = None
        return await self.connect()

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
            # CRITICAL: We disable server VAD (turn_detection: null) because we use
            # our own local VAD for end-of-speech detection. Using server_vad would
            # cause OpenAI to consume/process the audio buffer automatically, which
            # conflicts with our manual commit flow and results in "buffer too small"
            # errors when we try to commit.
            #
            # Manual mode flow:
            # 1. Client sends audio via input_audio_buffer.append
            # 2. Client detects end-of-speech with local VAD
            # 3. Client commits buffer via input_audio_buffer.commit
            # 4. Server transcribes and returns conversation.item.input_audio_transcription.completed
            await self._connection.session.update(
                session={
                    "modalities": ["audio", "text"],
                    "voice": self.config.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1",
                        "language": "en",  # Force English transcription
                    },
                    "turn_detection": None,  # Disable server VAD - we use local VAD
                    "temperature": self.config.temperature,
                    "max_response_output_tokens": self.config.max_response_tokens,
                }
            )

            self._is_connected = True
            self._last_activity_time = time.monotonic()
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
                await self._connection.close()
            except Exception as e:
                logger.debug("realtime_disconnect_error", error=str(e))
            finally:
                self._connection = None
                self._is_connected = False
                logger.info("realtime_disconnected")

    async def send_audio(self, audio_data: bytes) -> bool:
        """Send audio chunk to the Realtime API.

        Args:
            audio_data: Raw PCM audio bytes (int16, mono)

        Returns:
            True if audio was sent successfully, False if connection is dead
        """
        if not self._connection:
            logger.debug("send_audio_no_connection")
            return False

        original_size = len(audio_data)

        # Resample from 16kHz to 24kHz if needed
        if self.config.input_sample_rate != self.config.sample_rate:
            audio_data = self._resample_audio(
                audio_data,
                self.config.input_sample_rate,
                self.config.sample_rate,
            )

        resampled_size = len(audio_data)

        # Encode as base64 for the API
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        try:
            await self._connection.input_audio_buffer.append(audio=audio_b64)
            self._last_activity_time = time.monotonic()
            # Log every 50th chunk to avoid log spam but still provide visibility
            if not hasattr(self, "_send_count"):
                self._send_count = 0
            self._send_count += 1
            if self._send_count % 50 == 1:
                logger.debug(
                    "send_audio_chunk",
                    chunk_num=self._send_count,
                    original_bytes=original_size,
                    resampled_bytes=resampled_size,
                    b64_len=len(audio_b64),
                )
            return True
        except Exception as e:
            error_str = str(e)
            # Detect WebSocket death (1011 = internal error, keepalive timeout)
            if "1011" in error_str or "keepalive" in error_str or "closed" in error_str:
                logger.warning("send_audio_connection_dead", error=error_str)
                self._is_connected = False
                self._connection = None
                return False
            logger.warning("send_audio_failed", error=error_str)
            return False

    async def send_audio_batch(self, chunks: list[bytes]) -> bool:
        """Send multiple audio chunks to the Realtime API.

        Args:
            chunks: List of raw PCM audio byte chunks (int16, mono)

        Returns:
            True if all audio was sent successfully
        """
        if not chunks:
            return True

        logger.info("send_audio_batch_starting", chunk_count=len(chunks))

        for i, chunk in enumerate(chunks):
            success = await self.send_audio(chunk)
            if not success:
                logger.warning("send_audio_batch_failed", at_chunk=i, total=len(chunks))
                return False

        logger.info("send_audio_batch_complete", chunk_count=len(chunks))
        return True

    async def commit_audio(self) -> bool:
        """Commit the audio buffer to trigger transcription.

        In manual VAD mode, this must be called after the client detects
        end-of-speech. It triggers the server to create a user message
        item and begin transcription.

        Returns:
            True if commit succeeded, False otherwise
        """
        if not self._connection:
            logger.warning("commit_audio_no_connection")
            return False

        try:
            await self._connection.input_audio_buffer.commit()
            self._last_activity_time = time.monotonic()
            logger.info("audio_buffer_committed_successfully")
            return True
        except Exception as e:
            error_str = str(e)
            # "buffer too small" means no audio was in the buffer to commit
            if "too small" in error_str.lower() or "empty" in error_str.lower():
                logger.error(
                    "commit_audio_buffer_empty",
                    error=error_str,
                    msg="No audio data was received by OpenAI - check send_audio flow",
                )
            else:
                logger.warning("commit_audio_failed", error=error_str)
            return False

    async def clear_audio_buffer(self) -> None:
        """Clear the input audio buffer.

        In manual VAD mode, this should be called before starting a new
        recording session to ensure no stale audio from previous interactions.
        """
        if not self._connection:
            return

        try:
            await self._connection.input_audio_buffer.clear()
            # Reset the send counter for the new recording session
            self._send_count = 0
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
        """Send text to OpenAI Realtime for TTS playback.

        This creates an assistant message containing the exact text we want
        spoken, then triggers a response to generate the audio. Using role
        "assistant" ensures OpenAI reads the text verbatim rather than
        generating a reply to it.

        Args:
            text: Text to be spoken aloud
        """
        if not self._connection:
            return

        try:
            # Clear any lingering audio buffer from previous STT
            await self._connection.input_audio_buffer.clear()

            # Create an assistant message with the text to speak
            # IMPORTANT: Using role="assistant" makes OpenAI read this text
            # verbatim for TTS. Using role="user" would cause OpenAI to
            # generate its own response TO this text instead.
            await self._connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": text}],
                }
            )
            # Request audio generation for the assistant message
            await self._connection.response.create()
            self._last_activity_time = time.monotonic()
            logger.debug("text_sent_for_tts", text_length=len(text))
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
                # Update activity time on any event received
                self._last_activity_time = time.monotonic()

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
                    # Handle error event - error object has type, code, message attributes
                    error_obj = getattr(event, "error", None)
                    if error_obj:
                        error_type = getattr(error_obj, "type", "unknown")
                        error_code = getattr(error_obj, "code", "unknown")
                        error_message = getattr(error_obj, "message", str(error_obj))
                        logger.error(
                            "realtime_error",
                            error_type=error_type,
                            error_code=error_code,
                            message=error_message,
                        )
                        yield ("error", error_message)
                    else:
                        logger.error("realtime_error", event=str(event))
                        yield ("error", str(event))

        except Exception as e:
            logger.error("process_events_failed", error=str(e))
            yield ("error", str(e))

    async def transcribe_audio_stream(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> TranscriptionResult:
        """Transcribe audio stream to text using Realtime API.

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

    async def transcribe_whisper(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
    ) -> TranscriptionResult:
        """Transcribe audio using OpenAI's standard Whisper API (batch).

        This is a batch endpoint - you send complete audio and get transcription.
        Useful for comparing latency against the Realtime API's streaming approach.

        Args:
            audio_data: Complete audio buffer (int16 PCM mono)
            sample_rate: Sample rate of the audio (default 16kHz)

        Returns:
            Transcription result with text
        """
        import io
        import wave

        if not self._client:
            logger.error("transcribe_whisper_no_client")
            return TranscriptionResult(text="", confidence=0.0)

        start_time = time.monotonic()

        try:
            # Convert PCM to WAV format (Whisper API requires a file format)
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data)

            wav_buffer.seek(0)
            wav_buffer.name = "audio.wav"  # Required for the API

            audio_duration = len(audio_data) / 2 / sample_rate  # 2 bytes per sample
            logger.info(
                "transcribe_whisper_starting",
                audio_bytes=len(audio_data),
                audio_duration_s=round(audio_duration, 2),
            )

            # Call the standard Whisper API
            response = await self._client.audio.transcriptions.create(
                model="whisper-1",
                file=wav_buffer,
                language="en",
                response_format="text",
            )

            elapsed = time.monotonic() - start_time
            transcript = response.strip() if isinstance(response, str) else str(response)

            logger.info(
                "transcribe_whisper_complete",
                latency_ms=round(elapsed * 1000, 1),
                transcript_length=len(transcript),
                transcript_preview=transcript[:50] if transcript else "(empty)",
            )

            return TranscriptionResult(
                text=transcript,
                confidence=1.0,
                duration_seconds=audio_duration,
            )

        except Exception as e:
            elapsed = time.monotonic() - start_time
            logger.error("transcribe_whisper_failed", error=str(e), elapsed_ms=round(elapsed * 1000, 1))
            return TranscriptionResult(text="", confidence=0.0)

    async def speak(
        self,
        text: str,
    ) -> AsyncIterator[bytes]:
        """Convert text to speech audio stream using OpenAI's standard TTS API.

        Uses the /audio/speech endpoint which speaks text VERBATIM, unlike the
        Realtime API which generates conversational responses.

        Args:
            text: Text to speak (will be spoken exactly as provided)

        Yields:
            Audio chunks (PCM16, 24kHz)
        """
        if not self._client:
            logger.error("speak_failed_no_client")
            return

        try:
            logger.debug("speak_verbatim_starting", text_length=len(text))

            # Use the standard TTS API with streaming response
            # This speaks text VERBATIM, unlike the Realtime API
            async with self._client.audio.speech.with_streaming_response.create(
                model="tts-1",  # or "tts-1-hd" for higher quality
                voice=self.config.voice,
                input=text,
                response_format="pcm",  # Raw PCM16 at 24kHz
            ) as response:
                # Stream audio chunks as they arrive
                async for chunk in response.iter_bytes(chunk_size=4096):
                    if chunk:
                        # Calculate amplitude for HeadWobble if callback registered
                        if self.on_audio_amplitude:
                            amplitude = self._calculate_amplitude(chunk)
                            self.on_audio_amplitude(amplitude)
                        yield chunk

            # Reset amplitude when done
            if self.on_audio_amplitude:
                self.on_audio_amplitude(0.0)

            logger.debug("speak_verbatim_complete")

        except Exception as e:
            logger.error("speak_verbatim_failed", error=str(e))
            if self.on_audio_amplitude:
                self.on_audio_amplitude(0.0)

    async def speak_realtime(
        self,
        text: str,
    ) -> AsyncIterator[bytes]:
        """Convert text to speech using the Realtime API (DEPRECATED).

        WARNING: This method generates conversational responses, NOT verbatim
        speech. The Realtime API considers conversation history and may rephrase
        or respond to the text instead of speaking it directly.

        Use speak() instead for verbatim TTS.

        Args:
            text: Text to speak

        Yields:
            Audio chunks (PCM16, 24kHz)
        """
        # Ensure connection is alive - it may have timed out during Claude processing
        if not await self.ensure_connected():
            logger.error("speak_failed_no_connection")
            return

        try:
            await self.send_text(text)
        except Exception as e:
            error_str = str(e)
            if "1011" in error_str or "keepalive" in error_str or "closed" in error_str:
                # Connection died, try to reconnect once
                logger.info("speak_reconnecting_after_send_failure")
                self._is_connected = False
                self._connection = None
                if not await self.connect():
                    logger.error("speak_reconnect_failed")
                    return
                await self.send_text(text)
            else:
                logger.error("speak_send_text_failed", error=error_str)
                return

        async for event_type, data in self.process_events():
            if event_type == "audio_delta" and data:
                yield data
            elif event_type == "response_done":
                break
            elif event_type == "error":
                # Ignore stale audio buffer errors from previous STT phase
                error_str = str(data) if data else ""
                if "input_audio_buffer" in error_str:
                    logger.debug("speak_ignoring_stale_buffer_error", error=data)
                    continue
                # Check for connection timeout errors
                if "1011" in error_str or "keepalive" in error_str:
                    logger.warning("speak_connection_timeout", error=data)
                    self._is_connected = False
                    self._connection = None
                    break
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
