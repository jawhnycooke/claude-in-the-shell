"""Head wobble motion - speech-reactive animation.

Creates natural head movement during TTS playback that makes
speech feel more embodied and alive.

Based on patterns from Pollen Robotics' Conversation App:
- SwayRollRT algorithm transforms audio level into motion
- 80ms latency compensation for smooth real-time response
- Generation tracking for invalidation when new audio arrives

This is a SECONDARY motion source, meaning it provides offsets
that overlay on top of primary motions (breathing, idle, emotions).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reachy_agent.behaviors.motion_types import (
    MotionPriority,
    PoseOffset,
)


@dataclass
class WobbleConfig:
    """Configuration for head wobble during speech.

    All amplitudes in degrees. Based on Conversation App parameters.

    Attributes:
        max_pitch_deg: Maximum pitch displacement.
        max_yaw_deg: Maximum yaw displacement.
        max_roll_deg: Maximum roll displacement.
        latency_compensation_ms: Audio processing latency to compensate.
        smoothing_factor: Smoothing for transitions (0.0-1.0).
        noise_scale: Scale factor for Perlin-like noise overlay.
        enabled: Whether wobble is active.
    """

    max_pitch_deg: float = 8.0
    max_yaw_deg: float = 6.0
    max_roll_deg: float = 4.0
    latency_compensation_ms: float = 80.0
    smoothing_factor: float = 0.3
    noise_scale: float = 0.2
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WobbleConfig:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


class HeadWobble:
    """Head wobble motion source for speech animation.

    This is a SECONDARY motion source that provides additive offsets
    based on audio level. During TTS playback, it creates subtle
    head movements that make speech feel more natural.

    The wobble algorithm:
    1. Receives audio level (0.0 to 1.0) from TTS system
    2. Maps level to displacement using configurable curves
    3. Adds Perlin-like noise for organic variation
    4. Returns PoseOffset to blend with primary motion

    Example:
        config = WobbleConfig(max_pitch_deg=8.0)
        wobble = HeadWobble(config)
        await wobble.start()

        # During TTS playback:
        wobble.update_audio_level(0.7)  # Speaking loudly
        offset = await wobble.get_contribution(base_pose)

        # When TTS ends:
        wobble.update_audio_level(0.0)
        await wobble.stop()
    """

    def __init__(self, config: WobbleConfig | None = None) -> None:
        """Initialize head wobble.

        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or WobbleConfig()
        self._active = False
        self._start_time: datetime | None = None

        # Audio tracking
        self._audio_level: float = 0.0
        self._smoothed_level: float = 0.0
        self._generation: int = 0

        # Noise state for organic variation
        self._noise_offset_x = random.uniform(0, 1000)
        self._noise_offset_y = random.uniform(0, 1000)
        self._noise_offset_z = random.uniform(0, 1000)

    @property
    def priority(self) -> MotionPriority:
        """Return SECONDARY priority - wobble overlays other motions."""
        return MotionPriority.SECONDARY

    @property
    def is_active(self) -> bool:
        """Check if wobble is currently active."""
        return self._active

    @property
    def generation(self) -> int:
        """Get current generation for invalidation tracking."""
        return self._generation

    async def start(self) -> None:
        """Start wobble animation."""
        self._active = True
        self._start_time = datetime.now()
        self._generation += 1
        self._smoothed_level = 0.0

    async def stop(self) -> None:
        """Stop wobble animation."""
        self._active = False
        self._start_time = None
        self._audio_level = 0.0

    def update_audio_level(self, level: float) -> None:
        """Update the current audio level.

        Call this continuously during TTS playback with the
        current audio amplitude (0.0 to 1.0).

        Args:
            level: Audio level from 0.0 (silence) to 1.0 (max).
        """
        self._audio_level = max(0.0, min(1.0, level))

    def invalidate(self) -> None:
        """Invalidate current motion for new audio.

        Call this when new audio arrives to ensure smooth
        transition from previous motion state.
        """
        self._generation += 1

    async def get_contribution(self, base_pose: Any) -> PoseOffset:
        """Calculate wobble offset at current time.

        Args:
            base_pose: Current base pose (for reference, not used).

        Returns:
            PoseOffset with wobble displacements.
        """
        if not self._active or self._start_time is None:
            return PoseOffset(generation=self._generation)

        # Smooth the audio level
        self._smoothed_level += (
            self._audio_level - self._smoothed_level
        ) * self.config.smoothing_factor

        elapsed = (datetime.now() - self._start_time).total_seconds()

        # Calculate base displacement from audio level
        level = self._smoothed_level

        # Map audio level to displacement (non-linear curve for natural feel)
        # Uses sqrt for more responsive feel at low levels
        mapped_level = math.sqrt(level)

        # Generate noise-like variation using sum of sines
        # This approximates Perlin noise without the complexity
        noise_x = self._pseudo_noise(elapsed, self._noise_offset_x)
        noise_y = self._pseudo_noise(elapsed, self._noise_offset_y)
        noise_z = self._pseudo_noise(elapsed, self._noise_offset_z)

        # Calculate final offsets
        pitch_offset = (
            mapped_level * self.config.max_pitch_deg
            + noise_x * self.config.noise_scale * self.config.max_pitch_deg
        )

        yaw_offset = (
            noise_y * self.config.noise_scale * self.config.max_yaw_deg * (1 + level)
        )

        roll_offset = (
            noise_z * self.config.noise_scale * self.config.max_roll_deg * (1 + level)
        )

        return PoseOffset(
            pitch=pitch_offset,
            yaw=yaw_offset,
            roll=roll_offset,
            z=0.0,  # No Z-axis wobble
            left_antenna=0.0,  # No antenna wobble
            right_antenna=0.0,
            generation=self._generation,
        )

    def _pseudo_noise(self, t: float, offset: float) -> float:
        """Generate pseudo-noise using sum of sines.

        Approximates Perlin noise with overlapping frequencies.

        Args:
            t: Time in seconds.
            offset: Random offset for this dimension.

        Returns:
            Value between -1.0 and 1.0.
        """
        # Sum of sines at different frequencies
        value = (
            math.sin((t + offset) * 2.3) * 0.5
            + math.sin((t + offset) * 3.7) * 0.3
            + math.sin((t + offset) * 5.1) * 0.2
        )
        return value

    def get_status(self) -> dict[str, Any]:
        """Get current wobble status for debugging.

        Returns:
            Dictionary with wobble state information.
        """
        return {
            "active": self._active,
            "audio_level": self._audio_level,
            "smoothed_level": self._smoothed_level,
            "generation": self._generation,
            "enabled": self.config.enabled,
        }


