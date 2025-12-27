"""Unit tests for the EmotionLoader class."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from reachy_agent.emotions.loader import (
    EmotionData,
    EmotionLoader,
    Keyframe,
    get_emotion_loader,
)


class TestKeyframe:
    """Tests for the Keyframe dataclass."""

    def test_from_dict(self) -> None:
        """Test creating a keyframe from a dictionary."""
        data = {
            "time_ms": 100.0,
            "head": {"roll": 0.1, "pitch": 0.2, "yaw": 0.3},
            "antennas": [0.5, 0.6],
            "body_yaw": 0.1,
        }

        keyframe = Keyframe.from_dict(data)

        assert keyframe.time_ms == 100.0
        assert keyframe.head["roll"] == 0.1
        assert keyframe.head["pitch"] == 0.2
        assert keyframe.head["yaw"] == 0.3
        assert keyframe.antennas == [0.5, 0.6]
        assert keyframe.body_yaw == 0.1


class TestEmotionData:
    """Tests for the EmotionData dataclass."""

    def test_from_file(self, tmp_path: Path) -> None:
        """Test loading emotion data from a JSON file."""
        # Create a test emotion file
        emotion_data = {
            "name": "test_emotion",
            "description": "A test emotion",
            "duration_ms": 1000.0,
            "keyframes": [
                {
                    "time_ms": 0.0,
                    "head": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "antennas": [0.5, 0.5],
                    "body_yaw": 0.0,
                },
                {
                    "time_ms": 500.0,
                    "head": {"roll": 0.1, "pitch": 0.1, "yaw": 0.1},
                    "antennas": [0.6, 0.4],
                    "body_yaw": 0.05,
                },
            ],
        }

        json_path = tmp_path / "test_emotion.json"
        json_path.write_text(json.dumps(emotion_data))

        emotion = EmotionData.from_file(json_path)

        assert emotion.name == "test_emotion"
        assert emotion.description == "A test emotion"
        assert emotion.duration_ms == 1000.0
        assert len(emotion.keyframes) == 2
        assert emotion.keyframes[0].time_ms == 0.0
        assert emotion.keyframes[1].time_ms == 500.0
        assert emotion.audio_file is None

    def test_from_file_with_audio(self, tmp_path: Path) -> None:
        """Test that audio file is detected when present."""
        emotion_data = {
            "name": "audio_emotion",
            "description": "Emotion with audio",
            "duration_ms": 500.0,
            "keyframes": [],
        }

        json_path = tmp_path / "audio_emotion.json"
        json_path.write_text(json.dumps(emotion_data))

        # Create corresponding audio file
        audio_path = tmp_path / "audio_emotion.wav"
        audio_path.write_bytes(b"fake audio data")

        emotion = EmotionData.from_file(json_path)

        assert emotion.audio_file == audio_path

    def test_from_file_missing_file(self, tmp_path: Path) -> None:
        """Test that FileNotFoundError is raised for missing files."""
        with pytest.raises(FileNotFoundError):
            EmotionData.from_file(tmp_path / "nonexistent.json")


class TestEmotionLoader:
    """Tests for the EmotionLoader class."""

    @pytest.fixture
    def loader_with_data(self, tmp_path: Path) -> EmotionLoader:
        """Create a loader with test data."""
        # Create manifest
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {
                "happy1": {
                    "file": "happy1.json",
                    "duration_ms": 1000.0,
                    "keyframe_count": 10,
                },
                "sad1": {
                    "file": "sad1.json",
                    "duration_ms": 2000.0,
                    "keyframe_count": 20,
                },
            },
            "dances": {
                "dance1": {
                    "file": "dance1.json",
                    "duration_ms": 5000.0,
                    "keyframe_count": 50,
                }
            },
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        # Create emotion files
        for name in ["happy1", "sad1", "dance1"]:
            emotion_data = {
                "name": name,
                "description": f"Test {name}",
                "duration_ms": 1000.0,
                "keyframes": [
                    {
                        "time_ms": 0.0,
                        "head": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                        "antennas": [0.5, 0.5],
                        "body_yaw": 0.0,
                    }
                ],
            }
            (tmp_path / f"{name}.json").write_text(json.dumps(emotion_data))

        return EmotionLoader(data_dir=tmp_path)

    def test_list_emotions(self, loader_with_data: EmotionLoader) -> None:
        """Test listing available emotions."""
        emotions = loader_with_data.list_emotions()

        assert emotions == ["happy1", "sad1"]

    def test_list_dances(self, loader_with_data: EmotionLoader) -> None:
        """Test listing available dances."""
        dances = loader_with_data.list_dances()

        assert dances == ["dance1"]

    def test_list_all(self, loader_with_data: EmotionLoader) -> None:
        """Test listing all emotions and dances."""
        all_items = loader_with_data.list_all()

        assert all_items == ["dance1", "happy1", "sad1"]

    def test_has_emotion(self, loader_with_data: EmotionLoader) -> None:
        """Test checking if emotion exists."""
        assert loader_with_data.has_emotion("happy1") is True
        assert loader_with_data.has_emotion("dance1") is True
        assert loader_with_data.has_emotion("nonexistent") is False

    def test_get_emotion(self, loader_with_data: EmotionLoader) -> None:
        """Test loading emotion data."""
        emotion = loader_with_data.get_emotion("happy1")

        assert emotion is not None
        assert emotion.name == "happy1"
        assert len(emotion.keyframes) == 1

    def test_get_emotion_caching(self, loader_with_data: EmotionLoader) -> None:
        """Test that emotions are cached after first load."""
        emotion1 = loader_with_data.get_emotion("happy1")
        emotion2 = loader_with_data.get_emotion("happy1")

        # Should be the same object from cache
        assert emotion1 is emotion2

    def test_get_emotion_nonexistent(self, loader_with_data: EmotionLoader) -> None:
        """Test that None is returned for nonexistent emotions."""
        emotion = loader_with_data.get_emotion("nonexistent")

        assert emotion is None

    def test_get_emotion_info(self, loader_with_data: EmotionLoader) -> None:
        """Test getting emotion metadata without full load."""
        info = loader_with_data.get_emotion_info("happy1")

        assert info is not None
        assert info["duration_ms"] == 1000.0
        assert info["keyframe_count"] == 10

    def test_clear_cache(self, loader_with_data: EmotionLoader) -> None:
        """Test clearing the emotion cache."""
        loader_with_data.get_emotion("happy1")
        assert len(loader_with_data._cache) == 1

        loader_with_data.clear_cache()

        assert len(loader_with_data._cache) == 0

    def test_preload_all(self, loader_with_data: EmotionLoader) -> None:
        """Test preloading all emotions."""
        loaded = loader_with_data.preload_all()

        assert loaded == 3
        assert len(loader_with_data._cache) == 3

    def test_missing_manifest(self, tmp_path: Path) -> None:
        """Test loader works with missing manifest."""
        loader = EmotionLoader(data_dir=tmp_path)

        assert loader.list_emotions() == []
        assert loader.list_dances() == []


class TestGetEmotionLoader:
    """Tests for the get_emotion_loader function."""

    def test_returns_singleton(self) -> None:
        """Test that get_emotion_loader returns the same instance."""
        loader1 = get_emotion_loader()
        loader2 = get_emotion_loader()

        assert loader1 is loader2


class TestRealEmotionData:
    """Integration tests using real bundled emotion data."""

    @pytest.fixture
    def real_loader(self) -> EmotionLoader:
        """Get loader pointing to real data directory."""
        return EmotionLoader()

    def test_manifest_exists(self, real_loader: EmotionLoader) -> None:
        """Test that the real manifest file exists."""
        assert (real_loader.data_dir / "manifest.json").exists()

    def test_list_real_emotions(self, real_loader: EmotionLoader) -> None:
        """Test listing real bundled emotions."""
        emotions = real_loader.list_emotions()

        # Should have many emotions
        assert len(emotions) >= 70

        # Check some expected emotions
        assert "curious1" in emotions
        assert "cheerful1" in emotions
        assert "confused1" in emotions

    def test_list_real_dances(self, real_loader: EmotionLoader) -> None:
        """Test listing real bundled dances."""
        dances = real_loader.list_dances()

        assert dances == ["dance1", "dance2", "dance3"]

    def test_load_real_emotion(self, real_loader: EmotionLoader) -> None:
        """Test loading a real emotion file."""
        emotion = real_loader.get_emotion("cheerful1")

        assert emotion is not None
        assert emotion.name == "cheerful1"
        assert emotion.duration_ms > 0
        assert len(emotion.keyframes) > 0

        # Verify keyframe structure
        first_kf = emotion.keyframes[0]
        assert "roll" in first_kf.head
        assert "pitch" in first_kf.head
        assert "yaw" in first_kf.head
        assert len(first_kf.antennas) == 2

    def test_load_real_dance(self, real_loader: EmotionLoader) -> None:
        """Test loading a real dance file."""
        dance = real_loader.get_emotion("dance1")

        assert dance is not None
        assert dance.name == "dance1"
        assert dance.duration_ms > 0

    def test_audio_files_exist(self, real_loader: EmotionLoader) -> None:
        """Test that audio files are detected for emotions."""
        emotion = real_loader.get_emotion("cheerful1")

        assert emotion is not None
        assert emotion.audio_file is not None
        assert emotion.audio_file.exists()
        assert emotion.audio_file.suffix == ".wav"
