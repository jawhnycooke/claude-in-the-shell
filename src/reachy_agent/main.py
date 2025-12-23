"""Reachy Agent - Main entry point.

Run with: python -m reachy_agent
Or: reachy-agent (after installation)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

import typer

from reachy_agent.agent.loop import ReachyAgentLoop
from reachy_agent.utils.config import load_config, get_env_settings
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
) -> None:
    """Async main function.

    Args:
        config_path: Path to configuration file.
        daemon_url: URL of Reachy daemon.
        mock_daemon: Whether to start mock daemon.
        interactive: Whether to run interactive loop.
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
    )

    # Start mock daemon if requested
    mock_task = None
    if mock_daemon:
        log.info("Starting mock daemon")
        mock_task = asyncio.create_task(start_mock_daemon())
        await asyncio.sleep(1)  # Wait for daemon to start

    # Create and run agent
    async with ReachyAgentLoop(config=config, daemon_url=daemon_url).session() as agent:
        if interactive:
            await run_interactive_loop(agent)
        else:
            # Non-interactive mode - just keep running
            log.info("Running in non-interactive mode. Press Ctrl+C to exit.")
            while True:
                await asyncio.sleep(1)


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
) -> None:
    """Run the Reachy agent."""
    try:
        asyncio.run(
            async_main(
                config_path=config,
                daemon_url=daemon_url,
                mock_daemon=mock,
                interactive=not non_interactive,
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
def check() -> None:
    """Check system health and configuration."""
    import httpx

    print("🔍 Checking Reachy Agent configuration...\n")

    # Check configuration
    try:
        config = load_config()
        print(f"✅ Configuration loaded")
        print(f"   Model: {config.agent.model.value}")
        print(f"   Wake word: {config.agent.wake_word}")
    except Exception as e:
        print(f"❌ Configuration error: {e}")

    # Check environment
    env = get_env_settings()
    if env.anthropic_api_key:
        print(f"✅ Anthropic API key configured")
    else:
        print(f"⚠️ Anthropic API key not set (ANTHROPIC_API_KEY)")

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
        print(f"❌ Reachy daemon not reachable at localhost:8000")
    except Exception as e:
        print(f"❌ Error checking daemon: {e}")

    print("\n")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
