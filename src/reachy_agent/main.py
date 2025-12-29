"""Reachy Agent - Main entry point.

Run with: python -m reachy_agent
Or: reachy-agent (after installation)

Commands:
- run: Start the agent with basic interactive prompt
- repl: Start the Rich-based CLI REPL
- web: Start the web dashboard server
- check: Check system health
- version: Show version info
"""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import typer

from reachy_agent.agent.agent import ReachyAgentLoop
from reachy_agent.utils.config import get_env_settings, load_config
from reachy_agent.utils.logging import configure_logging, get_logger

app = typer.Typer(
    name="reachy-agent",
    help="Reachy Agent - An embodied AI agent for Reachy Mini robot",
)

log = get_logger(__name__)


def setup_signal_handlers(loop: asyncio.AbstractEventLoop, agent: ReachyAgentLoop) -> None:
    """Set up signal handlers for graceful shutdown.

    Args:
        loop: Event loop.
        agent: Agent loop to shutdown.
    """

    async def shutdown_handler() -> None:
        log.info("Received shutdown signal")
        await agent.shutdown()
        loop.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown_handler()))


async def run_interactive_loop(agent: ReachyAgentLoop) -> None:
    """Run an interactive conversation loop.

    Args:
        agent: Initialized agent loop.
    """
    print("\n🤖 Reachy Agent Ready!")
    print("Type your messages below. Use Ctrl+C to exit.\n")

    while True:
        try:
            # Get user input
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input("You: ")
            )

            if not user_input.strip():
                continue

            # Process input
            response = await agent.process_input(user_input)

            if response.success:
                print(f"\nReachy: {response.text}\n")
            else:
                print(f"\n⚠️ Error: {response.error}\n")

        except EOFError:
            break


async def async_main(
    config_path: Path | None = None,
    daemon_url: str = "http://localhost:8000",
    mock_daemon: bool = False,
    interactive: bool = True,
    voice_mode: bool = False,
) -> None:
    """Async main function.

    Args:
        config_path: Path to configuration file.
        daemon_url: URL of Reachy daemon.
        mock_daemon: Whether to start mock daemon.
        interactive: Whether to run interactive loop.
        voice_mode: Whether to enable voice interaction.
    """
    # Load configuration
    config = load_config(config_path)
    env = get_env_settings()

    # Configure logging
    configure_logging(
        level="DEBUG" if env.debug else "INFO",
        json_format=False,  # Console format for development
    )

    log.info(
        "Starting Reachy Agent",
        model=config.agent.model.value,
        daemon_url=daemon_url,
        mock_daemon=mock_daemon,
        voice_mode=voice_mode,
    )

    # Start mock daemon if requested
    if mock_daemon:
        log.info("Starting mock daemon")
        _ = asyncio.create_task(start_mock_daemon())
        await asyncio.sleep(1)  # Wait for daemon to start

    # Create and run agent
    # Disable motion blending and idle behavior in voice mode for cleaner logs
    async with ReachyAgentLoop(
        config=config,
        daemon_url=daemon_url,
        enable_motion_blend=not voice_mode,  # Disable for voice testing
        enable_idle_behavior=not voice_mode,  # Disable for voice testing
    ).session() as agent:
        if voice_mode:
            await run_voice_mode(agent)
        elif interactive:
            await run_interactive_loop(agent)
        else:
            # Non-interactive mode - just keep running
            log.info("Running in non-interactive mode. Press Ctrl+C to exit.")
            while True:
                await asyncio.sleep(1)


async def run_voice_mode(agent: ReachyAgentLoop) -> None:
    """Run the agent with voice interaction.

    Args:
        agent: Initialized agent loop.
    """
    try:
        from reachy_agent.voice import VoicePipeline
    except ImportError as e:
        print(f"\n❌ Voice dependencies not installed: {e}")
        print("Install with: pip install reachy-agent[voice]")
        return

    print("\n🎤 Reachy Agent Voice Mode")
    print("Say 'Hey Reachy' to activate. Use Ctrl+C to exit.\n")

    # Create and start voice pipeline
    pipeline = VoicePipeline(
        agent=agent,
        on_transcription=lambda text: print(f"You: {text}"),
        on_response=lambda text: print(f"Reachy: {text}"),
    )

    try:
        success = await pipeline.initialize()
        if not success:
            print("❌ Failed to initialize voice pipeline")
            return

        await pipeline.start()

        # Keep running until interrupted
        while pipeline.is_running:
            await asyncio.sleep(0.1)

    finally:
        await pipeline.stop()


async def start_mock_daemon() -> None:
    """Start the mock daemon server in background."""
    try:
        import uvicorn

        from reachy_agent.mcp_servers.reachy.daemon_mock import create_mock_daemon_app

        app = create_mock_daemon_app()
        config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
        server = uvicorn.Server(config)
        await server.serve()
    except ImportError:
        log.warning("uvicorn not installed, cannot start mock daemon")


