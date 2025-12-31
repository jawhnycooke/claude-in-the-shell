"""Motion blending type definitions.

Core dataclasses and protocols for the motion blending system.
Enables simultaneous primary (exclusive) and secondary (additive) motions.

Based on patterns from Pollen Robotics' Conversation App.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Protocol, Union

if TYPE_CHECKING:
    pass


class MotionPriority(str, Enum):
    """Motion priority levels.

    PRIMARY: Exclusive motions - only one can be active at a time
             (breathing, idle look-around, emotions, dances)
    SECONDARY: Additive motions - overlay on top of primary
               (speech wobble, face tracking)
    """

    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclass
class PoseLimits:
    """Safety limits for pose values.

    All angles in degrees, z in millimeters.
    """

    pitch_range: tuple[float, float] = (-45.0, 45.0)
    yaw_range: tuple[float, float] = (-45.0, 45.0)
    roll_range: tuple[float, float] = (-30.0, 30.0)
    z_range: tuple[float, float] = (-50.0, 50.0)
    antenna_range: tuple[float, float] = (0.0, 90.0)

    @classmethod
    def from_dict(cls, data: dict) -> PoseLimits:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class PoseOffset:
    """Delta values to add to a base pose.

    Used by secondary motion sources (wobble, face tracking)
    to overlay motion on top of primary poses.

    All angles in degrees, z in millimeters.
    """

    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    z: float = 0.0
    left_antenna: float = 0.0
    right_antenna: float = 0.0
    generation: int = 0  # For invalidation tracking

    def scale(self, factor: float) -> PoseOffset:
        """Scale offset by factor.

        Args:
            factor: Scaling factor (0.0 to 1.0 typical).

        Returns:
            New PoseOffset with scaled values.
        """
        return PoseOffset(
            pitch=self.pitch * factor,
            yaw=self.yaw * factor,
            roll=self.roll * factor,
            z=self.z * factor,
            left_antenna=self.left_antenna * factor,
            right_antenna=self.right_antenna * factor,
            generation=self.generation,
        )

    def __add__(self, other: PoseOffset) -> PoseOffset:
        """Add two offsets together."""
        return PoseOffset(
            pitch=self.pitch + other.pitch,
            yaw=self.yaw + other.yaw,
            roll=self.roll + other.roll,
            z=self.z + other.z,
            left_antenna=self.left_antenna + other.left_antenna,
            right_antenna=self.right_antenna + other.right_antenna,
            generation=max(self.generation, other.generation),
        )


@dataclass
class HeadPose:
    """Complete head pose snapshot.

    All angles in degrees. Convention:
    - pitch: positive = look up
    - yaw: positive = look left
    - roll: positive = tilt right (from robot's perspective)
    - z: vertical offset in millimeters

    Antenna angles: 0 = flat/back, 90 = vertical (straight up)
    """

    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0
    z: float = 0.0  # Vertical offset in mm
    left_antenna: float = 90.0  # Vertical (straight up)
    right_antenna: float = 90.0
    timestamp: datetime = field(default_factory=datetime.now)

    def __add__(self, offset: PoseOffset) -> HeadPose:
        """Add offset to create new pose.

        Args:
            offset: PoseOffset to add.

        Returns:
            New HeadPose with offset applied.
        """
        return HeadPose(
            pitch=self.pitch + offset.pitch,
            yaw=self.yaw + offset.yaw,
            roll=self.roll + offset.roll,
            z=self.z + offset.z,
            left_antenna=self.left_antenna + offset.left_antenna,
            right_antenna=self.right_antenna + offset.right_antenna,
        )

    def clamp(self, limits: PoseLimits) -> HeadPose:
        """Clamp pose to safety limits.

        Args:
            limits: PoseLimits defining safe ranges.

        Returns:
            New HeadPose with values clamped to limits.
        """

        def _clamp(value: float, range_tuple: tuple[float, float]) -> float:
            return max(range_tuple[0], min(range_tuple[1], value))

        return HeadPose(
            pitch=_clamp(self.pitch, limits.pitch_range),
            yaw=_clamp(self.yaw, limits.yaw_range),
            roll=_clamp(self.roll, limits.roll_range),
            z=_clamp(self.z, limits.z_range),
            left_antenna=_clamp(self.left_antenna, limits.antenna_range),
            right_antenna=_clamp(self.right_antenna, limits.antenna_range),
        )

    def lerp(self, target: HeadPose, t: float) -> HeadPose:
        """Linear interpolation toward target pose.

        Args:
            target: Target pose to interpolate toward.
            t: Interpolation factor (0.0 = self, 1.0 = target).

        Returns:
            New HeadPose interpolated between self and target.
        """
        t = max(0.0, min(1.0, t))
        return HeadPose(
            pitch=self.pitch + (target.pitch - self.pitch) * t,
            yaw=self.yaw + (target.yaw - self.yaw) * t,
            roll=self.roll + (target.roll - self.roll) * t,
            z=self.z + (target.z - self.z) * t,
            left_antenna=self.left_antenna + (target.left_antenna - self.left_antenna) * t,
            right_antenna=self.right_antenna + (target.right_antenna - self.right_antenna) * t,
        )

    def ease_in_out(self, target: HeadPose, t: float) -> HeadPose:
        """Ease-in-out interpolation toward target pose.

        Uses cubic ease-in-out for smooth acceleration and deceleration.
        The motion starts slow, speeds up in the middle, and slows down at the end.

        Args:
            target: Target pose to interpolate toward.
            t: Progress factor (0.0 = start, 1.0 = end).

        Returns:
            New HeadPose with eased interpolation between self and target.
        """
        t = max(0.0, min(1.0, t))
        # Cubic ease-in-out: slow start, fast middle, slow end
        if t < 0.5:
            eased_t = 4.0 * t * t * t
        else:
            eased_t = 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0
        return self.lerp(target, eased_t)

    @classmethod
    def neutral(cls) -> HeadPose:
        """Return a neutral (center) pose with antennas vertical."""
        return cls(pitch=0.0, yaw=0.0, roll=0.0, z=0.0, left_antenna=90.0, right_antenna=90.0)

    @classmethod
    def from_dict(cls, data: dict) -> HeadPose:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k) and k != "timestamp"})


# Type alias for motion contribution
MotionContribution = Union[HeadPose, PoseOffset]


class MotionSource(Protocol):
    """Protocol for motion sources (breathing, wobble, idle, etc.).

    Motion sources provide contributions to the final robot pose.
    Primary sources return HeadPose (exclusive), secondary return
    PoseOffset (additive).
    """

    @property
    def priority(self) -> MotionPriority:
        """Motion priority level (PRIMARY or SECONDARY)."""
        ...

    @property
    def is_active(self) -> bool:
        """Whether motion source is currently active."""
        ...

    async def get_contribution(self, base_pose: HeadPose) -> MotionContribution:
        """Get this source's contribution to the final pose.

        Args:
            base_pose: Current base pose for reference.

        Returns:
            HeadPose for PRIMARY priority (replaces base)
            PoseOffset for SECONDARY priority (adds to base)
        """
        ...

    async def start(self) -> None:
        """Start the motion source."""
        ...

    async def stop(self) -> None:
        """Stop the motion source."""
        ...
