"""Reachy Agent Behaviors - Autonomous behavior patterns.

This module contains autonomous behavior patterns that run when the
agent is not actively responding to user commands. These behaviors
make the robot feel more alive and natural.
"""

from reachy_agent.behaviors.idle import IdleBehaviorController, IdleBehaviorConfig

__all__ = ["IdleBehaviorController", "IdleBehaviorConfig"]
