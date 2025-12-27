"""Unit tests for ReachyDaemonClient emotion playback methods.

Tests cover:
- play_local_emotion() async method
- Three-tier fallback logic (local -> HuggingFace -> custom)
- Backend type checking
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from reachy_agent.emotions.loader import EmotionLoader
from reachy_agent.mcp_servers.reachy.daemon_client import (
    DaemonBackend,
    ReachyDaemonClient,
    ReachyDaemonError,
)


class TestPlayLocalEmotion:
    """Tests for the play_local_emotion() async method."""

    @pytest.fixture
    def mock_emotion_loader(self, tmp_path: Path) -> EmotionLoader:
        """Create a mock emotion loader with test data."""
        # Create manifest
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {
                "happy1": {
                    "file": "happy1.json",
                    "duration_ms": 500.0,
                    "keyframe_count": 2,
                },
            },
            "dances": {},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        # Create emotion file with two keyframes
        emotion_data = {
            "name": "happy1",
            "description": "Test happy emotion",
            "duration_ms": 500.0,
            "keyframes": [
                {
                    "time_ms": 0.0,
                    "head": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "antennas": [0.5, 0.5],
                    "body_yaw": 0.0,
                },
                {
                    "time_ms": 250.0,
                    "head": {"roll": 0.1, "pitch": 0.1, "yaw": 0.1},
                    "antennas": [0.6, 0.6],
                    "body_yaw": 0.05,
                },
            ],
        }
        (tmp_path / "happy1.json").write_text(json.dumps(emotion_data))

        return EmotionLoader(data_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_play_local_emotion_requires_real_backend(self) -> None:
        """Test that play_local_emotion fails with mock backend."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")

        # Force mock backend
        client._backend = DaemonBackend.MOCK

        result = await client.play_local_emotion("happy1")

        assert result["status"] == "error"
        assert "only available on real daemon" in result["message"]

        await client.close()

    @pytest.mark.asyncio
    async def test_play_local_emotion_not_found(
        self, mock_emotion_loader: EmotionLoader
    ) -> None:
        """Test that play_local_emotion returns error for missing emotion."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")

        # Force real backend
        client._backend = DaemonBackend.REAL

        result = await client.play_local_emotion(
            "nonexistent", emotion_loader=mock_emotion_loader
        )

        assert result["status"] == "error"
        assert "not found" in result["message"]

        await client.close()

    @pytest.mark.asyncio
    async def test_play_local_emotion_success(
        self, mock_emotion_loader: EmotionLoader
    ) -> None:
        """Test successful local emotion playback."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")

        # Force real backend
        client._backend = DaemonBackend.REAL

        # Mock the _request method to simulate successful API calls
        client._request = AsyncMock(return_value={"uuid": "test-uuid"})

        result = await client.play_local_emotion(
            "happy1", emotion_loader=mock_emotion_loader
        )

        assert result["status"] == "success"
        assert result["move_name"] == "happy1"
        assert result["source"] == "local"

        # Verify _request was called for each keyframe
        assert client._request.call_count == 2

        await client.close()

    @pytest.mark.asyncio
    async def test_play_local_emotion_keyframe_failure(
        self, mock_emotion_loader: EmotionLoader
    ) -> None:
        """Test that keyframe failures are handled gracefully."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")

        # Force real backend
        client._backend = DaemonBackend.REAL

        # Mock _request to fail on second keyframe
        call_count = 0

        async def mock_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ReachyDaemonError("Connection lost")
            return {"uuid": "test-uuid"}

        client._request = mock_request  # type: ignore[method-assign]

        result = await client.play_local_emotion(
            "happy1", emotion_loader=mock_emotion_loader
        )

        assert result["status"] == "error"
        assert "Connection lost" in result["message"]

        await client.close()


class TestThreeTierFallback:
    """Tests for the three-tier emotion fallback logic."""

    @pytest.fixture
    def mock_emotion_loader(self, tmp_path: Path) -> EmotionLoader:
        """Create a mock emotion loader with curious1."""
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {
                "curious1": {
                    "file": "curious1.json",
                    "duration_ms": 500.0,
                    "keyframe_count": 1,
                },
            },
            "dances": {},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        emotion_data = {
            "name": "curious1",
            "description": "Test curious emotion",
            "duration_ms": 500.0,
            "keyframes": [
                {
                    "time_ms": 0.0,
                    "head": {"roll": 0.0, "pitch": 0.0, "yaw": 0.1},
                    "antennas": [0.5, 0.5],
                    "body_yaw": 0.0,
                },
            ],
        }
        (tmp_path / "curious1.json").write_text(json.dumps(emotion_data))

        return EmotionLoader(data_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_fallback_uses_local_first(
        self, mock_emotion_loader: EmotionLoader
    ) -> None:
        """Test that play_emotion tries local first."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.REAL

        # Patch get_emotion_loader to return our mock
        with patch(
            "reachy_agent.mcp_servers.reachy.daemon_client.get_emotion_loader",
            return_value=mock_emotion_loader,
        ):
            # Mock _request for successful local playback
            client._request = AsyncMock(return_value={"uuid": "test-uuid"})

            result = await client.play_emotion("curious")

            assert result["status"] == "success"
            assert result.get("source") == "local"

        await client.close()

    @pytest.mark.asyncio
    async def test_fallback_to_huggingface_on_local_failure(
        self, tmp_path: Path
    ) -> None:
        """Test that HuggingFace is tried when local fails."""
        # Create empty loader (no local emotions)
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {},
            "dances": {},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        empty_loader = EmotionLoader(data_dir=tmp_path)

        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.REAL

        with patch(
            "reachy_agent.mcp_servers.reachy.daemon_client.get_emotion_loader",
            return_value=empty_loader,
        ):
            # Mock successful HuggingFace playback
            client._request = AsyncMock(return_value={"uuid": "hf-uuid"})

            result = await client.play_emotion("curious")

            assert result["status"] == "success"
            # Should have called play_recorded_move endpoint
            assert client._request.call_count >= 1

        await client.close()

    @pytest.mark.asyncio
    async def test_fallback_to_custom_on_huggingface_failure(
        self, tmp_path: Path
    ) -> None:
        """Test that custom composition is used when both local and HF fail."""
        # Create empty loader
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {},
            "dances": {},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        empty_loader = EmotionLoader(data_dir=tmp_path)

        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.REAL

        call_count = 0

        async def mock_request(
            method: str, path: str, **kwargs: Any
        ) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            # Fail HuggingFace call (recorded-move-dataset path)
            if "recorded-move-dataset" in path:
                raise ReachyDaemonError("HuggingFace unavailable")
            # Succeed for custom composition (goto endpoint)
            return {"uuid": "custom-uuid"}

        with patch(
            "reachy_agent.mcp_servers.reachy.daemon_client.get_emotion_loader",
            return_value=empty_loader,
        ):
            client._request = mock_request  # type: ignore[method-assign]

            # Use "thinking" which is a custom emotion (not in native mapping)
            result = await client.play_emotion("thinking")

            assert result["status"] == "success"

        await client.close()

    @pytest.mark.asyncio
    async def test_unknown_emotion_uses_neutral(self, tmp_path: Path) -> None:
        """Test that unknown emotions fall back to neutral."""
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {},
            "dances": {},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        empty_loader = EmotionLoader(data_dir=tmp_path)

        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.REAL

        with patch(
            "reachy_agent.mcp_servers.reachy.daemon_client.get_emotion_loader",
            return_value=empty_loader,
        ):
            client._request = AsyncMock(return_value={"uuid": "neutral-uuid"})

            result = await client.play_emotion("completely_unknown_emotion")

            # Should succeed using neutral fallback
            assert result["status"] == "success"

        await client.close()

    @pytest.mark.asyncio
    async def test_mock_backend_uses_expression_endpoint(self) -> None:
        """Test that mock backend uses /expression/emotion endpoint."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.MOCK

        client._request = AsyncMock(
            return_value={"status": "success", "emotion": "happy"}
        )

        result = await client.play_emotion("happy")

        assert result["status"] == "success"
        # Verify it called the mock endpoint
        client._request.assert_called_once()
        call_args = client._request.call_args
        assert call_args[0][1] == "/expression/emotion"

        await client.close()


class TestDanceThreeTierFallback:
    """Tests for the dance three-tier fallback logic."""

    @pytest.fixture
    def mock_dance_loader(self, tmp_path: Path) -> EmotionLoader:
        """Create a mock emotion loader with dance1."""
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {},
            "dances": {
                "dance1": {
                    "file": "dance1.json",
                    "duration_ms": 1000.0,
                    "keyframe_count": 2,
                },
            },
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        dance_data = {
            "name": "dance1",
            "description": "Test dance",
            "duration_ms": 1000.0,
            "keyframes": [
                {
                    "time_ms": 0.0,
                    "head": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                    "antennas": [0.7, 0.7],
                    "body_yaw": 0.0,
                },
                {
                    "time_ms": 500.0,
                    "head": {"roll": 0.1, "pitch": -0.1, "yaw": 0.2},
                    "antennas": [0.8, 0.6],
                    "body_yaw": 0.1,
                },
            ],
        }
        (tmp_path / "dance1.json").write_text(json.dumps(dance_data))

        return EmotionLoader(data_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_dance_uses_local_first(
        self, mock_dance_loader: EmotionLoader
    ) -> None:
        """Test that dance() tries local first."""
        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.REAL

        with patch(
            "reachy_agent.mcp_servers.reachy.daemon_client.get_emotion_loader",
            return_value=mock_dance_loader,
        ):
            client._request = AsyncMock(return_value={"uuid": "test-uuid"})

            result = await client.dance("celebrate")  # Maps to dance1

            assert result["status"] == "success"
            assert result.get("source") == "local"

        await client.close()

    @pytest.mark.asyncio
    async def test_dance_fallback_to_custom_routine(self, tmp_path: Path) -> None:
        """Test that unknown dance uses custom DANCE_ROUTINES."""
        manifest = {
            "version": "1.0",
            "source_dataset": "test",
            "downloaded_at": "2025-01-01T00:00:00Z",
            "emotions": {},
            "dances": {},
        }
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        empty_loader = EmotionLoader(data_dir=tmp_path)

        client = ReachyDaemonClient(base_url="http://localhost:8000")
        client._backend = DaemonBackend.REAL

        with patch(
            "reachy_agent.mcp_servers.reachy.daemon_client.get_emotion_loader",
            return_value=empty_loader,
        ):
            client._request = AsyncMock(return_value={"uuid": "custom-uuid"})

            # "greeting" is not in NATIVE_DANCE_MAPPING, uses DANCE_ROUTINES
            result = await client.dance("greeting", duration_seconds=2.0)

            assert result["status"] == "success"

        await client.close()
