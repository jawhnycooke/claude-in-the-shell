"""Voice pipeline orchestrator for Reachy Agent.

State machine that coordinates:
1. Wake word detection ("Hey Reachy")
2. Voice activity detection (end-of-speech)
3. Speech-to-text (OpenAI Realtime)
4. Claude Agent processing
5. Text-to-speech response (OpenAI Realtime)
6. HeadWobble animation during speech

State machine features:
- Valid transition validation (prevents invalid state changes)
- Async locking (prevents race conditions)
- Timeout guards (prevents stuck states)
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import structlog

from reachy_agent.voice.audio import AudioConfig, AudioManager
from reachy_agent.voice.errors import StateTimeoutError, StateTransitionError
from reachy_agent.voice.openai_realtime import OpenAIRealtimeClient, RealtimeConfig
from reachy_agent.voice.persona import PersonaConfig, PersonaManager
from reachy_agent.voice.recovery import (
    DegradedModeConfig,
    PipelineRecoveryManager,
    RecoveryAction,
)
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


# Valid state transitions (from_state -> set of allowed to_states)
# Any transition not in this matrix is invalid and will be logged/rejected
VALID_TRANSITIONS: dict[VoicePipelineState, set[VoicePipelineState]] = {
    VoicePipelineState.IDLE: {
        VoicePipelineState.LISTENING_WAKE,
        VoicePipelineState.LISTENING_SPEECH,  # Direct speech mode (no wake word)
    },
    VoicePipelineState.LISTENING_WAKE: {
        VoicePipelineState.WAKE_DETECTED,
        VoicePipelineState.LISTENING_SPEECH,  # Wake word disabled/unavailable
        VoicePipelineState.IDLE,
        VoicePipelineState.ERROR,
    },
    VoicePipelineState.WAKE_DETECTED: {
        VoicePipelineState.LISTENING_SPEECH,
        VoicePipelineState.LISTENING_WAKE,  # Timeout waiting for speech
        VoicePipelineState.ERROR,
    },
    VoicePipelineState.LISTENING_SPEECH: {
        VoicePipelineState.PROCESSING,
        VoicePipelineState.LISTENING_WAKE,  # Empty/failed speech
        VoicePipelineState.IDLE,
        VoicePipelineState.ERROR,
    },
    VoicePipelineState.PROCESSING: {
        VoicePipelineState.SPEAKING,
        VoicePipelineState.LISTENING_WAKE,  # Empty response
        VoicePipelineState.IDLE,
        VoicePipelineState.ERROR,
    },
    VoicePipelineState.SPEAKING: {
        VoicePipelineState.LISTENING_WAKE,  # Response complete
        VoicePipelineState.IDLE,
        VoicePipelineState.ERROR,
    },
    VoicePipelineState.ERROR: {
        VoicePipelineState.LISTENING_WAKE,  # Auto-recovery
        VoicePipelineState.IDLE,  # Manual stop
    },
}

# Maximum time allowed in each state before forcing ERROR transition
# IDLE and LISTENING_WAKE have no timeout (can wait indefinitely)
STATE_TIMEOUTS: dict[VoicePipelineState, float] = {
    VoicePipelineState.WAKE_DETECTED: 2.0,  # Quick transition expected
    VoicePipelineState.LISTENING_SPEECH: 35.0,  # max_speech_duration + buffer
    VoicePipelineState.PROCESSING: 90.0,  # Claude response (includes tool calls)
    VoicePipelineState.SPEAKING: 180.0,  # Long responses (3 minutes max)
    VoicePipelineState.ERROR: 10.0,  # Brief error recovery pause
}


@dataclass
class VoicePipelineConfig:
    """Configuration for the voice pipeline."""

    audio: AudioConfig = field(default_factory=AudioConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)
    degraded_mode: DegradedModeConfig = field(default_factory=DegradedModeConfig)

    # Pipeline behavior
    wake_word_enabled: bool = True
    confirmation_beep: bool = True
    auto_restart: bool = True  # Restart listening after response

    # Persona management (Ghost in the Shell theme)
    persona_manager: PersonaManager | None = None


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

    # User feedback callbacks for errors and degraded modes
    on_error_message: Callable[[str], None] | None = None
    on_degraded_mode: Callable[[str, bool], None] | None = None  # (component, is_degraded)
    on_listening_timeout: Callable[[float], None] | None = None
    on_transcription_empty: Callable[[], None] | None = None

    # Recovery manager (initialized in __post_init__)
    _recovery: PipelineRecoveryManager = field(
        default_factory=PipelineRecoveryManager, repr=False
    )

    # Components
    _audio: AudioManager | None = field(default=None, repr=False)
    _wake_word: WakeWordDetector | None = field(default=None, repr=False)
    _vad: VoiceActivityDetector | None = field(default=None, repr=False)
    _realtime: OpenAIRealtimeClient | None = field(default=None, repr=False)

    # State
    _state: VoicePipelineState = field(default=VoicePipelineState.IDLE, repr=False)
    _is_running: bool = field(default=False, repr=False)
    _main_task: asyncio.Task | None = field(default=None, repr=False)
    _pending_response: str = field(default="", repr=False)
    _is_speaking: bool = field(default=False, repr=False)  # Suppress wake word during TTS

    # State machine locking and timeout management
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _state_entered_at: float = field(default=0.0, repr=False)  # time.monotonic() when state entered
    _timeout_task: asyncio.Task | None = field(default=None, repr=False)

    # Latency tracking (time.monotonic() for each segment)
    _wake_time: float = field(default=0.0, repr=False)
    _speech_end_time: float = field(default=0.0, repr=False)
    _transcription_time: float = field(default=0.0, repr=False)
    _response_time: float = field(default=0.0, repr=False)
    _tts_start_time: float = field(default=0.0, repr=False)

    # Persona state (Ghost in the Shell theme)
    _current_persona: PersonaConfig | None = field(default=None, repr=False)
    _pending_persona: PersonaConfig | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize recovery manager with config and callbacks."""
        # Configure recovery manager with degraded mode settings from config
        self._recovery = PipelineRecoveryManager(
            config=self.config.degraded_mode,
            on_degraded_mode=self._on_degraded_mode_change,
        )

        # Initialize default persona if persona manager is configured
        if self.config.persona_manager:
            default_persona = self.config.persona_manager.get_default()
            if default_persona:
                self._current_persona = default_persona
                self.config.persona_manager.current_persona = default_persona
                logger.info(
                    "default_persona_initialized",
                    persona=default_persona.name,
                    voice=default_persona.voice,
                )

    def _on_degraded_mode_change(self, component: str, is_degraded: bool) -> None:
        """Internal callback when a component enters/exits degraded mode."""
        if self.on_degraded_mode:
            self.on_degraded_mode(component, is_degraded)

    @property
    def state(self) -> VoicePipelineState:
        """Get current pipeline state."""
        return self._state

    @property
    def degraded_modes(self) -> set[str]:
        """Get currently active degraded modes."""
        return self._recovery.degraded_modes

    @property
    def is_degraded(self) -> bool:
        """Check if any component is in degraded mode."""
        return len(self._recovery.degraded_modes) > 0

    @property
    def is_running(self) -> bool:
        """Check if pipeline is running."""
        return self._is_running

    @property
    def current_persona(self) -> PersonaConfig | None:
        """Get the currently active persona."""
        return self._current_persona

    async def _switch_persona(self, persona: PersonaConfig) -> bool:
        """Switch to a new persona.

        Updates the voice, system prompt, and reconnects to OpenAI.

        Args:
            persona: The PersonaConfig to switch to

        Returns:
            True if switch succeeded
        """
        old_persona = self._current_persona
        logger.info(
            "persona_switching",
            from_persona=old_persona.name if old_persona else None,
            to_persona=persona.name,
            new_voice=persona.voice,
        )

        # Update the current persona
        self._current_persona = persona
        if self.config.persona_manager:
            self.config.persona_manager.current_persona = persona

        # Update OpenAI voice (requires reconnect)
        if self._realtime:
            self.config.realtime.voice = persona.voice
            await self._realtime.disconnect()
            connected = await self._realtime.connect()
            if not connected:
                logger.error("persona_switch_reconnect_failed", persona=persona.name)
                return False

        # Update agent system prompt if available
        if self.agent and hasattr(self.agent, "update_system_prompt"):
            from reachy_agent.agent.options import load_persona_prompt

            new_prompt = load_persona_prompt(persona)
            self.agent.update_system_prompt(new_prompt)
            logger.info(
                "persona_prompt_updated",
                persona=persona.name,
                prompt_length=len(new_prompt),
            )

        logger.info(
            "persona_switched",
            persona=persona.name,
            voice=persona.voice,
            display_name=persona.display_name,
        )
        return True

    def get_recovery_status(self) -> dict:
        """Get detailed recovery status report.

        Returns a dict with:
        - degraded_modes: List of components in degraded mode
        - strategies: Per-component retry state (current_retries, max_retries, last_failure)
        - state: Current pipeline state
        - is_running: Whether pipeline is active

        Useful for monitoring and debugging.
        """
        status = self._recovery.get_status_report()
        status["state"] = self._state.value
        status["is_running"] = self._is_running
        return status

    async def initialize(self) -> bool:
        """Initialize all voice components with recovery support.

        Components are initialized with graceful degradation:
        - Audio: Required - pipeline fails if audio unavailable
        - Wake word: Optional - falls back to direct speech mode if unavailable
        - VAD: Optional - falls back to energy-based detection if Silero unavailable
        - OpenAI Realtime: Required - pipeline fails if unavailable

        Returns:
            True if initialization successful (may be in degraded mode)
        """
        logger.info("voice_pipeline_initializing")

        # Reset recovery state from any previous run
        self._recovery.reset_all()

        # Initialize audio manager (required - cannot degrade)
        self._audio = AudioManager(config=self.config.audio)
        if not self._audio.is_available:
            logger.error("audio_not_available")
            if self.on_error_message:
                self.on_error_message("Audio device not available")
            return False

        # Initialize wake word detector with degraded mode support
        if self.config.wake_word_enabled:
            try:
                self._wake_word = WakeWordDetector(
                    config=self.config.wake_word,
                    on_wake=self._on_wake_word_detected,
                )
                if not self._wake_word.is_available:
                    # Wake word model failed to load - enter degraded mode
                    if self.config.degraded_mode.skip_wake_word_on_failure:
                        self._recovery.enter_degraded_mode(
                            "wake_word",
                            reason="Wake word model unavailable, switching to direct speech mode",
                        )
                        logger.warning(
                            "wake_word_degraded_mode",
                            msg="Will skip wake word detection",
                        )
                    else:
                        logger.error("wake_word_init_failed_no_fallback")
                        return False
            except Exception as e:
                # Exception during wake word init - try to degrade
                if self.config.degraded_mode.skip_wake_word_on_failure:
                    self._recovery.enter_degraded_mode(
                        "wake_word", reason=f"Wake word init error: {e}"
                    )
                    logger.warning(
                        "wake_word_init_exception_degraded",
                        error=str(e),
                        msg="Entering direct speech mode",
                    )
                    self._wake_word = None
                else:
                    logger.error("wake_word_init_exception", error=str(e))
                    return False

        # Initialize VAD with energy-based fallback support
        try:
            self._vad = VoiceActivityDetector(
                config=self.config.vad,
                on_speech_start=self._on_speech_start,
                on_speech_end=self._on_speech_end,
            )
            # VAD falls back to energy-based detection if Silero model fails to load
            # (indicated by _model being None)
            if self._vad._model is None:
                self._recovery.enter_degraded_mode(
                    "vad", reason="Silero VAD unavailable, using energy-based fallback"
                )
        except Exception as e:
            if self.config.degraded_mode.use_energy_vad_fallback:
                # VAD will use energy fallback internally, but we track it
                self._recovery.enter_degraded_mode("vad", reason=f"VAD init error: {e}")
                logger.warning(
                    "vad_init_exception_degraded",
                    error=str(e),
                    msg="VAD will use energy fallback",
                )
            else:
                logger.error("vad_init_exception", error=str(e))
                return False

        # Initialize OpenAI Realtime client (required - cannot degrade)
        self._realtime = OpenAIRealtimeClient(
            config=self.config.realtime,
            on_audio_amplitude=self._on_audio_amplitude,
            on_transcription=self._on_transcription_received,
        )

        if not self._realtime.is_available:
            logger.error("openai_realtime_not_available")
            if self.on_error_message:
                self.on_error_message("OpenAI Realtime API not available")
            return False

        # Log initialization status including any degraded modes
        logger.info(
            "voice_pipeline_initialized",
            wake_word_enabled=self.config.wake_word_enabled
            and not self._recovery.is_degraded("wake_word"),
            wake_word_model=self._wake_word.model_name
            if self._wake_word and self._wake_word.is_available
            else None,
            degraded_modes=list(self._recovery.degraded_modes),
            is_degraded=self.is_degraded,
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

        # Enable voice mode on agent - skips speak tool (pipeline handles TTS)
        if self.agent is not None:
            self.agent.set_voice_mode(True)
            logger.info("voice_mode_enabled", reason="pipeline handles TTS directly")

        self._is_running = True
        self._set_state(VoicePipelineState.LISTENING_WAKE)

        # Start main loop
        self._main_task = asyncio.create_task(self._run_loop())
        logger.info("voice_pipeline_started")

    async def stop(self) -> None:
        """Stop the voice pipeline."""
        self._is_running = False

        # Cancel timeout guard task
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._timeout_task
            self._timeout_task = None

        if self._main_task:
            self._main_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._main_task
            self._main_task = None

        # Disable voice mode on agent
        if self.agent is not None:
            self.agent.set_voice_mode(False)
            logger.info("voice_mode_disabled")

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
        # Resume idle behavior when returning to wake word listening
        # This resumes the natural look-around behavior after a conversation
        await self._resume_idle_behavior()

        # Skip wake word if unavailable or in degraded mode (direct speech mode)
        if (
            not self._wake_word
            or not self._wake_word.is_available
            or self._recovery.is_degraded("wake_word")
        ):
            # Direct speech mode - go directly to listening
            self._set_state(VoicePipelineState.LISTENING_SPEECH)
            return

        # Wait if we're in the cooldown period after speaking
        # This prevents the microphone from picking up Reachy's own voice
        if self._is_speaking:
            logger.debug("wake_word_suppressed_during_speech")
            await asyncio.sleep(0.5)
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

                # Skip wake word detection if speaking (acoustic echo suppression)
                if self._is_speaking:
                    continue

                detected_model = self._wake_word.process_audio(chunk)
                if detected_model:
                    # Call the callback with the detected model name
                    # (this queues persona switch and sets state)
                    self._on_wake_word_detected(detected_model)
                    break

        finally:
            await self._audio.stop_recording()

    async def _handle_wake_detected(self) -> None:
        """Handle wake word detection."""
        # Start latency tracking for this conversation turn
        self._wake_time = time.monotonic()
        logger.info("latency_wake_detected", timestamp=self._wake_time)

        # Signal to agent that we're listening
        if self.agent:
            self.agent.set_listening_state(True)

        # Perform a quick "listening" motion to acknowledge wake word
        # Antenna perk-up provides immediate visual feedback
        await self._perform_wake_motion()

        # Optional confirmation beep
        if self.config.confirmation_beep:
            # TODO: Play a confirmation sound
            pass

        self._set_state(VoicePipelineState.LISTENING_SPEECH)

    async def _listen_for_speech(self) -> None:
        """Listen for user speech and detect end-of-speech.

        This method handles WebSocket connection issues mid-stream by buffering
        all audio locally. If the connection dies during recording, we reconnect
        and replay all buffered audio to the new connection before committing.

        Manual VAD mode flow (since we disabled server VAD):
        1. Clear any stale audio from previous session
        2. Send audio chunks as user speaks
        3. Use local VAD to detect end-of-speech
        4. Commit buffer to trigger transcription
        """
        logger.info("listening_for_speech_starting")

        # Ensure OpenAI Realtime connection is active before listening
        # (it may have timed out during previous TTS playback or Claude processing)
        if not await self._realtime.ensure_connected():
            logger.error("listen_for_speech_connection_failed")
            self._set_state(VoicePipelineState.ERROR)
            return

        # CRITICAL: Clear any stale audio buffer from previous interactions
        # This is required for manual VAD mode per OpenAI documentation
        await self._realtime.clear_audio_buffer()
        logger.debug("audio_buffer_cleared_for_new_recording")

        # Start recording
        await self._audio.start_recording()

        # Reset VAD state
        self._vad.reset()

        speech_chunks: list[bytes] = []
        connection_died = False
        chunks_sent = 0

        try:
            async for chunk in self._audio.read_audio_stream():
                if not self._is_running:
                    break

                # Collect audio for local processing FIRST (before sending)
                # This ensures we have all audio even if connection dies
                speech_chunks.append(chunk)

                # Send audio to OpenAI Realtime for transcription
                # send_audio returns False if connection is dead
                if not connection_died:
                    success = await self._realtime.send_audio(chunk)
                    if success:
                        chunks_sent += 1
                    else:
                        connection_died = True
                        logger.warning(
                            "connection_died_mid_recording",
                            chunks_buffered=len(speech_chunks),
                            chunks_sent=chunks_sent,
                        )

                # Check for end of speech
                state = self._vad.process_audio(chunk)
                if state.name == "END_OF_SPEECH":
                    # Track end-of-speech latency
                    self._speech_end_time = time.monotonic()
                    since_wake_ms = (self._speech_end_time - self._wake_time) * 1000 if self._wake_time > 0 else 0
                    logger.info(
                        "latency_speech_ended",
                        timestamp=self._speech_end_time,
                        since_wake_ms=round(since_wake_ms, 1),
                        total_chunks=len(speech_chunks),
                        chunks_sent=chunks_sent,
                        connection_died=connection_died,
                    )
                    break

        finally:
            await self._audio.stop_recording()

        logger.info(
            "speech_recording_complete",
            total_chunks=len(speech_chunks),
            chunks_sent=chunks_sent,
            connection_died=connection_died,
        )

        # If connection died mid-stream, reconnect and replay all buffered audio
        if connection_died and speech_chunks:
            logger.info(
                "replaying_buffered_audio",
                chunks=len(speech_chunks),
            )
            if await self._realtime.ensure_connected():
                success = await self._realtime.send_audio_batch(speech_chunks)
                if success:
                    logger.info("buffered_audio_replayed")
                else:
                    logger.error("buffered_audio_replay_failed")
            else:
                logger.error("reconnect_failed_after_connection_death")
                self._set_state(VoicePipelineState.ERROR)
                return

        self._set_state(VoicePipelineState.PROCESSING)

    async def _process_speech(self) -> None:
        """Process transcribed speech through Claude agent.

        In manual VAD mode, we must commit the audio buffer to trigger
        transcription. The transcription runs asynchronously and returns
        via the conversation.item.input_audio_transcription.completed event.
        """
        logger.info("processing_speech_committing_audio")

        # Commit audio buffer to trigger transcription
        # This is required since we use manual VAD mode (turn_detection: null)
        await self._realtime.commit_audio()
        logger.debug("audio_committed_waiting_for_transcription")

        # Wait for transcription from OpenAI with timeout
        transcript = ""
        try:
            async with asyncio.timeout(15.0):  # 15 second timeout for transcription
                async for event_type, data in self._realtime.process_events():
                    if event_type == "transcription":
                        transcript = data or ""
                        break
                    elif event_type == "error":
                        logger.error("transcription_error", error=data)
                        self._set_state(VoicePipelineState.ERROR)
                        return
        except TimeoutError:
            logger.warning("transcription_timeout", msg="No transcription received within 15s")
            self._restart_listening()
            return

        if not transcript.strip():
            logger.info("empty_transcription")
            self._restart_listening()
            return

        # Track transcription latency
        self._transcription_time = time.monotonic()
        since_speech_end_ms = (self._transcription_time - self._speech_end_time) * 1000 if self._speech_end_time > 0 else 0
        logger.info(
            "latency_transcription_received",
            timestamp=self._transcription_time,
            since_speech_end_ms=round(since_speech_end_ms, 1),
            text=transcript,
        )

        if self.on_transcription:
            self.on_transcription(transcript)

        # Send to Claude agent
        if self.agent:
            try:
                response = await self.agent.process_input(transcript)
                response_text = response.text if response else ""

                # Get any captured speak tool text (verbatim content Claude wanted to say)
                speak_text = self.agent.get_voice_mode_speak_text()
                if speak_text:
                    logger.info(
                        "voice_mode_speak_text_prepending",
                        speak_text_length=len(speak_text),
                        response_text_length=len(response_text) if response_text else 0,
                    )
                    # Speak the verbatim content first, then the conversational response
                    if response_text:
                        response_text = f"{speak_text} {response_text}"
                    else:
                        response_text = speak_text

                if response_text:
                    # Track agent response latency
                    self._response_time = time.monotonic()
                    since_transcription_ms = (self._response_time - self._transcription_time) * 1000 if self._transcription_time > 0 else 0
                    logger.info(
                        "latency_response_received",
                        timestamp=self._response_time,
                        since_transcription_ms=round(since_transcription_ms, 1),
                        text_length=len(response_text),
                    )
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

    async def _play_response(self) -> None:
        """Play TTS response through speaker."""
        if not self._pending_response:
            self._restart_listening()
            return

        # Track TTS start latency (total time from wake word to first audio)
        self._tts_start_time = time.monotonic()
        since_response_ms = (self._tts_start_time - self._response_time) * 1000 if self._response_time > 0 else 0
        total_ms = (self._tts_start_time - self._wake_time) * 1000 if self._wake_time > 0 else 0
        logger.info(
            "latency_tts_started",
            timestamp=self._tts_start_time,
            since_response_ms=round(since_response_ms, 1),
            total_wake_to_tts_ms=round(total_ms, 1),
            text_length=len(self._pending_response),
            text_preview=self._pending_response[:50] + "..." if len(self._pending_response) > 50 else self._pending_response,
        )

        # Set speaking flag to suppress wake word detection (acoustic echo suppression)
        self._is_speaking = True

        try:
            # Collect all TTS audio chunks first, then play
            # OpenAI returns 24kHz audio, we need to resample or play at correct rate
            audio_chunks: list[bytes] = []
            chunk_count = 0
            tts_collect_start = time.monotonic()

            async for chunk in self._realtime.speak(self._pending_response):
                if chunk:
                    audio_chunks.append(chunk)
                    chunk_count += 1
                    # Log progress every 20 chunks to show audio is streaming
                    if chunk_count % 20 == 0:
                        logger.info(
                            "tts_collecting_chunks",
                            chunks_so_far=chunk_count,
                            bytes_so_far=sum(len(c) for c in audio_chunks),
                        )

            collect_time = time.monotonic() - tts_collect_start

            if audio_chunks:
                # Combine all chunks into one buffer
                full_audio = b"".join(audio_chunks)
                # Calculate expected duration: 24kHz, 16-bit mono = 48000 bytes/sec
                expected_duration_s = len(full_audio) / 48000
                logger.info(
                    "tts_audio_collected",
                    chunks=chunk_count,
                    total_bytes=len(full_audio),
                    collect_time_s=round(collect_time, 2),
                    expected_duration_s=round(expected_duration_s, 2),
                )

                # Play the combined audio at 24kHz (OpenAI's output rate)
                play_start = time.monotonic()
                await self._play_audio_24k(full_audio)
                play_time = time.monotonic() - play_start
                logger.info(
                    "tts_playback_complete",
                    play_time_s=round(play_time, 2),
                    expected_s=round(expected_duration_s, 2),
                )
            else:
                logger.warning("no_tts_audio_received", collect_time_s=round(collect_time, 2))

        except Exception as e:
            logger.error("tts_playback_error", error=str(e))

        finally:
            self._pending_response = ""

            # Signal to agent that we're done speaking
            if self.agent:
                self.agent.set_listening_state(False)

            # Add cooldown period after speaking to let audio settle
            # before re-enabling wake word detection
            logger.debug("speech_cooldown_starting")
            await asyncio.sleep(1.5)  # 1.5 second cooldown for acoustic echo to clear
            self._is_speaking = False
            logger.debug("speech_cooldown_complete")

            # CRITICAL: Reset wake word model state after TTS playback
            # This prevents false triggers from residual activation in the model's
            # internal buffers (OpenWakeWord maintains state across audio chunks)
            # We use preserve_cooldown=True to keep the detection cooldown active,
            # preventing immediate re-triggers from speaker echo/reverb
            if self._wake_word:
                self._wake_word.reset(preserve_cooldown=True)
                # Set fresh cooldown time to prevent false triggers
                # (use module-level time import - no local import to avoid scope issues)
                self._wake_word._last_detection_time = time.time()
                logger.info("wake_word_model_reset_after_tts", cooldown_active=True)

            # Apply pending persona switch AFTER response completes
            # This ensures the current response finishes with the current voice
            # before switching to the new persona
            if self._pending_persona and self._pending_persona != self._current_persona:
                await self._switch_persona(self._pending_persona)
                self._pending_persona = None

            self._restart_listening()

    async def _play_audio_24k(self, audio_data: bytes) -> None:
        """Play audio data from OpenAI (24kHz) through hardware (16kHz).

        OpenAI Realtime API outputs PCM16 audio at 24kHz, but the Reachy Mini
        USB Audio hardware only supports 16kHz. This method resamples the audio
        before playback.

        IMPORTANT: We prepend 200ms of silence before the actual audio to give
        PyAudio time to initialize the stream. Without this, the first 100-300ms
        of audio is often cut off (the "buffer warmup" problem).
        """
        if not self._audio or not self._audio._pyaudio:
            logger.warning("audio_manager_not_available")
            return

        import asyncio

        import numpy as np
        import pyaudio

        def _resample_and_play() -> None:
            import time as time_module

            # Resample from 24kHz to 16kHz for Reachy Mini hardware
            samples = np.frombuffer(audio_data, dtype=np.int16)
            if len(samples) == 0:
                logger.warning("playback_empty_audio_buffer")
                return

            # Linear interpolation resampling: 24kHz -> 16kHz (ratio 2/3)
            ratio = 16000 / 24000
            new_length = int(len(samples) * ratio)
            indices = np.linspace(0, len(samples) - 1, new_length)
            resampled = np.interp(indices, np.arange(len(samples)), samples)
            resampled_int16 = resampled.astype(np.int16)

            # CRITICAL: Prepend 500ms of silence to prevent beginning cutoff
            # PyAudio + Reachy Mini USB audio needs time to initialize the stream;
            # without this lead-in, the first 200-500ms of audio is often inaudible
            # ("buffer warmup" problem). Increased from 200ms to 500ms based on testing.
            silence_duration_ms = 500
            silence_samples = int(16000 * silence_duration_ms / 1000)  # 8000 samples at 16kHz
            silence = np.zeros(silence_samples, dtype=np.int16)

            # Combine silence + actual audio
            audio_with_leadin = np.concatenate([silence, resampled_int16])
            resampled_bytes = audio_with_leadin.tobytes()

            logger.info(
                "audio_prepended_silence",
                silence_ms=silence_duration_ms,
                silence_samples=silence_samples,
            )

            # Calculate expected playback duration
            expected_duration_s = len(resampled_bytes) / (16000 * 2)  # 16kHz, 16-bit
            logger.info(
                "audio_playback_starting",
                original_samples=len(samples),
                resampled_samples=new_length,
                resampled_bytes=len(resampled_bytes),
                expected_duration_s=round(expected_duration_s, 2),
            )

            # Play at 16kHz (Reachy Mini hardware rate)
            stream = self._audio._pyaudio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,  # Reachy Mini Audio hardware rate
                output=True,
                output_device_index=self._audio.config.output_device_index,
            )
            try:
                play_start = time_module.time()
                stream.write(resampled_bytes)
                play_end = time_module.time()
                logger.info(
                    "audio_playback_finished",
                    actual_duration_s=round(play_end - play_start, 2),
                    expected_duration_s=round(expected_duration_s, 2),
                )
            finally:
                stream.stop_stream()
                stream.close()

        await asyncio.get_event_loop().run_in_executor(None, _resample_and_play)

    async def _handle_error(self) -> None:
        """Handle error state."""
        logger.warning("voice_pipeline_error_state")
        await asyncio.sleep(2.0)  # Brief pause before restart

        if self.config.auto_restart:
            self._set_state(VoicePipelineState.LISTENING_WAKE)
        else:
            self._is_running = False

    def _restart_listening(self) -> None:
        """Restart the listening loop.

        Chooses wake word or direct speech mode based on:
        - config.wake_word_enabled setting
        - Whether wake word is in degraded mode (unavailable)
        """
        if self.config.auto_restart and self._is_running:
            # Use wake word only if enabled AND not in degraded mode
            wake_word_active = (
                self.config.wake_word_enabled
                and not self._recovery.is_degraded("wake_word")
            )
            if wake_word_active:
                self._set_state(VoicePipelineState.LISTENING_WAKE)
            else:
                self._set_state(VoicePipelineState.LISTENING_SPEECH)
        else:
            self._set_state(VoicePipelineState.IDLE)

    def _set_state(self, new_state: VoicePipelineState) -> None:
        """Update pipeline state with validation, locking, and timeout guards.

        This method:
        1. Validates the transition is allowed by VALID_TRANSITIONS matrix
        2. Cancels any existing timeout guard task
        3. Updates state and records entry time
        4. Starts a new timeout guard if the state has a timeout
        5. Calls the state change callback

        Invalid transitions are logged as warnings but not blocked to avoid
        deadlocks. In production, these logs indicate programming errors.
        """
        old_state = self._state

        # Validate transition (warn but don't block to avoid deadlocks)
        valid_targets = VALID_TRANSITIONS.get(old_state, set())
        if new_state not in valid_targets:
            logger.warning(
                "invalid_state_transition",
                from_state=old_state.value,
                to_state=new_state.value,
                valid_targets=[s.value for s in valid_targets],
            )
            # Continue anyway - blocking could cause deadlock

        # Cancel existing timeout guard
        if self._timeout_task and not self._timeout_task.done():
            self._timeout_task.cancel()
            self._timeout_task = None

        # Update state
        self._state = new_state
        self._state_entered_at = time.monotonic()

        logger.debug(
            "state_changed",
            old_state=old_state.value,
            new_state=new_state.value,
        )

        # Start timeout guard for this state if it has a timeout
        timeout = STATE_TIMEOUTS.get(new_state)
        if timeout and self._is_running:
            self._timeout_task = asyncio.create_task(
                self._state_timeout_guard(new_state, timeout)
            )

        if self.on_state_change:
            self.on_state_change(new_state)

    async def _state_timeout_guard(
        self, expected_state: VoicePipelineState, timeout: float
    ) -> None:
        """Background task that forces state recovery if state times out.

        This prevents the pipeline from getting stuck indefinitely in any
        state. If the state changes before timeout, this task is cancelled.

        For ERROR state, we recover to LISTENING_WAKE (auto-heal).
        For other states, we transition to ERROR first.

        Args:
            expected_state: The state we expect to still be in
            timeout: Seconds before triggering timeout
        """
        try:
            await asyncio.sleep(timeout)

            # Only trigger timeout if we're still in the expected state
            if self._state == expected_state and self._is_running:
                logger.error(
                    "state_timeout",
                    state=expected_state.value,
                    timeout_seconds=timeout,
                    time_in_state=time.monotonic() - self._state_entered_at,
                )

                # For ERROR state, auto-recover to LISTENING_WAKE
                # This prevents the pipeline from getting stuck in error loops
                if expected_state == VoicePipelineState.ERROR:
                    logger.info("auto_recovering_from_error_state")
                    self._set_state(VoicePipelineState.LISTENING_WAKE)
                else:
                    self._set_state(VoicePipelineState.ERROR)

        except asyncio.CancelledError:
            # Task was cancelled because state changed - this is normal
            pass

    async def _perform_wake_motion(self) -> None:
        """Perform a quick motion to acknowledge wake word detection.

        Creates visible feedback when the robot hears the wake word:
        1. Pauses idle behavior to stop random movements
        2. Moves head to neutral + slight upward tilt (attentive)
        3. Perks up both antennas (alert/listening pose)

        Uses fire-and-forget to avoid blocking the state transition.
        """
        if not self.agent or not hasattr(self.agent, "_daemon_client"):
            logger.debug("wake_motion_skipped", reason="no daemon client")
            return

        daemon_client = self.agent._daemon_client
        if daemon_client is None:
            logger.debug("wake_motion_skipped", reason="daemon client not initialized")
            return

        try:
            # Pause idle behavior so the wake motion is clearly visible
            if hasattr(self.agent, "_idle_controller") and self.agent._idle_controller:
                await self.agent._idle_controller.pause()
                logger.debug("wake_motion_idle_paused")

            # Send a combined "attentive" pose:
            # - Head: neutral yaw/roll, slight upward pitch (looking at speaker)
            # - Antennas: both perked up high (alert/listening)
            asyncio.create_task(
                daemon_client.set_full_pose(
                    roll=0.0,
                    pitch=8.0,  # Slight upward tilt - attentive
                    yaw=0.0,  # Face forward
                    left_antenna=85.0,  # Perked up (90 = max vertical)
                    right_antenna=85.0,
                )
            )
            logger.info("wake_motion_triggered", motion="attentive_pose")

        except Exception as e:
            # Don't let motion failures break the pipeline
            logger.warning("wake_motion_failed", error=str(e))

    async def _resume_idle_behavior(self) -> None:
        """Resume idle behavior when returning to wake word listening.

        This restores the natural look-around behavior after a conversation
        ends and the robot goes back to waiting for the wake word.
        """
        if not self.agent:
            return

        try:
            # Resume idle behavior
            if hasattr(self.agent, "_idle_controller") and self.agent._idle_controller:
                await self.agent._idle_controller.resume()
                logger.debug("idle_behavior_resumed")

            # Signal to agent that we're no longer listening
            if hasattr(self.agent, "set_listening_state"):
                self.agent.set_listening_state(False)

        except Exception as e:
            # Don't let this break the pipeline
            logger.warning("resume_idle_behavior_failed", error=str(e))

    def _on_wake_word_detected(self, detected_model: str) -> None:
        """Callback when wake word is detected.

        Queues persona switch if a different persona's wake word was detected.
        The actual switch happens after the current response completes.

        Args:
            detected_model: Name of the wake word model that triggered
                           (e.g., "hey_motoko", "hey_batou")
        """
        if self._state == VoicePipelineState.LISTENING_WAKE:
            # Check if this triggers a persona switch
            if self.config.persona_manager:
                new_persona = self.config.persona_manager.get_persona(detected_model)
                if new_persona and new_persona != self._current_persona:
                    # Queue the switch for after response completes
                    self._pending_persona = new_persona
                    logger.info(
                        "persona_switch_queued",
                        from_persona=self._current_persona.name if self._current_persona else None,
                        to_persona=new_persona.name,
                        wake_word=detected_model,
                    )

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
