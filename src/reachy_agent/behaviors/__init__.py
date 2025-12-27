"""Reachy Agent Behaviors - Autonomous behavior patterns.

This module contains autonomous behavior patterns that run when the
agent is not actively responding to user commands. These behaviors
make the robot feel more alive and natural.

Motion blending architecture:
- PRIMARY motions (exclusive): breathing, idle look-around, emotions
- SECONDARY motions (additive): speech wobble, face tracking

The MotionBlendController orchestrates all motion sources at 100Hz internal
tick rate, sending composed poses to the daemon at 20Hz.
"""

from reachy_agent.behaviors.blend_controller import (
    BlendControllerConfig,
    MotionBlendController,
)
from reachy_agent.behaviors.breathing import BreathingConfig, BreathingMotion
from reachy_agent.behaviors.idle import IdleBehaviorConfig, IdleBehaviorController
from reachy_agent.behaviors.motion_types import (
    HeadPose,
    MotionContribution,
    MotionPriority,
    MotionSource,
    PoseLimits,
    PoseOffset,
)
from reachy_agent.behaviors.wobble import HeadWobble, WobbleConfig, simulate_speech

__all__ = [
    # Core types
    "HeadPose",
    "PoseOffset",
    "PoseLimits",
    "MotionPriority",
    "MotionSource",
    "MotionContribution",
    # Blend controller
    "MotionBlendController",
    "BlendControllerConfig",
    # Motion sources - Primary
    "BreathingMotion",
    "BreathingConfig",
    "IdleBehaviorController",
    "IdleBehaviorConfig",
    # Motion sources - Secondary
    "HeadWobble",
    "WobbleConfig",
    "simulate_speech",
]