async def simulate_speech(
    wobble: HeadWobble,
    duration_seconds: float = 3.0,
    sample_rate_hz: float = 30.0,
) -> list[PoseOffset]:
    """Simulate speech audio for testing wobble.

    Generates synthetic audio levels that mimic speech patterns
    (syllables, pauses, emphasis variations).

    Args:
        wobble: HeadWobble instance to drive.
        duration_seconds: How long to simulate.
        sample_rate_hz: Updates per second.

    Returns:
        List of PoseOffset samples generated.
    """
    import asyncio

    from reachy_agent.behaviors.motion_types import HeadPose

    samples: list[PoseOffset] = []
    interval = 1.0 / sample_rate_hz
    elapsed = 0.0

    await wobble.start()

    while elapsed < duration_seconds:
        # Simulate speech pattern
        # Syllable pattern: ~5Hz modulation
        syllable = 0.5 + 0.5 * math.sin(elapsed * 5.0 * 2 * math.pi)

        # Phrase pattern: ~0.5Hz modulation (pauses between phrases)
        phrase = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(elapsed * 0.5 * 2 * math.pi))

        # Random micro-variation
        noise = random.uniform(-0.1, 0.1)

        # Combine for final level
        level = max(0.0, min(1.0, syllable * phrase + noise))
        wobble.update_audio_level(level)

        # Get the offset
        offset = await wobble.get_contribution(HeadPose.neutral())
        samples.append(offset)

        await asyncio.sleep(interval)
        elapsed += interval

    await wobble.stop()
    return samples


if __name__ == "__main__":
    # Demo the wobble simulation
    import asyncio

    async def demo():
        print("Head Wobble Simulation Demo")
        print("=" * 40)

        config = WobbleConfig(max_pitch_deg=10.0, max_yaw_deg=8.0)
        wobble = HeadWobble(config)

        print(f"Config: max_pitch={config.max_pitch_deg}°, max_yaw={config.max_yaw_deg}°")
        print("\nSimulating 3 seconds of speech...")

        samples = await simulate_speech(wobble, duration_seconds=3.0)

        print(f"\nGenerated {len(samples)} samples")
        print("\nSample offsets (pitch, yaw, roll):")

        # Show every 10th sample
        for i, sample in enumerate(samples[::10]):
            print(
                f"  [{i*10:3d}] pitch={sample.pitch:+6.2f}° "
                f"yaw={sample.yaw:+6.2f}° roll={sample.roll:+6.2f}°"
            )

        print("\nDemo complete!")

    asyncio.run(demo())
