"""FastAPI application factory for Reachy Agent web dashboard.

Creates the web application with routes, WebSocket handlers,
and static file serving for the dashboard frontend.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from reachy_agent.permissions.handlers.web_handler import WebSocketPermissionHandler
from reachy_agent.permissions.storage.sqlite_audit import SQLiteAuditStorage
from reachy_agent.utils.logging import get_logger
from reachy_agent.web.routes import api_router, ws_router

if TYPE_CHECKING:
    from reachy_agent.agent.agent import AgentLoop

log = get_logger(__name__)


class DashboardState:
    """Shared state for the dashboard application.

    Holds references to handlers, storage, and agent loop
    that are shared across routes and WebSocket connections.

    Attributes:
        permission_handler: WebSocket-based permission handler.
        audit_storage: SQLite audit log storage.
        agent_loop: Optional agent loop for conversations.
        daemon_url: URL of the reachy daemon.
        conversation_history: Recent conversation messages.
    """

    def __init__(
        self,
        daemon_url: str = "http://localhost:8765",
        agent_loop: Any | None = None,
    ) -> None:
        """Initialize dashboard state.

        Args:
            daemon_url: URL of the reachy daemon.
            agent_loop: Optional agent loop instance.
        """
        self.permission_handler = WebSocketPermissionHandler()
        self.audit_storage = SQLiteAuditStorage()
        self.agent_loop = agent_loop
        self.daemon_url = daemon_url
        self.conversation_history: list[dict[str, Any]] = []
        self.turn_count = 0


def create_app(
    daemon_url: str = "http://localhost:8765",
    agent_loop: Any | None = None,
    debug: bool = False,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        daemon_url: URL of the reachy daemon for status/control.
        agent_loop: Optional agent loop for conversation handling.
        debug: Enable debug mode.

    Returns:
        Configured FastAPI application.

    Example:
        ```python
        app = create_app(
            daemon_url="http://localhost:8765",
            debug=True,
        )

        # Run with uvicorn
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=8080)
        ```
    """
    # Create shared state
    state = DashboardState(
        daemon_url=daemon_url,
        agent_loop=agent_loop,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Application lifespan handler."""
        log.info(
            "Starting Reachy Agent dashboard",
            daemon_url=daemon_url,
            debug=debug,
        )
        yield
        log.info("Shutting down Reachy Agent dashboard")
        await state.audit_storage.close()

    app = FastAPI(
        title="Reachy Agent Dashboard",
        description="Web interface for interacting with Reachy Agent",
        version="0.1.0",
        debug=debug,
        lifespan=lifespan,
    )

    # Store state on app for access in routes
    app.state.dashboard = state

    # Include API routes
    app.include_router(api_router, prefix="/api")

    # Include WebSocket routes
    app.include_router(ws_router)

    # Static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @app.get("/")
        async def serve_index() -> FileResponse:
            """Serve the dashboard index page."""
            return FileResponse(static_dir / "index.html")

    return app


async def run_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    daemon_url: str = "http://localhost:8765",
    agent_loop: Any | None = None,
    debug: bool = False,
) -> None:
    """Run the dashboard server.

    Convenience function for starting the server programmatically.

    Args:
        host: Host to bind to.
        port: Port to listen on.
        daemon_url: URL of the reachy daemon.
        agent_loop: Optional agent loop instance.
        debug: Enable debug mode.
    """
    import uvicorn

    app = create_app(
        daemon_url=daemon_url,
        agent_loop=agent_loop,
        debug=debug,
    )

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="debug" if debug else "info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Reachy Agent Dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    parser.add_argument("--daemon-url", default="http://localhost:8765")
    parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()

    asyncio.run(run_server(
        host=args.host,
        port=args.port,
        daemon_url=args.daemon_url,
        debug=args.debug,
    ))
