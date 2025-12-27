"""Unit tests for the motion blending system.

Tests:
- motion_types.py - HeadPose, PoseOffset, PoseLimits
- breathing.py - BreathingMotion oscillation patterns
- wobble.py - HeadWobble audio-reactive motion
- blend_controller.py - MotionBlendController composition
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any

import pytest

from reachy_agent.behaviors import (
    BlendControllerConfig,
    BreathingConfig,
    BreathingMotion,
    HeadPose,
    HeadWobble,
    MotionBlendController,
    MotionPriority,
    PoseLimits,
    PoseOffset,
    WobbleConfig,
)


# =============================================================================
# HeadPose Tests
# =============================================================================


class TestHeadPose:
    """Tests for HeadPose dataclass."""

    def test_neutral_pose(self) -> None:
        """Test neutral pose creation."""
        pose = HeadPose.neutral()

        assert pose.pitch == 0.0
        assert pose.yaw == 0.0
        assert pose.roll == 0.0
        assert pose.z == 0.0
        assert pose.left_antenna == 45.0
        assert pose.right_antenna == 45.0

    def test_add_offset(self) -> None:
        """Test adding PoseOffset to HeadPose."""
        pose = HeadPose(pitch=10.0, yaw=20.0, roll=5.0, z=10.0)
        offset = PoseOffset(pitch=5.0, yaw=-10.0, roll=2.0, z=5.0)

        result = pose + offset

        assert result.pitch == 15.0
        assert result.yaw == 10.0
        assert result.roll == 7.0
        assert result.z == 15.0

    def test_clamp_to_limits(self) -> None:
        """Test clamping pose to safety limits."""
        pose = HeadPose(pitch=60.0, yaw=-60.0, roll=40.0, z=100.0)
        limits = PoseLimits(
            pitch_range=(-45.0, 45.0),
            yaw_range=(-45.0, 45.0),
            roll_range=(-30.0, 30.0),
            z_range=(-50.0, 50.0),
        )

        clamped = pose.clamp(limits)

        assert clamped.pitch == 45.0
        assert clamped.yaw == -45.0
        assert clamped.roll == 30.0
        assert clamped.z == 50.0

    def test_lerp_interpolation(self) -> None:
        """Test linear interpolation between poses."""
        start = HeadPose(pitch=0.0, yaw=0.0)
        end = HeadPose(pitch=10.0, yaw=20.0)

        # Halfway
        mid = start.lerp(end, 0.5)
        assert mid.pitch == 5.0
        assert mid.yaw == 10.0

        # Start
        at_start = start.lerp(end, 0.0)
        assert at_start.pitch == 0.0

        # End
        at_end = start.lerp(end, 1.0)
        assert at_end.pitch == 10.0

    def test_from_dict(self) -> None:
        """Test creating pose from dictionary."""
        data = {"pitch": 15.0, "yaw": -10.0, "z": 5.0}
        pose = HeadPose.from_dict(data)

        assert pose.pitch == 15.0
        assert pose.yaw == -10.0
        assert pose.z == 5.0
        assert pose.roll == 0.0  # Default


# =============================================================================
# PoseOffset Tests
# =============================================================================


class TestPoseOffset:
    """Tests for PoseOffset dataclass."""

    def test_scale(self) -> None:
        """Test scaling offset values."""
        offset = PoseOffset(pitch=10.0, yaw=20.0, roll=5.0)

        scaled = offset.scale(0.5)

        assert scaled.pitch == 5.0
        assert scaled.yaw == 10.0
        assert scaled.roll == 2.5

    def test_add_offsets(self) -> None:
        """Test adding two offsets together."""
        offset1 = PoseOffset(pitch=5.0, yaw=10.0)
        offset2 = PoseOffset(pitch=3.0, yaw=-5.0)

        combined = offset1 + offset2

        assert combined.pitch == 8.0
        assert combined.yaw == 5.0

    def test_generation_tracking(self) -> None:
        """Test generation tracking for invalidation."""
        offset1 = PoseOffset(generation=1)
        offset2 = PoseOffset(generation=5)

        combined = offset1 + offset2

        assert combined.generation == 5  # Max of both


# =============================================================================
# BreathingMotion Tests
# =============================================================================


class TestBreathingMotion:
    """Tests for BreathingMotion behavior."""

    @pytest.mark.asyncio
    async def test_priority(self) -> None:
        """Test breathing is PRIMARY priority."""
        breathing = BreathingMotion()

        assert breathing.priority == MotionPriority.PRIMARY

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping breathing."""
        breathing = BreathingMotion()

        assert not breathing.is_active

        await breathing.start()
        assert breathing.is_active

        await breathing.stop()
        assert not breathing.is_active

    @pytest.mark.asyncio
    async def test_z_oscillation(self) -> None:
        """Test Z-axis oscillation produces expected values."""
        config = BreathingConfig(z_amplitude_mm=5.0, z_frequency_hz=1.0)
        breathing = BreathingMotion(config)
        await breathing.start()

        # Wait for oscillation
        await asyncio.sleep(0.01)

        pose = await breathing.get_contribution(HeadPose.neutral())

        # Z should be oscillating
        assert isinstance(pose, HeadPose)
        assert -5.5 <= pose.z <= 5.5  # Within amplitude range

    @pytest.mark.asyncio
    async def test_antenna_opposite_motion(self) -> None:
        """Test antennas oscillate in opposite directions."""
        config = BreathingConfig(
            antenna_amplitude_deg=15.0,
            antenna_frequency_hz=2.0,
            antenna_base_angle=45.0,
        )
        breathing = BreathingMotion(config)
        await breathing.start()

        # Get multiple samples
        samples = []
        for _ in range(10):
            pose = await breathing.get_contribution(HeadPose.neutral())
            samples.append(pose)
            await asyncio.sleep(0.05)

        # Check antennas are moving in opposite directions
        for pose in samples:
            left_delta = pose.left_antenna - config.antenna_base_angle
            right_delta = pose.right_antenna - config.antenna_base_angle
            # When left moves up, right should move down
            # The signs should be opposite
            if abs(left_delta) > 0.1 and abs(right_delta) > 0.1:
                assert left_delta * right_delta <= 0, "Antennas should move opposite"

    @pytest.mark.asyncio
    async def test_inactive_returns_base_pose(self) -> None:
        """Test inactive breathing returns base pose."""
        breathing = BreathingMotion()
        base = HeadPose(pitch=10.0, yaw=5.0)

        # Set base pose before starting
        breathing.set_base_pose(base)

        pose = await breathing.get_contribution(HeadPose.neutral())

        assert pose.pitch == base.pitch
        assert pose.yaw == base.yaw


