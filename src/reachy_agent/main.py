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
    test_voice_mode: bool = False,
) -> None:
    """Async main function.

    Args:
        config_path: Path to configuration file.
        daemon_url: URL of Reachy daemon.
        mock_daemon: Whether to start mock daemon.
        interactive: Whether to run interactive loop.
        voice_mode: Whether to enable voice interaction.
        test_voice_mode: Whether to run autonomous voice tests.
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
        test_voice_mode=test_voice_mode,
    )

    # Start mock daemon if requested
    if mock_daemon:
        log.info("Starting mock daemon")
        _ = asyncio.create_task(start_mock_daemon())
        await asyncio.sleep(1)  # Wait for daemon to start

    # Create and run agent
    async with ReachyAgentLoop(
        config=config,
        daemon_url=daemon_url,
        enable_motion_blend=True,
        enable_idle_behavior=True,
    ).session() as agent:
        if test_voice_mode:
            await run_voice_test_mode(agent)
        elif voice_mode:
            await run_voice_mode(agent, config)
        elif interactive:
            await run_interactive_loop(agent)
        else:
            # Non-interactive mode - just keep running
            log.info("Running in non-interactive mode. Press Ctrl+C to exit.")
            while True:
                await asyncio.sleep(1)


async def run_voice_mode(agent: ReachyAgentLoop, config: dict | None = None) -> None:
    """Run the agent with voice interaction.

    Args:
        agent: Initialized agent loop.
        config: Optional config dict with voice settings from YAML.
    """
    try:
        from reachy_agent.voice import VoicePipeline, VoicePipelineConfig
        from reachy_agent.voice.audio import AudioConfig
    except ImportError as e:
        print(f"\n❌ Voice dependencies not installed: {e}")
        print("Install with: pip install reachy-agent[voice]")
        return

    print("\n🎤 Reachy Agent Voice Mode")
    print("Say 'Hey Reachy' to activate. Use Ctrl+C to exit.\n")

    # Build voice pipeline config from YAML settings
    voice_config = VoicePipelineConfig()
    if config and hasattr(config, "voice") and config.voice:
        voice_cfg = config.voice
        # Build audio config with device indices from YAML
        if voice_cfg.get("audio"):
            audio_cfg = voice_cfg["audio"]
            voice_config.audio = AudioConfig(
                sample_rate=audio_cfg.get("sample_rate", 16000),
                channels=audio_cfg.get("channels", 1),
                chunk_size=audio_cfg.get("chunk_size", 512),
                format_bits=audio_cfg.get("format_bits", 16),
                input_device_index=audio_cfg.get("input_device_index"),
                output_device_index=audio_cfg.get("output_device_index"),
                max_init_retries=audio_cfg.get("max_init_retries", 3),
                retry_delay_seconds=audio_cfg.get("retry_delay_seconds", 1.0),
                output_lead_in_ms=audio_cfg.get("output_lead_in_ms", 200),
                input_warmup_chunks=audio_cfg.get("input_warmup_chunks", 5),
            )
            log.info(
                "Voice audio config loaded",
                input_device=voice_config.audio.input_device_index,
                output_device=voice_config.audio.output_device_index,
            )

    # Create and start voice pipeline
    pipeline = VoicePipeline(
        agent=agent,
        config=voice_config,
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


async def run_voice_test_mode(agent: ReachyAgentLoop) -> None:
    """Run autonomous voice pipeline tests using synthetic speech.

    Uses OpenAI TTS to generate synthetic human speech and inject it
    into the voice pipeline for automated end-to-end testing.

    Args:
        agent: Initialized agent loop.
    """
    try:
        from reachy_agent.voice import (
            DEFAULT_TEST_SCENARIOS,
            SyntheticHuman,
            VoicePipeline,
            VoicePipelineConfig,
            VoiceTestHarness,
        )
    except ImportError as e:
        print(f"\n❌ Voice dependencies not installed: {e}")
        print("Install with: pip install reachy-agent[voice]")
        return

    print("\n🧪 Reachy Agent Voice Test Mode")
    print("Running autonomous voice pipeline tests...\n")

    # Create voice pipeline with wake word disabled for testing
    config = VoicePipelineConfig(wake_word_enabled=False)
    pipeline = VoicePipeline(
        agent=agent,
        config=config,
        on_transcription=lambda text: print(f"  📝 Transcription: {text}"),
        on_response=lambda text: print(f"  🗣️ Response: {text[:100]}..."),
    )

    # Initialize pipeline
    success = await pipeline.initialize()
    if not success:
        print("❌ Failed to initialize voice pipeline")
        return

    # Create test harness
    harness = VoiceTestHarness(
        agent=agent,
        pipeline=pipeline,
        synthetic_human=SyntheticHuman(),
    )

    # Wire up pipeline callbacks to harness
    pipeline.on_transcription = harness._on_transcription
    pipeline.on_response = harness._on_response

    if not await harness.initialize():
        print("❌ Failed to initialize test harness")
        return

    try:
        # Connect synthetic human
        if not await harness.synthetic_human.connect():
            print("❌ Failed to connect synthetic human to OpenAI")
            return

        print(f"Running {len(DEFAULT_TEST_SCENARIOS)} test scenarios...\n")
        print("-" * 60)

        # Run test scenarios
        results = await harness.run_all_scenarios(DEFAULT_TEST_SCENARIOS)

        # Print summary
        print("\n" + "=" * 60)
        print("TEST RESULTS SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in results if r.success)
        failed = len(results) - passed

        for result in results:
            status_icon = "✅" if result.success else "❌"
            print(f"{status_icon} {result.input_text[:40]:<40} [{result.status.value}]")
            if not result.success and result.error_message:
                print(f"   Error: {result.error_message}")

        print("-" * 60)
        print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
        print("=" * 60)

    finally:
        await harness.cleanup()
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
    test_voice: bool = typer.Option(
        False,
        "--test-voice",
        help="Run autonomous voice pipeline tests using synthetic speech",
    ),
) -> None:
    """Run the Reachy agent.

    Use --voice to enable real-time voice interaction with the robot.
    Use --test-voice to run autonomous voice pipeline tests without manual speech.
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
                test_voice_mode=test_voice,
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
