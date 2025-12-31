"""Wake word detector for Reachy voice pipeline.

Detects wake phrases using OpenWakeWord library.
Supports multiple wake words for persona switching (Ghost in the Shell theme).

Runs continuously in low-power mode until wake phrase is detected.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import structlog

if TYPE_CHECKING:
    from openwakeword.model import Model as OWWModel

logger = structlog.get_logger(__name__)


# Available wake word models
# OpenWakeWord bundled models - fallbacks if no custom models provided
# Priority order - we'll try each until one loads
WAKE_WORD_MODELS = [
    "hey_jarvis",  # Primary fallback wake word
    "alexa",  # Fallback
    "hey_mycroft",  # Another assistant wake word
]


@dataclass
class WakeWordConfig:
    """Wake word detection configuration.

    Supports both single wake word (model_name) and multi-persona wake words
    (persona_models) for Ghost in the Shell theme switching.
    """

    model_name: str = "hey_jarvis"  # Fallback wake word if no persona models
    sensitivity: float = 0.5  # 0.0 (strict) to 1.0 (lenient)
    chunk_size: int = 1280  # Samples per chunk (80ms at 16kHz)
    sample_rate: int = 16000
    cooldown_seconds: float = 2.0  # Ignore detections for this long after trigger
    custom_models_dir: str = "data/wake_words"  # Directory for custom .onnx models
    persona_models: list[str] = field(default_factory=list)  # e.g., ["hey_motoko", "hey_batou"]


@dataclass
class WakeWordDetector:
    """Detects wake word in audio stream.

    Uses OpenWakeWord for efficient wake word detection.
    Designed to run continuously with minimal CPU usage.

    Supports multi-persona wake words for Ghost in the Shell theme:
    - "Hey Motoko" → Major Kusanagi persona
    - "Hey Batou" → Batou persona
    """

    config: WakeWordConfig = field(default_factory=WakeWordConfig)
    on_wake: Callable[[str], None] | None = None  # Callback receives detected model name
    _model: OWWModel | None = field(default=None, repr=False)
    _is_running: bool = field(default=False, repr=False)
    _last_detection_time: float = field(default=0.0, repr=False)
    _active_models: list[str] = field(default_factory=list, repr=False)  # Models to check

    def __post_init__(self) -> None:
        """Initialize the wake word model."""
        self._load_model()

    def _load_model(self) -> None:
        """Load the OpenWakeWord model(s).

        Supports two modes:
        1. Persona mode: Load custom .onnx models from custom_models_dir
        2. Fallback mode: Use bundled OpenWakeWord models

        OpenWakeWord 0.4.0+ API:
        - Model(wakeword_models=[...]) loads specific custom models
        - Model() loads all default bundled models
        """
        try:
            from openwakeword.model import Model

            custom_model_paths = self._find_custom_models()

            try:
                if custom_model_paths:
                    # Load custom persona models
                    self._model = Model(wakeword_models=custom_model_paths)
                    self._active_models = [
                        Path(p).stem for p in custom_model_paths
                    ]
                    logger.info(
                        "wake_word_custom_models_loaded",
                        models=self._active_models,
                        paths=custom_model_paths,
                        sensitivity=self.config.sensitivity,
                    )
                else:
                    # Fall back to bundled models
                    self._model = Model()
                    available_models = list(self._model.models.keys())

                    # Use configured model or find fallback
                    if self.config.model_name in available_models:
                        self._active_models = [self.config.model_name]
                    else:
                        # Find first available from preference list
                        for fallback in WAKE_WORD_MODELS:
                            if fallback in available_models:
                                self._active_models = [fallback]
                                break
                        else:
                            self._active_models = available_models[:1] if available_models else []

                    if self._active_models:
                        logger.info(
                            "wake_word_bundled_model_loaded",
                            model=self._active_models[0],
                            all_available=available_models,
                            sensitivity=self.config.sensitivity,
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

    def _find_custom_models(self) -> list[str]:
        """Find custom wake word .onnx models.

        Looks for .onnx files matching persona_models in custom_models_dir.

        Returns:
            List of absolute paths to found model files
        """
        if not self.config.persona_models:
            return []

        custom_dir = Path(self.config.custom_models_dir)
        if not custom_dir.exists():
            logger.debug(
                "custom_models_dir_not_found",
                path=str(custom_dir),
            )
            return []

        found_paths = []
        missing_models = []

        for model_name in self.config.persona_models:
            model_path = custom_dir / f"{model_name}.onnx"
            if model_path.exists():
                found_paths.append(str(model_path.absolute()))
            else:
                missing_models.append(model_name)

        if missing_models:
            logger.warning(
                "custom_wake_word_models_missing",
                missing=missing_models,
                expected_dir=str(custom_dir),
                hint="See data/wake_words/README.md for training instructions",
            )

        return found_paths

    @property
    def is_available(self) -> bool:
        """Check if wake word detection is available."""
        return self._model is not None and len(self._active_models) > 0

    @property
    def model_name(self) -> str | None:
        """Get the primary loaded model name."""
        if self._active_models:
            return self._active_models[0]
        return None

    @property
    def active_models(self) -> list[str]:
        """Get all active model names being listened for."""
        return self._active_models.copy()

    def process_audio(self, audio_data: bytes) -> str | None:
        """Process audio chunk and check for wake words.

        Checks all active models (persona wake words) and returns
        the first one that triggers above threshold.

        Args:
            audio_data: Raw PCM audio bytes (int16, 16kHz, mono)

        Returns:
            Name of detected wake word model, or None if no detection
        """
        if not self._model or not self._active_models:
            return None

        import time

        # Check cooldown
        current_time = time.time()
        if current_time - self._last_detection_time < self.config.cooldown_seconds:
            return None

        # Convert bytes to numpy array
        samples = np.frombuffer(audio_data, dtype=np.int16)

        # Run prediction
        predictions = self._model.predict(samples)

        # Check all active models for detection
        threshold = 1.0 - self.config.sensitivity
        for model_name in self._active_models:
            if model_name in predictions:
                score = predictions[model_name]
                if score > threshold:
                    logger.info(
                        "wake_word_detected",
                        model=model_name,
                        score=score,
                        threshold=threshold,
                    )
                    self._last_detection_time = current_time
                    return model_name

        return None

    async def listen(
        self,
        audio_stream: AsyncIterator[bytes],
    ) -> None:
        """Listen to audio stream for wake word.

        Args:
            audio_stream: Async iterator yielding audio chunks

        Calls on_wake callback with detected model name when wake word is detected.
        """
        if not self._model:
            logger.error("wake_word_model_not_loaded")
            return

        self._is_running = True
        logger.info(
            "wake_word_listening_started",
            models=self._active_models,
            primary=self.model_name,
        )

        try:
            async for chunk in audio_stream:
                if not self._is_running:
                    break

                detected_model = self.process_audio(chunk)
                if detected_model and self.on_wake:
                    # Run callback without blocking, passing detected model name
                    asyncio.create_task(self._trigger_wake(detected_model))

        finally:
            self._is_running = False
            logger.info("wake_word_listening_stopped")

    async def _trigger_wake(self, detected_model: str) -> None:
        """Trigger the wake callback with detected model name.

        Args:
            detected_model: Name of the wake word model that triggered
        """
        if self.on_wake:
            if asyncio.iscoroutinefunction(self.on_wake):
                await self.on_wake(detected_model)
            else:
                self.on_wake(detected_model)

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