# =============================================================================
# HeadWobble Tests
# =============================================================================


class TestHeadWobble:
    """Tests for HeadWobble behavior."""

    @pytest.mark.asyncio
    async def test_priority(self) -> None:
        """Test wobble is SECONDARY priority."""
        wobble = HeadWobble()

        assert wobble.priority == MotionPriority.SECONDARY

    @pytest.mark.asyncio
    async def test_start_stop(self) -> None:
        """Test starting and stopping wobble."""
        wobble = HeadWobble()

        assert not wobble.is_active

        await wobble.start()
        assert wobble.is_active

        await wobble.stop()
        assert not wobble.is_active

    @pytest.mark.asyncio
    async def test_audio_level_response(self) -> None:
        """Test wobble responds to audio level changes."""
        wobble = HeadWobble()
        await wobble.start()

        # Zero audio level
        wobble.update_audio_level(0.0)
        await asyncio.sleep(0.1)  # Let smoothing settle
        silent_offset = await wobble.get_contribution(HeadPose.neutral())

        # High audio level
        wobble.update_audio_level(1.0)
        await asyncio.sleep(0.1)  # Let smoothing apply
        loud_offset = await wobble.get_contribution(HeadPose.neutral())

        assert isinstance(silent_offset, PoseOffset)
        assert isinstance(loud_offset, PoseOffset)

        # Loud should have more pitch displacement
        assert abs(loud_offset.pitch) > abs(silent_offset.pitch)

    @pytest.mark.asyncio
    async def test_returns_pose_offset(self) -> None:
        """Test wobble returns PoseOffset (not HeadPose)."""
        wobble = HeadWobble()
        await wobble.start()
        wobble.update_audio_level(0.5)

        result = await wobble.get_contribution(HeadPose.neutral())

        assert isinstance(result, PoseOffset)

    @pytest.mark.asyncio
    async def test_generation_increments(self) -> None:
        """Test generation increments on invalidate."""
        wobble = HeadWobble()

        gen1 = wobble.generation
        wobble.invalidate()
        gen2 = wobble.generation

        assert gen2 > gen1


# =============================================================================
# MotionBlendController Tests
# =============================================================================


