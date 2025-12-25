"""CLI module for Reachy Agent.

Provides interactive command-line interface for agent conversations,
using Rich for formatting and prompt_toolkit for input handling.
"""

from reachy_agent.cli.repl import AgentREPL

__all__ = ["AgentREPL"]
