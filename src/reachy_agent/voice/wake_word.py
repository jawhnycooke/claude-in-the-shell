"""Wake word detector for Reachy voice pipeline.

Detects "Hey Reachy" trigger phrase using OpenWakeWord library.
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


# Available wake word models that could work for "Hey Reachy"
# In priority order - we'll try each until one loads
WAKE_WORD_MODELS = [
    "hey_jarvis",  # Closest phonetically to "Hey Reachy"
    "alexa",  # Common wake word, good fallback
    "hey_mycroft",  # Another assistant wake word
]


@dataclass
class WakeWordConfig:
    """Wake word detection configuration."""

    model_name: str = "hey_jarvis"
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
        """Load the OpenWakeWord model."""
        try:
            from openwakeword.model import Model

            # Try loading configured model first
            models_to_try = [self.config.model_name] + [
                m for m in WAKE_WORD_MODELS if m != self.config.model_name
            ]

            for model_name in models_to_try:
                try:
                    self._model = Model(
                        wakeword_models=[model_name],
                        inference_framework="onnx",
                    )
                    logger.info(
                        "wake_word_model_loaded",
                        model=model_name,
                        sensitivity=self.config.sensitivity,
                    )
                    return
                except Exception as e:
                    logger.debug(
                        "wake_word_model_failed",
                        model=model_name,
                        error=str(e),
                    )
                    continue

            logger.warning("no_wake_word_model_available")

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

        # Check if any model triggered above threshold
        for model_name, score in predictions.items():
            threshold = 1.0 - self.config.sensitivity
            if score > threshold:
                logger.info(
                    "wake_word_detected",
                    model=model_name,
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

    def reset(self) -> None:
        """Reset detection state."""
        if self._model:
            self._model.reset()
        self._last_detection_time = 0.0
