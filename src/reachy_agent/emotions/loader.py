"""Load and cache emotion data from local JSON files.

This module provides the EmotionLoader class for loading bundled emotion data
from the data/emotions/ directory, enabling offline playback without requiring
HuggingFace downloads at runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


class HeadPoseDict(TypedDict):
    """Type definition for head pose angles in radians."""

    roll: float
    pitch: float
    yaw: float


class KeyframeValidationError(ValueError):
    """Raised when keyframe data is invalid."""

    pass


@dataclass(frozen=True)
class Keyframe:
    """Single keyframe in an emotion animation.

    Attributes:
        time_ms: Time offset from start in milliseconds (>= 0).
        head: Head pose with roll, pitch, yaw in radians.
        antennas: Antenna angles [left, right] in radians.
        body_yaw: Body rotation in radians.

    Note:
        body_yaw is stored but not currently applied during playback.
        The daemon's /api/move/goto endpoint doesn't support body rotation.
        This data is preserved for future use when body rotation is supported.
    """

    time_ms: float
    head: HeadPoseDict
    antennas: tuple[float, float]  # Immutable tuple instead of list
    body_yaw: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Keyframe:
        """Create a Keyframe from a dictionary.

        Args:
            data: Dictionary containing keyframe data with required keys:
                - time_ms: Time offset in milliseconds
                - head: Dict with roll, pitch, yaw keys
                - antennas: List/tuple of 2 floats [left, right]
                - body_yaw: Body rotation in radians

        Returns:
            Validated Keyframe instance.

        Raises:
            KeyframeValidationError: If required fields are missing or invalid.
        """
        # Validate required fields
        required_fields = ["time_ms", "head", "antennas", "body_yaw"]
        missing = [f for f in required_fields if f not in data]
        if missing:
            raise KeyframeValidationError(f"Missing required fields: {missing}")

        # Validate time_ms
        time_ms = data["time_ms"]
        if not isinstance(time_ms, (int, float)) or time_ms < 0:
            raise KeyframeValidationError(
                f"time_ms must be a non-negative number, got: {time_ms}"
            )

        # Validate head pose
        head = data["head"]
        if not isinstance(head, dict):
            raise KeyframeValidationError(f"head must be a dict, got: {type(head)}")
        for key in ("roll", "pitch", "yaw"):
            if key not in head:
                raise KeyframeValidationError(f"head missing required key: {key}")
            if not isinstance(head[key], (int, float)):
                raise KeyframeValidationError(
                    f"head.{key} must be a number, got: {type(head[key])}"
                )

        # Validate antennas
        antennas = data["antennas"]
        if not isinstance(antennas, (list, tuple)) or len(antennas) != 2:
            raise KeyframeValidationError(
                f"antennas must be a list/tuple of 2 floats, got: {antennas}"
            )
        for i, val in enumerate(antennas):
            if not isinstance(val, (int, float)):
                raise KeyframeValidationError(
                    f"antennas[{i}] must be a number, got: {type(val)}"
                )

        # Validate body_yaw
        body_yaw = data["body_yaw"]
        if not isinstance(body_yaw, (int, float)):
            raise KeyframeValidationError(
                f"body_yaw must be a number, got: {type(body_yaw)}"
            )

        # Create typed head dict
        head_typed: HeadPoseDict = {
            "roll": float(head["roll"]),
            "pitch": float(head["pitch"]),
            "yaw": float(head["yaw"]),
        }

        return cls(
            time_ms=float(time_ms),
            head=head_typed,
            antennas=(float(antennas[0]), float(antennas[1])),
            body_yaw=float(body_yaw),
        )


@dataclass(frozen=True)
class EmotionData:
    """Complete emotion animation data.

    Attributes:
        name: Emotion name (e.g., "curious1", "cheerful1").
        description: Human-readable description of the emotion.
        duration_ms: Total animation duration in milliseconds.
        keyframes: Tuple of animation keyframes (immutable).
        audio_file: Path to audio file, if available.
    """

    name: str
    description: str
    duration_ms: float
    keyframes: tuple[Keyframe, ...] = field(default_factory=tuple)
    audio_file: Path | None = None

    @classmethod
    def from_file(cls, json_path: Path) -> EmotionData:
        """Load emotion data from a JSON file.

        Args:
            json_path: Path to the emotion JSON file.

        Returns:
            EmotionData instance with loaded keyframes.

        Raises:
            FileNotFoundError: If the JSON file doesn't exist.
            json.JSONDecodeError: If the file contains invalid JSON.
            KeyError: If required fields are missing.
            KeyframeValidationError: If keyframe data is invalid.
        """
        with open(json_path) as f:
            data = json.load(f)

        # Convert list to immutable tuple
        keyframes = tuple(Keyframe.from_dict(kf) for kf in data.get("keyframes", []))

        # Check for audio file
        audio_path = json_path.with_suffix(".wav")
        audio_file = audio_path if audio_path.exists() else None

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            duration_ms=data["duration_ms"],
            keyframes=keyframes,
            audio_file=audio_file,
        )


class EmotionLoader:
    """Load and cache emotion data from local files.

    The loader reads from data/emotions/ directory and caches loaded emotions
    in memory for fast repeated access.

    Example:
        loader = EmotionLoader()

        # List available emotions
        emotions = loader.list_emotions()
        dances = loader.list_dances()

        # Load a specific emotion
        emotion = loader.get_emotion("curious1")
        if emotion:
            for keyframe in emotion.keyframes:
                print(f"Time: {keyframe.time_ms}ms, Yaw: {keyframe.head['yaw']}")
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        """Initialize the emotion loader.

        Args:
            data_dir: Path to emotions data directory. If None, uses the default
                     location at data/emotions/ relative to project root.
        """
        if data_dir is None:
            # Default to data/emotions/ in project root
            data_dir = Path(__file__).parent.parent.parent.parent / "data" / "emotions"

        self._data_dir = data_dir
        self._cache: dict[str, EmotionData] = {}
        self._manifest: dict[str, Any] | None = None

    @property
    def data_dir(self) -> Path:
        """Path to the emotions data directory."""
        return self._data_dir

    def _load_manifest(self) -> dict[str, Any]:
        """Load and cache the manifest file."""
        if self._manifest is not None:
            return self._manifest

        manifest_path = self._data_dir / "manifest.json"
        if not manifest_path.exists():
            log.warning("Emotion manifest not found", path=str(manifest_path))
            self._manifest = {"emotions": {}, "dances": {}}
            return self._manifest

        with open(manifest_path) as f:
            self._manifest = json.load(f)

        log.debug(
            "Loaded emotion manifest",
            emotions=len(self._manifest.get("emotions", {})),
            dances=len(self._manifest.get("dances", {})),
        )
        return self._manifest

    def list_emotions(self) -> list[str]:
        """List all available emotion names.

        Returns:
            Sorted list of emotion names (e.g., ["amazed1", "cheerful1", ...]).
        """
        manifest = self._load_manifest()
        return sorted(manifest.get("emotions", {}).keys())

    def list_dances(self) -> list[str]:
        """List all available dance names.

        Returns:
            Sorted list of dance names (e.g., ["dance1", "dance2", "dance3"]).
        """
        manifest = self._load_manifest()
        return sorted(manifest.get("dances", {}).keys())

    def list_all(self) -> list[str]:
        """List all available emotions and dances.

        Returns:
            Sorted list of all emotion and dance names.
        """
        return sorted(self.list_emotions() + self.list_dances())

    def has_emotion(self, name: str) -> bool:
        """Check if an emotion exists in the local library.

        Args:
            name: Emotion name to check.

        Returns:
            True if the emotion exists locally, False otherwise.
        """
        manifest = self._load_manifest()
        return name in manifest.get("emotions", {}) or name in manifest.get(
            "dances", {}
        )

    def get_emotion(self, name: str) -> EmotionData | None:
        """Get emotion data by name.

        Loads from cache if previously loaded, otherwise reads from disk.

        Args:
            name: Emotion name (e.g., "curious1", "dance1").

        Returns:
            EmotionData if found, None if emotion doesn't exist.
        """
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        # Check if emotion exists
        if not self.has_emotion(name):
            log.debug("Emotion not found in manifest", name=name)
            return None

        # Load from file
        json_path = self._data_dir / f"{name}.json"
        if not json_path.exists():
            log.warning("Emotion file missing", name=name, path=str(json_path))
            return None

        try:
            emotion = EmotionData.from_file(json_path)
            self._cache[name] = emotion
            log.debug(
                "Loaded emotion",
                name=name,
                duration_ms=emotion.duration_ms,
                keyframes=len(emotion.keyframes),
                has_audio=emotion.audio_file is not None,
            )
            return emotion
        except (json.JSONDecodeError, KeyError) as e:
            log.error("Failed to load emotion", name=name, error=str(e))
            return None

    def get_emotion_info(self, name: str) -> dict[str, Any] | None:
        """Get emotion metadata without loading full keyframe data.

        This is faster than get_emotion() when you only need basic info.

        Args:
            name: Emotion name to look up.

        Returns:
            Dictionary with file, duration_ms, keyframe_count, and optional audio.
            None if emotion doesn't exist.
        """
        manifest = self._load_manifest()

        if name in manifest.get("emotions", {}):
            return manifest["emotions"][name]
        if name in manifest.get("dances", {}):
            return manifest["dances"][name]

        return None

    def clear_cache(self) -> None:
        """Clear the emotion cache to free memory."""
        self._cache.clear()
        log.debug("Cleared emotion cache")

    def preload_all(self) -> int:
        """Preload all emotions into cache.

        Returns:
            Number of emotions successfully loaded.
        """
        loaded = 0
        for name in self.list_all():
            if self.get_emotion(name) is not None:
                loaded += 1
        log.info("Preloaded emotions", count=loaded)
        return loaded


# Module-level singleton for convenience
_default_loader: EmotionLoader | None = None


def get_emotion_loader() -> EmotionLoader:
    """Get the default emotion loader singleton.

    Returns:
        Shared EmotionLoader instance.
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = EmotionLoader()
    return _default_loader
