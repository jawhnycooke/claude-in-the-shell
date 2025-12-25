"""Web dashboard module for Reachy Agent.

Provides a browser-based interface for agent conversations,
with WebSocket for real-time permission confirmations and
live video streaming from the MuJoCo simulation.
"""

from reachy_agent.web.app import create_app

__all__ = ["create_app"]
