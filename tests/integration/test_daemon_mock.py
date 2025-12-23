"""Integration tests for the mock Reachy daemon.

These tests start the actual FastAPI mock daemon and make real HTTP requests
to verify the daemon behavior.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from reachy_agent.mcp_servers.reachy.daemon_mock import create_mock_daemon_app


@pytest.fixture
def app():
    """Create the mock daemon app."""
    return create_mock_daemon_app()


@pytest.fixture
async def client(app):
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, client: AsyncClient) -> None:
        """Test health check returns healthy status."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["mode"] == "mock"


class TestHeadMovement:
    """Tests for the /head/move endpoint."""

    @pytest.mark.asyncio
    async def test_move_head_left(self, client: AsyncClient) -> None:
        """Test moving head left."""
        response = await client.post(
            "/head/move",
            json={"direction": "left", "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "left" in data["message"].lower()
        assert data["position"]["yaw"] < 0  # Left is negative yaw

    @pytest.mark.asyncio
    async def test_move_head_right(self, client: AsyncClient) -> None:
        """Test moving head right."""
        response = await client.post(
            "/head/move",
            json={"direction": "right", "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["position"]["yaw"] > 0  # Right is positive yaw

    @pytest.mark.asyncio
    async def test_move_head_up(self, client: AsyncClient) -> None:
        """Test moving head up."""
        response = await client.post(
            "/head/move",
            json={"direction": "up", "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["position"]["pitch"] < 0  # Up is negative pitch

    @pytest.mark.asyncio
    async def test_move_head_down(self, client: AsyncClient) -> None:
        """Test moving head down."""
        response = await client.post(
            "/head/move",
            json={"direction": "down", "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["position"]["pitch"] > 0  # Down is positive pitch

    @pytest.mark.asyncio
    async def test_move_head_front_resets_position(self, client: AsyncClient) -> None:
        """Test moving head to front resets position."""
        # First move left
        await client.post("/head/move", json={"direction": "left", "speed": "fast"})

        # Then move to front
        response = await client.post(
            "/head/move",
            json={"direction": "front", "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["position"]["yaw"] == 0.0
        assert data["position"]["pitch"] == 0.0
        assert data["position"]["roll"] == 0.0

    @pytest.mark.asyncio
    async def test_move_head_with_specific_degrees(self, client: AsyncClient) -> None:
        """Test moving head with specific angle."""
        response = await client.post(
            "/head/move",
            json={"direction": "left", "speed": "fast", "degrees": 30.0},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["position"]["yaw"] == -30.0


class TestEmotionExpression:
    """Tests for the /expression/emotion endpoint."""

    @pytest.mark.asyncio
    async def test_play_happy_emotion(self, client: AsyncClient) -> None:
        """Test playing happy emotion."""
        response = await client.post(
            "/expression/emotion",
            json={"emotion": "happy", "intensity": 0.8},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["emotion"] == "happy"
        assert data["intensity"] == 0.8

    @pytest.mark.asyncio
    async def test_play_sad_emotion(self, client: AsyncClient) -> None:
        """Test playing sad emotion."""
        response = await client.post(
            "/expression/emotion",
            json={"emotion": "sad", "intensity": 0.5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["emotion"] == "sad"

    @pytest.mark.asyncio
    async def test_emotion_default_intensity(self, client: AsyncClient) -> None:
        """Test emotion with default intensity."""
        response = await client.post(
            "/expression/emotion",
            json={"emotion": "curious"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["intensity"] == 0.7  # Default


class TestSpeech:
    """Tests for the /audio/speak endpoint."""

    @pytest.mark.asyncio
    async def test_speak_short_text(self, client: AsyncClient) -> None:
        """Test speaking short text."""
        response = await client.post(
            "/audio/speak",
            json={"text": "Hello world"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["text"] == "Hello world"
        assert "duration_seconds" in data

    @pytest.mark.asyncio
    async def test_speak_with_custom_speed(self, client: AsyncClient) -> None:
        """Test speaking with custom speed."""
        response = await client.post(
            "/audio/speak",
            json={"text": "Fast speech", "speed": 1.5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"


class TestCameraCapture:
    """Tests for the /camera/capture endpoint."""

    @pytest.mark.asyncio
    async def test_capture_image_basic(self, client: AsyncClient) -> None:
        """Test basic image capture."""
        response = await client.post(
            "/camera/capture",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["width"] == 640
        assert data["height"] == 480
        assert data["format"] == "jpeg"

    @pytest.mark.asyncio
    async def test_capture_with_analysis(self, client: AsyncClient) -> None:
        """Test image capture with analysis."""
        response = await client.post(
            "/camera/capture",
            json={"analyze": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "analysis" in data
        assert "objects_detected" in data["analysis"]
        assert "faces_detected" in data["analysis"]
        assert "description" in data["analysis"]

    @pytest.mark.asyncio
    async def test_capture_with_save(self, client: AsyncClient) -> None:
        """Test image capture with save."""
        response = await client.post(
            "/camera/capture",
            json={"save": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "saved_path" in data


class TestAntennaControl:
    """Tests for the /antenna/state endpoint."""

    @pytest.mark.asyncio
    async def test_set_left_antenna(self, client: AsyncClient) -> None:
        """Test setting left antenna angle."""
        response = await client.post(
            "/antenna/state",
            json={"left_angle": 30.0, "duration_ms": 100},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["left_angle"] == 30.0

    @pytest.mark.asyncio
    async def test_set_right_antenna(self, client: AsyncClient) -> None:
        """Test setting right antenna angle."""
        response = await client.post(
            "/antenna/state",
            json={"right_angle": 60.0, "duration_ms": 100},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["right_angle"] == 60.0

    @pytest.mark.asyncio
    async def test_set_both_antennas(self, client: AsyncClient) -> None:
        """Test setting both antenna angles."""
        response = await client.post(
            "/antenna/state",
            json={"left_angle": 20.0, "right_angle": 70.0, "duration_ms": 100},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["left_angle"] == 20.0
        assert data["right_angle"] == 70.0

    @pytest.mark.asyncio
    async def test_antenna_wiggle(self, client: AsyncClient) -> None:
        """Test antenna wiggle mode."""
        response = await client.post(
            "/antenna/state",
            json={"wiggle": True, "duration_ms": 100},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["wiggle"] is True


class TestSensorReadings:
    """Tests for the /sensors endpoint."""

    @pytest.mark.asyncio
    async def test_get_all_sensors(self, client: AsyncClient) -> None:
        """Test getting all sensor readings."""
        response = await client.get("/sensors")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "imu" in data
        assert "audio_level" in data
        assert "temperature" in data

    @pytest.mark.asyncio
    async def test_get_imu_only(self, client: AsyncClient) -> None:
        """Test getting only IMU sensor."""
        response = await client.get("/sensors?sensors=imu")

        assert response.status_code == 200
        data = response.json()
        assert "imu" in data
        assert "acceleration" in data["imu"]
        assert "gyroscope" in data["imu"]

    @pytest.mark.asyncio
    async def test_get_temperature_only(self, client: AsyncClient) -> None:
        """Test getting only temperature sensor."""
        response = await client.get("/sensors?sensors=temperature")

        assert response.status_code == 200
        data = response.json()
        assert "temperature" in data
        assert "cpu_celsius" in data["temperature"]
        assert "ambient_celsius" in data["temperature"]


class TestSoundLocalization:
    """Tests for the /audio/look_at_sound endpoint."""

    @pytest.mark.asyncio
    async def test_look_at_sound(self, client: AsyncClient) -> None:
        """Test sound localization."""
        response = await client.post(
            "/audio/look_at_sound",
            json={"timeout_ms": 100},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        # Result is random - either sound detected or not
        assert "sound_detected" in data or "message" in data


class TestDance:
    """Tests for the /expression/dance endpoint."""

    @pytest.mark.asyncio
    async def test_dance_happy(self, client: AsyncClient) -> None:
        """Test happy dance routine."""
        response = await client.post(
            "/expression/dance",
            json={"routine": "happy", "duration_seconds": 0.5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["routine"] == "happy"
        assert "Completed" in data["message"]

    @pytest.mark.asyncio
    async def test_dance_celebrate(self, client: AsyncClient) -> None:
        """Test celebrate dance routine."""
        response = await client.post(
            "/expression/dance",
            json={"routine": "celebrate", "duration_seconds": 0.5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["routine"] == "celebrate"


class TestBodyRotation:
    """Tests for the /body/rotate endpoint."""

    @pytest.mark.asyncio
    async def test_rotate_left(self, client: AsyncClient) -> None:
        """Test rotating body left."""
        response = await client.post(
            "/body/rotate",
            json={"direction": "left", "degrees": 90.0, "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["direction"] == "left"
        assert data["degrees"] == 90.0

    @pytest.mark.asyncio
    async def test_rotate_right(self, client: AsyncClient) -> None:
        """Test rotating body right."""
        response = await client.post(
            "/body/rotate",
            json={"direction": "right", "degrees": 45.0, "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["direction"] == "right"
        assert "current_rotation" in data


class TestLookAt:
    """Tests for the /head/look_at endpoint."""

    @pytest.mark.asyncio
    async def test_look_at_position(self, client: AsyncClient) -> None:
        """Test precise head positioning."""
        response = await client.post(
            "/head/look_at",
            json={
                "roll": 10.0,
                "pitch": -15.0,
                "yaw": 20.0,
                "z": 5.0,
                "duration": 0.1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["position"]["roll"] == 10.0
        assert data["position"]["pitch"] == -15.0
        assert data["position"]["yaw"] == 20.0
        assert data["position"]["z"] == 5.0


class TestListen:
    """Tests for the /audio/listen endpoint."""

    @pytest.mark.asyncio
    async def test_listen_audio(self, client: AsyncClient) -> None:
        """Test audio capture."""
        response = await client.post(
            "/audio/listen",
            json={"duration_seconds": 0.5},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["format"] == "wav"
        assert data["channels"] == 4
        assert "audio_base64" in data


class TestLifecycle:
    """Tests for the /lifecycle endpoints."""

    @pytest.mark.asyncio
    async def test_wake_up(self, client: AsyncClient) -> None:
        """Test motor initialization."""
        response = await client.post("/lifecycle/wake_up")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["is_awake"] is True

    @pytest.mark.asyncio
    async def test_sleep(self, client: AsyncClient) -> None:
        """Test motor shutdown."""
        response = await client.post("/lifecycle/sleep")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["is_awake"] is False

    @pytest.mark.asyncio
    async def test_wake_sleep_cycle(self, client: AsyncClient) -> None:
        """Test full wake/sleep cycle."""
        # Wake up
        response = await client.post("/lifecycle/wake_up")
        assert response.json()["is_awake"] is True

        # Sleep
        response = await client.post("/lifecycle/sleep")
        assert response.json()["is_awake"] is False

        # Wake up again
        response = await client.post("/lifecycle/wake_up")
        assert response.json()["is_awake"] is True


class TestGestures:
    """Tests for the /gesture endpoints."""

    @pytest.mark.asyncio
    async def test_nod(self, client: AsyncClient) -> None:
        """Test nodding gesture."""
        response = await client.post(
            "/gesture/nod",
            json={"times": 3, "speed": "fast"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["gesture"] == "nod"
        assert data["times"] == 3

    @pytest.mark.asyncio
    async def test_shake(self, client: AsyncClient) -> None:
        """Test head shake gesture."""
        response = await client.post(
            "/gesture/shake",
            json={"times": 2, "speed": "normal"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["gesture"] == "shake"
        assert data["times"] == 2

    @pytest.mark.asyncio
    async def test_rest(self, client: AsyncClient) -> None:
        """Test returning to rest pose."""
        response = await client.post("/gesture/rest")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["position"]["pitch"] == 0.0
        assert data["position"]["yaw"] == 0.0
        assert data["position"]["roll"] == 0.0


class TestDaemonClientIntegration:
    """Integration tests for ReachyDaemonClient with real mock daemon."""

    @pytest.mark.asyncio
    async def test_client_with_real_daemon(self, app) -> None:
        """Test the daemon client against the real mock daemon."""
        from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

        # Use httpx's ASGITransport to connect client to app
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as http:
            # Create a patched client that uses our test http client
            client = ReachyDaemonClient(base_url="http://test")
            # Replace the internal client
            client._client = http

            # Test health check
            result = await client.health_check()
            assert result["status"] == "healthy"

            # Test move head
            result = await client.move_head(direction="left", speed="fast")
            assert result["status"] == "success"

            # Test speak
            result = await client.speak(text="Hello", speed=1.0)
            assert result["status"] == "success"

            # Test capture image
            result = await client.capture_image(analyze=True)
            assert result["status"] == "success"
            assert "analysis" in result

    @pytest.mark.asyncio
    async def test_new_client_methods(self, app) -> None:
        """Test new daemon client methods against real mock daemon."""
        from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as http:
            client = ReachyDaemonClient(base_url="http://test")
            client._client = http

            # Test rotate
            result = await client.rotate(direction="left", degrees=90.0)
            assert result["status"] == "success"

            # Test look_at
            result = await client.look_at(roll=10.0, pitch=5.0, yaw=-10.0)
            assert result["status"] == "success"

            # Test listen
            result = await client.listen(duration_seconds=0.5)
            assert result["status"] == "success"

            # Test wake_up/sleep
            result = await client.wake_up()
            assert result["status"] == "success"

            result = await client.sleep()
            assert result["status"] == "success"

            # Test gestures
            result = await client.nod(times=2)
            assert result["status"] == "success"

            result = await client.shake(times=2)
            assert result["status"] == "success"

            result = await client.rest()
            assert result["status"] == "success"