class FailingMotionSource:
    """A motion source that raises exceptions for testing error handling."""

    def __init__(self, fail_on_contribution: bool = True) -> None:
        self._active = False
        self._fail_on_contribution = fail_on_contribution

    @property
    def priority(self) -> MotionPriority:
        return MotionPriority.PRIMARY

    @property
    def is_active(self) -> bool:
        return self._active

    async def start(self) -> None:
        self._active = True

    async def stop(self) -> None:
        self._active = False

    async def get_contribution(self, base_pose: HeadPose) -> HeadPose:
        if self._fail_on_contribution:
            raise RuntimeError("Simulated motion source failure")
        return HeadPose.neutral()


class TestMotionBlendController:
    """Tests for MotionBlendController orchestration."""

    @pytest.fixture
    def controller(self) -> MotionBlendController:
        """Create a controller for testing."""
        config = BlendControllerConfig(
            tick_rate_hz=100.0,
            command_rate_hz=20.0,
            enabled=True,
        )
        return MotionBlendController(config=config)

    @pytest.mark.asyncio
    async def test_register_sources(self, controller: MotionBlendController) -> None:
        """Test registering motion sources."""
        breathing = BreathingMotion()
        wobble = HeadWobble()

        controller.register_source("breathing", breathing)
        controller.register_source("wobble", wobble)

        assert "breathing" in controller._sources
        assert "wobble" in controller._sources

    @pytest.mark.asyncio
    async def test_set_primary(self, controller: MotionBlendController) -> None:
        """Test setting active primary motion source."""
        breathing = BreathingMotion()
        controller.register_source("breathing", breathing)

        await controller.set_primary("breathing")

        assert controller.active_primary == "breathing"
        assert breathing.is_active

    @pytest.mark.asyncio
    async def test_switch_primary(self, controller: MotionBlendController) -> None:
        """Test switching between primary sources stops the previous one."""
        breathing1 = BreathingMotion()
        breathing2 = BreathingMotion()

        controller.register_source("breath1", breathing1)
        controller.register_source("breath2", breathing2)

        await controller.set_primary("breath1")
        assert breathing1.is_active

        await controller.set_primary("breath2")
        assert not breathing1.is_active
        assert breathing2.is_active

    @pytest.mark.asyncio
    async def test_enable_disable_secondary(self, controller: MotionBlendController) -> None:
        """Test enabling and disabling secondary sources."""
        wobble = HeadWobble()
        controller.register_source("wobble", wobble)

        await controller.enable_secondary("wobble")
        assert "wobble" in controller.active_secondaries
        assert wobble.is_active

        await controller.disable_secondary("wobble")
        assert "wobble" not in controller.active_secondaries
        assert not wobble.is_active

    @pytest.mark.asyncio
    async def test_listening_state(self, controller: MotionBlendController) -> None:
        """Test listening state freezes antennas."""
        controller.set_listening(True)

        # Antenna positions should be frozen
        status = controller.get_status()
        assert status["listening"] is True

        controller.set_listening(False)
        status = controller.get_status()
        assert status["listening"] is False

    @pytest.mark.asyncio
    async def test_pose_composition(self) -> None:
        """Test pose composition with primary and secondary sources."""
        sent_poses: list[HeadPose] = []

        async def capture_pose(pose: HeadPose) -> None:
            sent_poses.append(pose)

        config = BlendControllerConfig(
            tick_rate_hz=100.0,
            command_rate_hz=50.0,  # Faster for testing
        )
        controller = MotionBlendController(
            config=config,
            send_pose_callback=capture_pose,
        )

        # Register sources
        breathing = BreathingMotion()
        wobble = HeadWobble()
        controller.register_source("breathing", breathing)
        controller.register_source("wobble", wobble)

        # Start controller and activate sources
        await controller.start()
        await controller.set_primary("breathing")
        await controller.enable_secondary("wobble")
        wobble.update_audio_level(0.5)

        # Let it run briefly
        await asyncio.sleep(0.1)

        await controller.stop()

        # Should have captured some poses
        assert len(sent_poses) > 0

    @pytest.mark.asyncio
    async def test_get_status(self, controller: MotionBlendController) -> None:
        """Test getting controller status."""
        breathing = BreathingMotion()
        controller.register_source("breathing", breathing)

        status = controller.get_status()

        assert "running" in status
        assert "active_primary" in status
        assert "active_secondaries" in status
        assert "registered_sources" in status
        assert "breathing" in status["registered_sources"]

    @pytest.mark.asyncio
    async def test_control_loop_continues_on_source_exception(self) -> None:
        """Test that control loop continues running when a motion source raises."""
        sent_poses: list[HeadPose] = []

        async def capture_pose(pose: HeadPose) -> None:
            sent_poses.append(pose)

        config = BlendControllerConfig(
            tick_rate_hz=100.0,
            command_rate_hz=50.0,
        )
        controller = MotionBlendController(
            config=config,
            send_pose_callback=capture_pose,
        )

        # Register a failing source
        failing_source = FailingMotionSource(fail_on_contribution=True)
        controller.register_source("failing", failing_source)

        # Start controller and activate failing source
        await controller.start()
        await controller.set_primary("failing")

        # Let it run for a bit - should not crash
        await asyncio.sleep(0.15)

        # Controller should still be running despite exceptions
        assert controller.is_running

        await controller.stop()

    @pytest.mark.asyncio
    async def test_control_loop_continues_on_callback_exception(self) -> None:
        """Test that control loop continues when pose callback raises."""
        call_count = 0

        async def failing_callback(pose: HeadPose) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("Simulated daemon callback failure")

        config = BlendControllerConfig(
            tick_rate_hz=100.0,
            command_rate_hz=50.0,
        )
        controller = MotionBlendController(
            config=config,
            send_pose_callback=failing_callback,
        )

        # Register a working source
        breathing = BreathingMotion()
        controller.register_source("breathing", breathing)

        await controller.start()
        await controller.set_primary("breathing")

        # Let it run - should continue despite callback failures
        await asyncio.sleep(0.15)

        assert controller.is_running
        assert call_count >= 3  # Should have attempted multiple calls

        await controller.stop()

    @pytest.mark.asyncio
    async def test_control_loop_recovers_after_source_fixed(self) -> None:
        """Test that control loop recovers when source stops failing."""
        sent_poses: list[HeadPose] = []

        async def capture_pose(pose: HeadPose) -> None:
            sent_poses.append(pose)

        config = BlendControllerConfig(
            tick_rate_hz=100.0,
            command_rate_hz=50.0,
        )
        controller = MotionBlendController(
            config=config,
            send_pose_callback=capture_pose,
        )

        # Register a source that initially fails
        failing_source = FailingMotionSource(fail_on_contribution=True)
        controller.register_source("failing", failing_source)

        await controller.start()
        await controller.set_primary("failing")

        # Let it run with failures
        await asyncio.sleep(0.1)

        # Fix the source
        failing_source._fail_on_contribution = False

        # Let it run after fix
        await asyncio.sleep(0.1)

        assert controller.is_running
        # Should have received poses after the fix
        assert len(sent_poses) > 0

        await controller.stop()


