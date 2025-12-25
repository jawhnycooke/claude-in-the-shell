"""Interactive REPL for Reachy Agent conversations.

Provides a command-line interface for chatting with the agent,
with Rich formatting and prompt_toolkit for input handling.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from reachy_agent.permissions.handlers.cli_handler import CLIPermissionHandler
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.agent.agent import AgentLoop

log = get_logger(__name__)


class AgentREPL:
    """Interactive REPL for Reachy Agent conversations.

    Provides a command-line interface with:
    - Rich markdown rendering for responses
    - Command history with prompt_toolkit
    - Built-in slash commands
    - Permission handler integration
    - Spinner for thinking/processing states

    Commands:
    - /help - Show available commands
    - /status - Show agent and robot status
    - /history - Show recent conversation history
    - /clear - Clear conversation history
    - /permissions - Show permission rules
    - /quit - Exit the REPL

    Example:
        ```python
        repl = AgentREPL(
            agent_loop=my_agent,
            daemon_url="http://localhost:8765",
        )
        await repl.run()
        ```

    Attributes:
        console: Rich Console for output formatting.
        permission_handler: CLI permission handler for confirmations.
    """

    # Slash command definitions
    COMMANDS = {
        "/help": "Show available commands",
        "/status": "Show agent and robot status",
        "/history": "Show recent conversation history",
        "/clear": "Clear conversation history",
        "/permissions": "Show permission rules",
        "/quit": "Exit the REPL",
        "/compact": "Compact conversation to reduce context",
    }

    # Prompt styling
    PROMPT_STYLE = Style.from_dict({
        "prompt": "ansigreen bold",
        "input": "ansiwhite",
    })

    def __init__(
        self,
        agent_loop: AgentLoop | None = None,
        daemon_url: str = "http://localhost:8765",
        history_file: str = "~/.reachy/repl_history",
        on_prompt: Callable[[str], Any] | None = None,
    ) -> None:
        """Initialize the REPL.

        Args:
            agent_loop: Optional AgentLoop instance. If not provided,
                        uses on_prompt callback for handling prompts.
            daemon_url: URL of the reachy daemon for status checks.
            history_file: Path to save command history.
            on_prompt: Callback for handling prompts when no agent_loop.
        """
        self.agent_loop = agent_loop
        self.daemon_url = daemon_url
        self._on_prompt = on_prompt

        # Rich console for output
        self.console = Console()
        self.permission_handler = CLIPermissionHandler(console=self.console)

        # Prompt session with history and completion
        from pathlib import Path

        history_path = Path(history_file).expanduser()
        history_path.parent.mkdir(parents=True, exist_ok=True)

        command_completer = WordCompleter(
            list(self.COMMANDS.keys()),
            ignore_case=True,
        )

        self._session = PromptSession(
            history=FileHistory(str(history_path)),
            auto_suggest=AutoSuggestFromHistory(),
            completer=command_completer,
            style=self.PROMPT_STYLE,
        )

        # Conversation state
        self._conversation_history: list[dict[str, str]] = []
        self._running = False
        self._turn_count = 0

    async def run(self) -> None:
        """Run the interactive REPL loop.

        Displays welcome message, then loops reading prompts
        and displaying responses until /quit or EOF.
        """
        self._running = True
        self._setup_signal_handlers()

        # Welcome message
        self._display_welcome()

        while self._running:
            try:
                # Get user input
                user_input = await self._get_input()

                if user_input is None:
                    # EOF (Ctrl+D)
                    break

                user_input = user_input.strip()

                if not user_input:
                    continue

                # Handle slash commands
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                    continue

                # Process as conversation prompt
                await self._handle_prompt(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /quit to exit[/dim]")
                continue

            except EOFError:
                break

            except Exception as e:
                log.exception("Error in REPL loop")
                self.console.print(f"[red]Error: {e}[/red]")

        self._display_goodbye()

    def _setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""
        def handle_sigint(signum: int, frame: Any) -> None:
            # Let KeyboardInterrupt propagate to the loop
            raise KeyboardInterrupt

        signal.signal(signal.SIGINT, handle_sigint)

    async def _get_input(self) -> str | None:
        """Get input from user with styled prompt."""
        try:
            prompt_text = [
                ("class:prompt", "reachy"),
                ("", " > "),
            ]

            # Run prompt_toolkit in executor since it blocks
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._session.prompt(prompt_text),
            )
            return result

        except EOFError:
            return None

    async def _handle_command(self, command: str) -> None:
        """Handle a slash command.

        Args:
            command: The command string (including slash).
        """
        cmd = command.lower().split()[0]
        args = command.split()[1:] if len(command.split()) > 1 else []

        if cmd == "/help":
            self._display_help()

        elif cmd == "/status":
            await self._display_status()

        elif cmd == "/history":
            self._display_history()

        elif cmd == "/clear":
            self._clear_history()

        elif cmd == "/permissions":
            await self._display_permissions()

        elif cmd == "/compact":
            await self._compact_conversation()

        elif cmd == "/quit":
            self._running = False

        else:
            self.console.print(
                f"[yellow]Unknown command: {cmd}[/yellow]\n"
                f"[dim]Type /help for available commands[/dim]"
            )

    async def _handle_prompt(self, prompt: str) -> None:
        """Handle a conversation prompt.

        Args:
            prompt: The user's message.
        """
        self._turn_count += 1

        # Add to history
        self._conversation_history.append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat(),
        })

        # Show thinking spinner
        with Live(
            Spinner("dots", text="Thinking...", style="cyan"),
            console=self.console,
            transient=True,
        ):
            try:
                if self.agent_loop is not None:
                    # Use agent loop
                    response = await self._run_agent(prompt)
                elif self._on_prompt is not None:
                    # Use callback
                    result = self._on_prompt(prompt)
                    if asyncio.iscoroutine(result):
                        response = await result
                    else:
                        response = str(result)
                else:
                    response = "[No agent configured - running in demo mode]\n\nI received your message but no agent is connected."

            except Exception as e:
                log.exception("Error processing prompt")
                response = f"Error: {e}"

        # Add response to history
        self._conversation_history.append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now().isoformat(),
        })

        # Display response
        self._display_response(response)

    async def _run_agent(self, prompt: str) -> str:
        """Run the agent loop with a prompt.

        Args:
            prompt: The user's message.

        Returns:
            The agent's response text.
        """
        if self.agent_loop is None:
            return "No agent connected"

        # The agent loop should return the response
        # This is a simplified interface - actual implementation
        # may vary based on AgentLoop API
        try:
            result = await self.agent_loop.process_input(prompt)
            return result.text if result.success else f"Error: {result.error}"
        except AttributeError:
            # Fallback if run_turn doesn't exist
            return "Agent loop interface not implemented"

    def _display_welcome(self) -> None:
        """Display welcome message."""
        welcome = Panel(
            Text.from_markup(
                "[bold cyan]Reachy Agent REPL[/bold cyan]\n\n"
                "Type your message to chat with Reachy.\n"
                "Use [bold]/help[/bold] for commands, [bold]/quit[/bold] to exit.\n"
                "[dim]Press Ctrl+D or type /quit to exit[/dim]"
            ),
            title="Welcome",
            border_style="cyan",
            padding=(1, 2),
        )
        self.console.print()
        self.console.print(welcome)
        self.console.print()

    def _display_goodbye(self) -> None:
        """Display goodbye message."""
        self.console.print()
        self.console.print(
            "[cyan]Goodbye! Thanks for chatting with Reachy.[/cyan]"
        )
        self.console.print()

    def _display_help(self) -> None:
        """Display available commands."""
        table = Table(title="Available Commands", show_header=True)
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="white")

        for cmd, desc in self.COMMANDS.items():
            table.add_row(cmd, desc)

        self.console.print(table)

    async def _display_status(self) -> None:
        """Display agent and robot status."""
        table = Table(title="Status", show_header=True)
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="white")

        # Agent status
        if self.agent_loop is not None:
            table.add_row("Agent", "[green]Connected[/green]")
        else:
            table.add_row("Agent", "[yellow]Demo Mode[/yellow]")

        # Turn count
        table.add_row("Turns", str(self._turn_count))

        # History size
        table.add_row("History", f"{len(self._conversation_history)} messages")

        # Try to get daemon status
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.daemon_url}/api/daemon/status",
                    timeout=2.0,
                )
                if response.status_code == 200:
                    status = response.json()
                    table.add_row(
                        "Robot",
                        f"[green]Connected[/green] ({status.get('connection_type', 'unknown')})",
                    )
                    if "head" in status:
                        head = status["head"]
                        table.add_row(
                            "Head Position",
                            f"roll={head.get('roll', 0):.1f}, "
                            f"pitch={head.get('pitch', 0):.1f}, "
                            f"yaw={head.get('yaw', 0):.1f}",
                        )
                else:
                    table.add_row("Robot", "[yellow]Unknown[/yellow]")
        except Exception:
            table.add_row("Robot", "[red]Disconnected[/red]")

        self.console.print(table)

    def _display_history(self) -> None:
        """Display recent conversation history."""
        if not self._conversation_history:
            self.console.print("[dim]No conversation history[/dim]")
            return

        # Show last 10 messages
        recent = self._conversation_history[-10:]

        table = Table(title="Recent History", show_header=True)
        table.add_column("Role", style="cyan", width=10)
        table.add_column("Message", style="white")

        for msg in recent:
            role = msg["role"].capitalize()
            content = msg["content"]
            # Truncate long messages
            if len(content) > 100:
                content = content[:97] + "..."

            if msg["role"] == "user":
                table.add_row(f"[green]{role}[/green]", content)
            else:
                table.add_row(f"[cyan]{role}[/cyan]", content)

        self.console.print(table)

    def _clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history.clear()
        self._turn_count = 0
        self.console.print("[green]Conversation history cleared[/green]")

    async def _display_permissions(self) -> None:
        """Display permission rules."""
        # This would integrate with the permission system
        # For now, show a placeholder
        rules = [
            ("mcp__reachy__*", 1, "Robot body control"),
            ("mcp__home_assistant__*", 2, "Smart home actions"),
            ("mcp__github__create_*", 3, "Create GitHub resources"),
            ("mcp__*__delete_*", 4, "Destructive operations"),
        ]

        self.permission_handler.print_permission_rules(rules)

    async def _compact_conversation(self) -> None:
        """Compact conversation to reduce context size."""
        if len(self._conversation_history) <= 4:
            self.console.print("[dim]Not enough history to compact[/dim]")
            return

        # Keep first and last 2 messages, summarize middle
        old_count = len(self._conversation_history)
        kept = self._conversation_history[:2] + self._conversation_history[-2:]
        self._conversation_history = kept

        self.console.print(
            f"[green]Compacted conversation: {old_count} -> {len(self._conversation_history)} messages[/green]"
        )

    def _display_response(self, response: str) -> None:
        """Display agent response with markdown formatting.

        Args:
            response: The response text to display.
        """
        # Try to render as markdown
        try:
            md = Markdown(response)
            panel = Panel(
                md,
                title="[cyan]Reachy[/cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
            self.console.print(panel)
        except Exception:
            # Fallback to plain text
            self.console.print(f"[cyan]Reachy:[/cyan] {response}")

        self.console.print()

    def get_permission_handler(self) -> CLIPermissionHandler:
        """Get the CLI permission handler for integration.

        Returns:
            The CLIPermissionHandler instance.
        """
        return self.permission_handler


async def main() -> None:
    """Entry point for running REPL standalone."""
    repl = AgentREPL()
    await repl.run()


if __name__ == "__main__":
    asyncio.run(main())
