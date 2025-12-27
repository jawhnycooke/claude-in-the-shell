"""Breathing motion - subtle idle animation.

Creates a natural "alive" feeling through:
1. Vertical body oscillation (Z-axis) - simulates breathing
2. Antenna sway (opposite directions) - creates attentive appearance
3. Micro head movements - subtle pitch variation

Based on Conversation App specification:
- Z-axis: 5mm amplitude at 0.1 Hz (6 second cycle)
- Antennas: +/-15 degrees at 0.5 Hz (2 second cycle), opposite directions
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reachy_agent.behaviors.motion_types import (
    HeadPose,
    MotionPriority,
)


@dataclass
class BreathingConfig:
    """Configuration for breathing behavior.

    All frequencies in Hz, amplitudes in their respective units
    (degrees for angles, mm for z-axis).
    """

    # Z-axis (body) oscillation - simulates breathing
    z_amplitude_mm: float = 5.0
    z_frequency_hz: float = 0.1  # 6 second period (slow breath)

    # Antenna oscillation - creates attentive appearance
    antenna_amplitude_deg: float = 15.0
    antenna_frequency_hz: float = 0.5  # 2 second period
    antenna_base_angle: float = 45.0  # Neutral antenna position

    # Head micro-movements - subtle variation
    pitch_amplitude_deg: float = 1.5
    pitch_frequency_hz: float = 0.12  # Slightly offset from z for organic feel

    # Yaw micro-drift (very subtle)
    yaw_amplitude_deg: float = 0.8
    yaw_frequency_hz: float = 0.07  # Very slow drift

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BreathingConfig:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


class BreathingMotion:
    """Breathing motion source - primary motion for idle state.

    Creates a subtle "alive" feeling through synchronized oscillations.
    This is a PRIMARY motion source, meaning it provides complete poses
    rather than offsets.

    The breathing pattern consists of:
    - Slow Z-axis oscillation (like breathing)
    - Antenna sway in opposite directions (attentive appearance)
    - Micro head pitch movements (subtle life)

    Example:
        config = BreathingConfig(z_amplitude_mm=5.0)
        breathing = BreathingMotion(config)
        await breathing.start()

        # In control loop:
        pose = await breathing.get_contribution(base_pose)
    """

    def __init__(self, config: BreathingConfig | None = None) -> None:
        """Initialize breathing motion.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or BreathingConfig()
        self._active = False
        self._start_time: datetime | None = None
        self._base_pose = HeadPose.neutral()

    @property
    def priority(self) -> MotionPriority:
        """Return PRIMARY priority - breathing is exclusive motion."""
        return MotionPriority.PRIMARY

    @property
    def is_active(self) -> bool:
        """Check if breathing is currently active."""
        return self._active

    async def start(self) -> None:
        """Start breathing animation."""
        self._active = True
        self._start_time = datetime.now()

    async def stop(self) -> None:
        """Stop breathing animation."""
        self._active = False
        self._start_time = None

    def set_base_pose(self, pose: HeadPose) -> None:
        """Set the base pose that breathing modifies.

        This allows breathing to maintain a general orientation
        (e.g., looking slightly left) while adding oscillations.

        Args:
            pose: Base pose to breathe around.
        """
        self._base_pose = pose

    async def get_contribution(self, base_pose: HeadPose) -> HeadPose:
        """Calculate breathing pose at current time.

        Args:
            base_pose: Current base pose (may be used for reference).

        Returns:
            HeadPose with breathing oscillations applied.
        """
        if not self._active or self._start_time is None:
            return self._base_pose

        elapsed = (datetime.now() - self._start_time).total_seconds()

        # Z-axis oscillation (breathing)
        z_offset = self.config.z_amplitude_mm * math.sin(
            2 * math.pi * self.config.z_frequency_hz * elapsed
        )

        # Antenna oscillation (opposite directions for natural look)
        antenna_wave = self.config.antenna_amplitude_deg * math.sin(
            2 * math.pi * self.config.antenna_frequency_hz * elapsed
        )
        left_antenna = self.config.antenna_base_angle + antenna_wave
        right_antenna = self.config.antenna_base_angle - antenna_wave  # Opposite

        # Micro pitch movement (subtle life)
        pitch_offset = self.config.pitch_amplitude_deg * math.sin(
            2 * math.pi * self.config.pitch_frequency_hz * elapsed
        )

        # Micro yaw drift (very subtle wandering)
        yaw_offset = self.config.yaw_amplitude_deg * math.sin(
            2 * math.pi * self.config.yaw_frequency_hz * elapsed
        )

        return HeadPose(
            pitch=self._base_pose.pitch + pitch_offset,
            yaw=self._base_pose.yaw + yaw_offset,
            roll=self._base_pose.roll,  # No roll oscillation
            z=self._base_pose.z + z_offset,
            left_antenna=left_antenna,
            right_antenna=right_antenna,
        )

    def get_current_phase(self) -> dict[str, float]:
        """Get current oscillation phases (for debugging/visualization).

        Returns:
            Dictionary with phase information for each oscillation.
        """
        if not self._active or self._start_time is None:
            return {"z_phase": 0.0, "antenna_phase": 0.0, "pitch_phase": 0.0}

        elapsed = (datetime.now() - self._start_time).total_seconds()

        return {
            "z_phase": (elapsed * self.config.z_frequency_hz) % 1.0,
            "antenna_phase": (elapsed * self.config.antenna_frequency_hz) % 1.0,
            "pitch_phase": (elapsed * self.config.pitch_frequency_hz) % 1.0,
            "elapsed_seconds": elapsed,
        }
