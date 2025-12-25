"""CLI-based permission handler using Rich for formatting.

Provides terminal-based confirmation prompts and notifications
with colorful, formatted output.
"""

from __future__ import annotations

import asyncio
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table
from rich.text import Text

from reachy_agent.permissions.handlers.base import PermissionHandler
from reachy_agent.utils.logging import get_logger

log = get_logger(__name__)


class CLIPermissionHandler(PermissionHandler):
    """CLI-based permission handler using Rich for formatting.

    Displays confirmation prompts and notifications in the terminal
    with color-coded, formatted output.

    Features:
    - Rich panels for confirmation requests
    - Color-coded notifications by permission tier
    - Formatted tables for tool parameters
    - Timeout handling for confirmations

    Example:
        ```python
        handler = CLIPermissionHandler()

        # Request confirmation (blocks until user responds or timeout)
        approved = await handler.request_confirmation(
            tool_name="mcp__calendar__create_event",
            reason="This will create a new calendar event",
            tool_input={"title": "Meeting", "date": "2024-01-15"},
            timeout_seconds=60.0,
        )

        # Display notification
        await handler.notify(
            tool_name="mcp__slack__send_message",
            message="Sent message to #general",
            tier=2,
        )
        ```

    Attributes:
        console: Rich Console instance for output.
    """

    # Tier color mapping
    TIER_COLORS = {
        1: "green",      # Autonomous - executed silently
        2: "blue",       # Notify - informational
        3: "yellow",     # Confirm - requires approval
        4: "red",        # Forbidden - blocked
    }

    TIER_NAMES = {
        1: "Autonomous",
        2: "Notify",
        3: "Confirm",
        4: "Forbidden",
    }

    def __init__(self, console: Console | None = None) -> None:
        """Initialize CLI permission handler.

        Args:
            console: Optional Rich Console instance.
                    If not provided, creates a new one.
        """
        self.console = console or Console()

    async def request_confirmation(
        self,
        tool_name: str,
        reason: str,
        tool_input: dict[str, Any],
        timeout_seconds: float = 60.0,
    ) -> bool:
        """Display confirmation prompt in CLI.

        Shows a formatted panel with tool details and waits for
        user input (y/n). Returns False on timeout.

        Args:
            tool_name: Name of the tool requiring confirmation.
            reason: Human-readable explanation.
            tool_input: Tool parameters to display.
            timeout_seconds: Maximum wait time.

        Returns:
            True if user confirmed, False if denied or timeout.
        """
        # Build parameter table
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="white")

        for key, value in tool_input.items():
            # Truncate long values
            str_value = str(value)
            if len(str_value) > 80:
                str_value = str_value[:77] + "..."
            table.add_row(key, str_value)

        # Create confirmation panel
        content = Text()
        content.append(f"{reason}\n\n", style="white")

        panel = Panel(
            table,
            title=f"[yellow bold]🔒 Confirmation Required: {tool_name}[/yellow bold]",
            subtitle=f"[dim]Timeout in {int(timeout_seconds)}s[/dim]",
            border_style="yellow",
            padding=(1, 2),
        )

        self.console.print()
        self.console.print(panel)
        self.console.print(f"[dim]{reason}[/dim]")
        self.console.print()

        # Get user confirmation with timeout
        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: Confirm.ask(
                        "[yellow bold]Allow this action?[/yellow bold]",
                        console=self.console,
                        default=False,
                    ),
                ),
                timeout=timeout_seconds,
            )

            if result:
                self.console.print("[green]✓ Action approved[/green]")
                log.info("User confirmed action", tool_name=tool_name)
            else:
                self.console.print("[red]✗ Action denied[/red]")
                log.info("User denied action", tool_name=tool_name)

            return result

        except asyncio.TimeoutError:
            self.console.print("[red]⏱ Confirmation timed out - action denied[/red]")
            log.warning(
                "Confirmation timed out",
                tool_name=tool_name,
                timeout_seconds=timeout_seconds,
            )
            return False

    async def notify(
        self,
        tool_name: str,
        message: str,
        tier: int = 2,
    ) -> None:
        """Display notification in CLI.

        Shows a color-coded notification message based on permission tier.

        Args:
            tool_name: Name of the tool that was executed.
            message: Notification message.
            tier: Permission tier (affects color).
        """
        color = self.TIER_COLORS.get(tier, "white")
        tier_name = self.TIER_NAMES.get(tier, f"Tier {tier}")

        # Format: [TIER] tool_name: message
        prefix = f"[{color}][{tier_name}][/{color}]"
        tool_part = f"[bold]{tool_name}[/bold]"

        self.console.print(f"{prefix} {tool_part}: {message}")

        log.debug(
            "Displayed notification",
            tool_name=tool_name,
            tier=tier,
        )

    async def display_error(
        self,
        tool_name: str,
        error: str,
        code: str | None = None,
    ) -> None:
        """Display error message in CLI.

        Shows a red error message with optional error code.

        Args:
            tool_name: Name of the tool that caused the error.
            error: Error message.
            code: Optional error code.
        """
        code_part = f"[{code}] " if code else ""
        self.console.print(
            f"[red bold]✗ Error in {tool_name}:[/red bold] "
            f"[red]{code_part}{error}[/red]"
        )

        log.debug(
            "Displayed error",
            tool_name=tool_name,
            error=error,
            code=code,
        )

    async def on_tool_start(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """Show tool execution start.

        Displays a subtle indicator that a tool is running.

        Args:
            tool_name: Name of the tool being executed.
            tool_input: The tool's input parameters.
        """
        self.console.print(f"[dim]▶ Executing {tool_name}...[/dim]")

    async def on_tool_complete(
        self,
        tool_name: str,
        result: Any,
        duration_ms: int,
    ) -> None:
        """Show tool execution completion.

        Displays a success indicator with duration.

        Args:
            tool_name: Name of the completed tool.
            result: The tool's return value.
            duration_ms: Execution time in milliseconds.
        """
        self.console.print(
            f"[dim]✓ {tool_name} completed in {duration_ms}ms[/dim]"
        )

    def print_permission_rules(
        self,
        rules: list[tuple[str, int, str]],
    ) -> None:
        """Display permission rules in a formatted table.

        Utility method for showing all configured permission rules.

        Args:
            rules: List of (pattern, tier, reason) tuples.
        """
        table = Table(title="Permission Rules", show_header=True)
        table.add_column("Pattern", style="cyan")
        table.add_column("Tier", style="yellow")
        table.add_column("Reason", style="dim")

        for pattern, tier, reason in rules:
            tier_name = self.TIER_NAMES.get(tier, str(tier))
            color = self.TIER_COLORS.get(tier, "white")
            table.add_row(
                pattern,
                f"[{color}]{tier_name}[/{color}]",
                reason,
            )

        self.console.print(table)