# =============================================================================
# PoseLimits Tests
# =============================================================================


class TestPoseLimits:
    """Tests for PoseLimits safety bounds."""

    def test_default_limits(self) -> None:
        """Test default safety limits."""
        limits = PoseLimits()

        assert limits.pitch_range == (-45.0, 45.0)
        assert limits.yaw_range == (-45.0, 45.0)
        assert limits.roll_range == (-30.0, 30.0)
        assert limits.z_range == (-50.0, 50.0)
        assert limits.antenna_range == (0.0, 90.0)

    def test_from_dict(self) -> None:
        """Test creating limits from dictionary."""
        data = {"pitch_range": (-30.0, 30.0), "yaw_range": (-20.0, 20.0)}
        limits = PoseLimits.from_dict(data)

        assert limits.pitch_range == (-30.0, 30.0)
        assert limits.yaw_range == (-20.0, 20.0)


# =============================================================================
# Config Tests
# =============================================================================


class TestConfigs:
    """Tests for configuration dataclasses."""

    def test_breathing_config_from_dict(self) -> None:
        """Test BreathingConfig.from_dict."""
        data = {"z_amplitude_mm": 10.0, "z_frequency_hz": 0.2}
        config = BreathingConfig.from_dict(data)

        assert config.z_amplitude_mm == 10.0
        assert config.z_frequency_hz == 0.2

    def test_wobble_config_from_dict(self) -> None:
        """Test WobbleConfig.from_dict."""
        data = {"max_pitch_deg": 12.0, "max_yaw_deg": 8.0}
        config = WobbleConfig.from_dict(data)

        assert config.max_pitch_deg == 12.0
        assert config.max_yaw_deg == 8.0

    def test_blend_controller_config_from_dict(self) -> None:
        """Test BlendControllerConfig.from_dict."""
        data = {"tick_rate_hz": 50.0, "command_rate_hz": 10.0}
        config = BlendControllerConfig.from_dict(data)

        assert config.tick_rate_hz == 50.0
        assert config.command_rate_hz == 10.0
