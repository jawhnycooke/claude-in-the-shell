"""Voice pipeline orchestrator for Reachy Agent.

State machine that coordinates:
1. Wake word detection ("Hey Reachy")
2. Voice activity detection (end-of-speech)
3. Speech-to-text (OpenAI Realtime)
4. Claude Agent processing
5. Text-to-speech response (OpenAI Realtime)
6. HeadWobble animation during speech
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import structlog

from reachy_agent.voice.audio import AudioConfig, AudioManager
from reachy_agent.voice.openai_realtime import OpenAIRealtimeClient, RealtimeConfig
from reachy_agent.voice.vad import VADConfig, VoiceActivityDetector
from reachy_agent.voice.wake_word import WakeWordConfig, WakeWordDetector

if TYPE_CHECKING:
    from reachy_agent.agent.agent import ReachyAgentLoop

logger = structlog.get_logger(__name__)


class VoicePipelineState(Enum):
    """Voice pipeline state machine states."""

    IDLE = "idle"  # Not listening, minimal resources
    LISTENING_WAKE = "listening_wake"  # Listening for wake word
    WAKE_DETECTED = "wake_detected"  # Wake word heard, preparing to listen
    LISTENING_SPEECH = "listening_speech"  # Recording user speech
    PROCESSING = "processing"  # Sending to Claude, waiting for response
    SPEAKING = "speaking"  # Playing TTS response
    ERROR = "error"  # Error state


@dataclass
class VoicePipelineConfig:
    """Configuration for the voice pipeline."""

    audio: AudioConfig = field(default_factory=AudioConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)

    # Pipeline behavior
    wake_word_enabled: bool = True
    confirmation_beep: bool = True
    auto_restart: bool = True  # Restart listening after response


@dataclass
class VoicePipeline:
    """Main voice pipeline orchestrator.

    Coordinates all voice components to enable natural voice interaction
    with the Reachy robot and Claude agent.
    """

    agent: ReachyAgentLoop | None = None
    config: VoicePipelineConfig = field(default_factory=VoicePipelineConfig)

    # Callbacks
    on_state_change: Callable[[VoicePipelineState], None] | None = None
    on_transcription: Callable[[str], None] | None = None
    on_response: Callable[[str], None] | None = None
    on_audio_amplitude: Callable[[float], None] | None = None

    # Components
    _audio: AudioManager | None = field(default=None, repr=False)
    _wake_word: WakeWordDetector | None = field(default=None, repr=False)
    _vad: VoiceActivityDetector | None = field(default=None, repr=False)
    _realtime: OpenAIRealtimeClient | None = field(default=None, repr=False)

    # State
    _state: VoicePipelineState = field(default=VoicePipelineState.IDLE, repr=False)
    _is_running: bool = field(default=False, repr=False)
    _main_task: asyncio.Task | None = field(default=None, repr=False)

    @property
    def state(self) -> VoicePipelineState:
        """Get current pipeline state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._is_running

    async def initialize(self) -> bool:
        """Initialize all voice components.

        Returns:
            True if initialization successful
        """
        logger.info("voice_pipeline_initializing")

        # Initialize audio manager
        self._audio = AudioManager(config=self.config.audio)
        if not self._audio.is_available:
            logger.error("audio_not_available")
            return False

        # Initialize wake word detector
        if self.config.wake_word_enabled:
            self._wake_word = WakeWordDetector(
                config=self.config.wake_word,
                on_wake=self._on_wake_word_detected,
            )
            if not self._wake_word.is_available:
                logger.warning("wake_word_not_available", msg="Will skip wake word")

        # Initialize VAD
        self._vad = VoiceActivityDetector(
            config=self.config.vad,
            on_speech_start=self._on_speech_start,
            on_speech_end=self._on_speech_end,
        )

        # Initialize OpenAI Realtime client
        self._realtime = OpenAIRealtimeClient(
            config=self.config.realtime,
            on_audio_amplitude=self._on_audio_amplitude,
            on_transcription=self._on_transcription_received,
        )

        if not self._realtime.is_available:
            logger.error("openai_realtime_not_available")
            return False

        logger.info(
            "voice_pipeline_initialized",
            wake_word_enabled=self.config.wake_word_enabled,
            wake_word_model=self._wake_word.model_name if self._wake_word else None,
        )
        return True

    async def start(self) -> None:
        """Start the voice pipeline."""
        if self._is_running:
            logger.warning("voice_pipeline_already_running")
            return

        # Initialize if not done
        if not self._audio:
            success = await self.initialize()
            if not success:
                logger.error("voice_pipeline_init_failed")
                return

        # Connect to OpenAI Realtime
        connected = await self._realtime.connect()
        if not connected:
            logger.error("realtime_connect_failed")
            return

        self._is_running = True
        self._set_state(VoicePipelineState.LISTENING_WAKE)

        # Start main loop
        self._main_task = asyncio.create_task(self._run_loop())
        logger.info("voice_pipeline_started")

    async def stop(self) -> None:
        """Stop the voice pipeline."""
        self._is_running = False

        if self._main_task:
            self._main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._main_task
            self._main_task = None

        # Clean up components
        if self._audio:
            await self._audio.close()
        if self._realtime:
            await self._realtime.disconnect()
        if self._wake_word:
            self._wake_word.stop()
        if self._vad:
            self._vad.stop()

        self._set_state(VoicePipelineState.IDLE)
        logger.info("voice_pipeline_stopped")

    async def _run_loop(self) -> None:
        """Main pipeline loop."""
        try:
            while self._is_running:
                if self._state == VoicePipelineState.LISTENING_WAKE:
                    await self._listen_for_wake_word()

                elif self._state == VoicePipelineState.WAKE_DETECTED:
                    await self._handle_wake_detected()

                elif self._state == VoicePipelineState.LISTENING_SPEECH:
                    await self._listen_for_speech()

                elif self._state == VoicePipelineState.PROCESSING:
                    await self._process_speech()

                elif self._state == VoicePipelineState.SPEAKING:
                    await self._play_response()

                elif self._state == VoicePipelineState.ERROR:
                    await self._handle_error()

                else:
                    await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.debug("voice_pipeline_loop_cancelled")
        except Exception as e:
            logger.error("voice_pipeline_loop_error", error=str(e))
            self._set_state(VoicePipelineState.ERROR)

    async def _listen_for_wake_word(self) -> None:
        """Listen for wake word activation."""
        if not self._wake_word or not self._wake_word.is_available:
            # Skip wake word, go directly to listening
            self._set_state(VoicePipelineState.LISTENING_SPEECH)
            return

        # Start audio recording
        await self._audio.start_recording()

        logger.debug("listening_for_wake_word")

        try:
            # Process audio chunks for wake word
            async for chunk in self._audio.read_audio_stream():
                if not self._is_running:
                    break

                if self._state != VoicePipelineState.LISTENING_WAKE:
                    break  # State changed by wake word callback

                detected = self._wake_word.process_audio(chunk)
                if detected:
                    self._set_state(VoicePipelineState.WAKE_DETECTED)
                    break

        finally:
            await self._audio.stop_recording()

    async def _handle_wake_detected(self) -> None:
        """Handle wake word detection."""
        logger.info("wake_word_triggered")

        # Signal to agent that we're listening
        if self.agent:
            await self.agent.set_listening_state(True)

        # Optional confirmation beep
        if self.config.confirmation_beep:
            # TODO: Play a confirmation sound
            pass

        self._set_state(VoicePipelineState.LISTENING_SPEECH)

    async def _listen_for_speech(self) -> None:
        """Listen for user speech and detect end-of-speech."""
        logger.debug("listening_for_speech")

        # Start recording
        await self._audio.start_recording()

        # Reset VAD state
        self._vad.reset()

        speech_chunks: list[bytes] = []

        try:
            async for chunk in self._audio.read_audio_stream():
                if not self._is_running:
                    break

                # Send audio to OpenAI Realtime for transcription
                await self._realtime.send_audio(chunk)

                # Collect audio for local processing
                speech_chunks.append(chunk)

                # Check for end of speech
                state = self._vad.process_audio(chunk)
                if state.name == "END_OF_SPEECH":
                    logger.debug(
                        "end_of_speech_detected",
                        chunks=len(speech_chunks),
                    )
                    break

        finally:
            await self._audio.stop_recording()

        # Commit audio buffer and get transcription
        await self._realtime.commit_audio()

        self._set_state(VoicePipelineState.PROCESSING)

    async def _process_speech(self) -> None:
        """Process transcribed speech through Claude agent."""
        logger.debug("processing_speech")

        # Wait for transcription from OpenAI
        transcript = ""
        async for event_type, data in self._realtime.process_events():
            if event_type == "transcription":
                transcript = data or ""
                break
            elif event_type == "error":
                logger.error("transcription_error", error=data)
                self._set_state(VoicePipelineState.ERROR)
                return

        if not transcript.strip():
            logger.debug("empty_transcription")
            self._restart_listening()
            return

        logger.info("transcription_received", text=transcript)

        if self.on_transcription:
            self.on_transcription(transcript)

        # Send to Claude agent
        if self.agent:
            try:
                response = await self.agent.process_input(transcript)
                response_text = response.text if response else ""

                if response_text:
                    logger.info("agent_response", text_length=len(response_text))
                    if self.on_response:
                        self.on_response(response_text)

                    # Queue response for TTS
                    self._pending_response = response_text
                    self._set_state(VoicePipelineState.SPEAKING)
                else:
                    self._restart_listening()

            except Exception as e:
                logger.error("agent_processing_error", error=str(e))
                self._set_state(VoicePipelineState.ERROR)
        else:
            # No agent - just restart listening
            self._restart_listening()

    _pending_response: str = ""

    async def _play_response(self) -> None:
        """Play TTS response through speaker."""
        if not self._pending_response:
            self._restart_listening()
            return

        logger.debug("playing_response", text_length=len(self._pending_response))

        try:
            # Stream TTS audio from OpenAI
            audio_chunks: list[bytes] = []

            async for chunk in self._realtime.speak(self._pending_response):
                audio_chunks.append(chunk)
                # Stream to speaker
                await self._audio.play_audio(chunk)

            logger.debug("response_played", chunks=len(audio_chunks))

        except Exception as e:
            logger.error("tts_playback_error", error=str(e))

        finally:
            self._pending_response = ""

            # Signal to agent that we're done speaking
            if self.agent:
                await self.agent.set_listening_state(False)

            self._restart_listening()

    async def _handle_error(self) -> None:
        """Handle error state."""
        logger.warning("voice_pipeline_error_state")
        await asyncio.sleep(2.0)  # Brief pause before restart

        if self.config.auto_restart:
            self._set_state(VoicePipelineState.LISTENING_WAKE)
        else:
            self._is_running = False

    def _restart_listening(self) -> None:
        """Restart the listening loop."""
        if self.config.auto_restart and self._is_running:
            if self.config.wake_word_enabled:
                self._set_state(VoicePipelineState.LISTENING_WAKE)
            else:
                self._set_state(VoicePipelineState.LISTENING_SPEECH)
        else:
            self._set_state(VoicePipelineState.IDLE)

    def _set_state(self, new_state: VoicePipelineState) -> None:
        """Update pipeline state with callback."""
        old_state = self._state
        self._state = new_state

        logger.debug(
            "state_changed",
            old_state=old_state.value,
            new_state=new_state.value,
        )

        if self.on_state_change:
            self.on_state_change(new_state)

    def _on_wake_word_detected(self) -> None:
        """Callback when wake word is detected."""
        if self._state == VoicePipelineState.LISTENING_WAKE:
            self._set_state(VoicePipelineState.WAKE_DETECTED)

    def _on_speech_start(self) -> None:
        """Callback when speech starts."""
        logger.debug("speech_started")

    def _on_speech_end(self, duration: float) -> None:
        """Callback when speech ends."""
        logger.debug("speech_ended", duration=duration)

    def _on_audio_amplitude(self, amplitude: float) -> None:
        """Callback for TTS audio amplitude (for HeadWobble)."""
        if self.on_audio_amplitude:
            self.on_audio_amplitude(amplitude)

        # Also update agent's wobble if available
        if self.agent and hasattr(self.agent, "_wobble"):
            self.agent._wobble.update_audio_level(amplitude)

    def _on_transcription_received(self, text: str) -> None:
        """Callback when transcription is received."""
        logger.debug("transcription_callback", text=text)

    async def __aenter__(self) -> VoicePipeline:
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.stop()