@app.command()
def run(
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    daemon_url: str = typer.Option(
        "http://localhost:8000",
        "--daemon-url",
        "-d",
        help="URL of Reachy daemon",
    ),
    mock: bool = typer.Option(
        False,
        "--mock",
        "-m",
        help="Start mock daemon for testing",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="Run without interactive prompt",
    ),
    voice: bool = typer.Option(
        False,
        "--voice",
        "-v",
        help="Enable voice interaction (requires OpenAI API key)",
    ),
) -> None:
    """Run the Reachy agent.

    Use --voice to enable real-time voice interaction with the robot.
    Requires: pip install reachy-agent[voice] and OPENAI_API_KEY env var.
    """
    try:
        asyncio.run(
            async_main(
                config_path=config,
                daemon_url=daemon_url,
                mock_daemon=mock,
                interactive=not non_interactive,
                voice_mode=voice,
            )
        )
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


@app.command()
def version() -> None:
    """Show version information."""
    from reachy_agent import __version__

    print(f"Reachy Agent v{__version__}")


@app.command()
def repl(
    daemon_url: str = typer.Option(
        "http://localhost:8765",
        "--daemon-url",
        "-d",
        help="URL of Reachy daemon",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
) -> None:
    """Start the Rich-based interactive REPL.

    Provides a full-featured CLI with:
    - Rich markdown rendering
    - Command history
    - Slash commands (/help, /status, /history, etc.)
    - Permission confirmation prompts
    """
    from reachy_agent.cli import AgentREPL
    from reachy_agent.permissions.storage.sqlite_audit import SQLiteAuditStorage

    # Load configuration
    cfg = load_config(config)
    env = get_env_settings()

    # Configure logging
    configure_logging(
        level="DEBUG" if env.debug else "INFO",
        json_format=False,
    )

    log.info("Starting REPL", daemon_url=daemon_url)

    async def run_repl() -> None:
        # Create audit storage for the session
        audit_storage = SQLiteAuditStorage()

        # Create agent loop (optional - can run in demo mode)
        agent_loop = None
        try:
            agent_loop = ReachyAgentLoop(config=cfg, daemon_url=daemon_url)
            await agent_loop.initialize()
        except Exception as e:
            log.warning(f"Agent initialization failed, running in demo mode: {e}")

        # Create and run REPL
        repl = AgentREPL(
            agent_loop=agent_loop,
            daemon_url=daemon_url,
        )

        try:
            await repl.run()
        finally:
            if agent_loop:
                await agent_loop.shutdown()
            await audit_storage.close()

    try:
        asyncio.run(run_repl())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


@app.command()
def web(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        "-h",
        help="Host to bind to",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        "-p",
        help="Port to listen on",
    ),
    daemon_url: str = typer.Option(
        "http://localhost:8765",
        "--daemon-url",
        "-d",
        help="URL of Reachy daemon",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Enable debug mode",
    ),
) -> None:
    """Start the web dashboard server.

    Provides a browser-based interface with:
    - Chat interface for agent conversations
    - Live video stream from MuJoCo simulation
    - Permission confirmation modals
    - Real-time status updates via WebSocket
    """
    from reachy_agent.web import create_app

    # Load configuration
    cfg = load_config(config)
    env = get_env_settings()

    # Configure logging
    configure_logging(
        level="DEBUG" if debug or env.debug else "INFO",
        json_format=False,
    )

    log.info(
        "Starting web dashboard",
        host=host,
        port=port,
        daemon_url=daemon_url,
    )

    async def run_web() -> None:
        import uvicorn

        # Create agent loop (optional)
        agent_loop = None
        try:
            agent_loop = ReachyAgentLoop(config=cfg, daemon_url=daemon_url)
            await agent_loop.initialize()
        except Exception as e:
            log.warning(f"Agent initialization failed, running in demo mode: {e}")

        # Create the web app
        web_app = create_app(
            daemon_url=daemon_url,
            agent_loop=agent_loop,
            debug=debug,
        )

        # Run with uvicorn
        uvicorn_config = uvicorn.Config(
            web_app,
            host=host,
            port=port,
            log_level="debug" if debug else "info",
        )
        server = uvicorn.Server(uvicorn_config)

        try:
            await server.serve()
        finally:
            if agent_loop:
                await agent_loop.shutdown()

    try:
        asyncio.run(run_web())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


@app.command()
def check() -> None:
    """Check system health and configuration."""
    import httpx

    print("🔍 Checking Reachy Agent configuration...\n")

    # Check configuration
    try:
        config = load_config()
        print("✅ Configuration loaded")
        print(f"   Model: {config.agent.model.value}")
        print(f"   Wake word: {config.agent.wake_word}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")

    # Check environment
    env = get_env_settings()
    if env.anthropic_api_key:
        print("✅ Anthropic API key configured")
    else:
        print("⚠️ Anthropic API key not set (ANTHROPIC_API_KEY)")

    # Check daemon
    try:
        response = httpx.get("http://localhost:8000/health", timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            mode = data.get("mode", "real")
            print(f"✅ Reachy daemon reachable (mode: {mode})")
        else:
            print(f"⚠️ Reachy daemon returned status {response.status_code}")
    except httpx.ConnectError:
        print("❌ Reachy daemon not reachable at localhost:8000")
    except Exception as e:
        print(f"❌ Error checking daemon: {e}")

    print("\n")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
