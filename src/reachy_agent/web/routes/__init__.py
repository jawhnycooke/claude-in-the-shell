"""Web routes for Reachy Agent dashboard."""

from reachy_agent.web.routes.api import router as api_router
from reachy_agent.web.routes.websocket import router as ws_router

__all__ = ["api_router", "ws_router"]
