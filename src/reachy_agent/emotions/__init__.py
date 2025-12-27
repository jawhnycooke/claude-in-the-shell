"""Local emotions library for offline emotion playback.

This package provides access to bundled emotion data from the
pollen-robotics/reachy-mini-emotions-library HuggingFace dataset.
"""

from reachy_agent.emotions.loader import (
    EmotionData,
    EmotionLoader,
    HeadPoseDict,
    Keyframe,
    KeyframeValidationError,
)

__all__ = [
    "EmotionLoader",
    "EmotionData",
    "Keyframe",
    "KeyframeValidationError",
    "HeadPoseDict",
]
