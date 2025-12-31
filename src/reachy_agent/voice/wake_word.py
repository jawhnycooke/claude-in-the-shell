"""Wake word detector for Reachy voice pipeline.

Detects "Hey Jarvis" trigger phrase using OpenWakeWord library.
Runs continuously in low-power mode until wake phrase is detected.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from openwakeword.model import Model as OWWModel

logger = structlog.get_logger(__name__)


# Available wake word models
# OpenWakeWord bundled models - "Hey Jarvis" is our primary wake word
# Priority order - we'll try each until one loads
WAKE_WORD_MODELS = [
    "hey_jarvis",  # Primary wake word - "Hey Jarvis" activates the robot
    "alexa",  # Fallback
    "hey_mycroft",  # Another assistant wake word
]


@dataclass
class WakeWordConfig:
    """Wake word detection configuration."""

    model_name: str = "hey_jarvis"  # Wake word: "Hey Jarvis"
    sensitivity: float = 0.5  # 0.0 (strict) to 1.0 (lenient)
    chunk_size: int = 1280  # Samples per chunk (80ms at 16kHz)
    sample_rate: int = 16000
    cooldown_seconds: float = 2.0  # Ignore detections for this long after trigger


@dataclass
class WakeWordDetector:
    """Detects wake word in audio stream.

    Uses OpenWakeWord for efficient wake word detection.
    Designed to run continuously with minimal CPU usage.
    """

    config: WakeWordConfig = field(default_factory=WakeWordConfig)
    on_wake: Callable[[], None] | None = None
    _model: OWWModel | None = field(default=None, repr=False)
    _is_running: bool = field(default=False, repr=False)
    _last_detection_time: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        """Initialize the wake word model."""
        self._load_model()

    def _load_model(self) -> None:
        """Load the OpenWakeWord model.

        OpenWakeWord 0.4.0 changed its API:
        - Model() with no args loads all default models (alexa, hey_mycroft, hey_jarvis, etc.)
        - We filter predictions at detection time to only respond to configured model
        """
        try:
            from openwakeword.model import Model

            # Load model with default bundled wake words
            # The new API loads all models; we filter by config.model_name at prediction time
            try:
                self._model = Model()

                # Verify our preferred model is available
                available_models = list(self._model.models.keys())
                if self.config.model_name in available_models:
                    logger.info(
                        "wake_word_model_loaded",
                        model=self.config.model_name,
                        all_available=available_models,
                        sensitivity=self.config.sensitivity,
                    )
                else:
                    # Fall back to first available model from our preference list
                    for fallback in WAKE_WORD_MODELS:
                        if fallback in available_models:
                            self.config.model_name = fallback
                            logger.info(
                                "wake_word_model_fallback",
                                model=fallback,
                                all_available=available_models,
                                sensitivity=self.config.sensitivity,
                            )
                            break
                    else:
                        # Use first available if none match
                        if available_models:
                            self.config.model_name = available_models[0]
                            logger.info(
                                "wake_word_model_default",
                                model=self.config.model_name,
                                all_available=available_models,
                            )
                        else:
                            logger.warning("no_wake_word_model_available")
                            self._model = None

            except Exception as e:
                logger.warning(
                    "wake_word_model_load_failed",
                    error=str(e),
                )
                self._model = None

        except ImportError:
            logger.warning(
                "openwakeword_not_installed",
                msg="Wake word detection unavailable",
            )
            self._model = None

    @property
    def is_available(self) -> bool:
        """Check if wake word detection is available."""
        return self._model is not None

    @property
    def model_name(self) -> str | None:
        """Get the loaded model name."""
        if self._model:
            return list(self._model.models.keys())[0]
        return None

    def process_audio(self, audio_data: bytes) -> bool:
        """Process audio chunk and check for wake word.

        Args:
            audio_data: Raw PCM audio bytes (int16, 16kHz, mono)

        Returns:
            True if wake word was detected
        """
        if not self._model:
            return False

        import time

        # Check cooldown
        current_time = time.time()
        if current_time - self._last_detection_time < self.config.cooldown_seconds:
            return False

        # Convert bytes to numpy array
        samples = np.frombuffer(audio_data, dtype=np.int16)

        # Run prediction
        predictions = self._model.predict(samples)

        # Only check the configured model's score (not all models)
        threshold = 1.0 - self.config.sensitivity
        if self.config.model_name in predictions:
            score = predictions[self.config.model_name]
            if score > threshold:
                logger.info(
                    "wake_word_detected",
                    model=self.config.model_name,
                    score=score,
                    threshold=threshold,
                )
                self._last_detection_time = current_time
                return True

        return False

    async def listen(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> None:
        """Listen to audio stream for wake word.

        Args:
            audio_stream: Async iterator yielding audio chunks

        Calls on_wake callback when wake word is detected.
        """
        if not self._model:
            logger.error("wake_word_model_not_loaded")
            return

        self._is_running = True
        logger.info("wake_word_listening_started", model=self.model_name)

        try:
            async for chunk in audio_stream:
                if not self._is_running:
                    break

                detected = self.process_audio(chunk)
                if detected and self.on_wake:
                    # Run callback without blocking
                    asyncio.create_task(self._trigger_wake())

        finally:
            self._is_running = False
            logger.info("wake_word_listening_stopped")

    async def _trigger_wake(self) -> None:
        """Trigger the wake callback."""
        if self.on_wake:
            if asyncio.iscoroutinefunction(self.on_wake):
                await self.on_wake()
            else:
                self.on_wake()

    def stop(self) -> None:
        """Stop listening for wake word."""
        self._is_running = False

    def reset(self, preserve_cooldown: bool = False) -> None:
        """Reset detection state.

        Args:
            preserve_cooldown: If True, don't reset the last detection time.
                              This is useful after TTS playback to prevent
                              immediate re-triggers from echo/reverb.
        """
        if self._model:
            self._model.reset()
        if not preserve_cooldown:
            self._last_detection_time = 0.0
