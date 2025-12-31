"""Claude Agent SDK options configuration.

Configures the Claude Agent with appropriate settings for
embodied AI operation on Reachy Mini.

Now uses the official Claude Agent SDK (ClaudeAgentOptions) for
configuration. Maintains backwards compatibility with existing
dictionary-based options.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from claude_agent_sdk import ClaudeAgentOptions, HookContext, HookMatcher

from reachy_agent.utils.config import ClaudeModel
from reachy_agent.utils.logging import get_logger

if TYPE_CHECKING:
    from reachy_agent.utils.config import ReachyConfig

log = get_logger(__name__)

# Type aliases for SDK hooks
HookInput = dict[str, Any]
HookJSONOutput = dict[str, Any]
HookFunction = Callable[[HookInput, str | None, HookContext], HookJSONOutput]

# Default prompts directory - try multiple strategies for robustness
def _find_prompts_dir() -> Path:
    """Find the prompts directory using multiple strategies.

    This handles both development (src layout) and installed package scenarios,
    as well as editable installs where __file__ may resolve differently.
    """
    candidates = [
        # Strategy 1: Relative to __file__ (works in standard src layout)
        Path(__file__).parent.parent.parent.parent / "prompts",
        # Strategy 2: Current working directory (reliable for CLI invocation)
        Path.cwd() / "prompts",
        # Strategy 3: Home directory config
        Path.home() / ".reachy" / "prompts",
    ]

    for candidate in candidates:
        if candidate.exists() and (candidate / "system").exists():
            return candidate

    # Fallback to first candidate even if not found
    return candidates[0]


PROMPTS_DIR = _find_prompts_dir()


def render_template(template: str, context: dict[str, str]) -> str:
    """Render a template string with context variables.

    Uses {{variable}} syntax for substitution.

    Args:
        template: Template string with {{variable}} placeholders.
        context: Dictionary of variable names to values.

    Returns:
        Rendered template with substitutions applied.
    """
    result = template
    for key, value in context.items():
        result = result.replace(f"{{{{{key}}}}}", str(value))
    return result


def get_default_context(config: ReachyConfig | None = None) -> dict[str, str]:
    """Get default context variables for prompt rendering.

    Args:
        config: Optional configuration for dynamic values.

    Returns:
        Dictionary of context variables.
    """
    now = datetime.now()
    return {
        "agent_name": config.agent.name if config else "Jarvis",
        "current_time": now.strftime("%H:%M"),
        "day_of_week": now.strftime("%A"),
        "turn_number": "1",
        "current_mood": "neutral",
        "energy_level": "high",
        "recent_summary": "Session just started.",
        "owner_name": "User",
        "preferences": "None specified",
        "schedule_patterns": "None specified",
        "connected_services": "None configured",
    }


def load_prompt_file(
    prompt_name: str,
    prompts_dir: Path | None = None,
) -> str | None:
    """Load a prompt file by name from the prompts directory.

    Args:
        prompt_name: Name of prompt file (e.g., 'system/default.md').
        prompts_dir: Optional prompts directory override.

    Returns:
        Prompt content or None if not found.
    """
    base_dir = prompts_dir or PROMPTS_DIR

    # Try exact path first
    prompt_path = base_dir / prompt_name
    if prompt_path.exists():
        log.debug("Loading prompt file", path=str(prompt_path))
        return prompt_path.read_text()

    # Try with .md extension
    if not prompt_name.endswith(".md"):
        prompt_path = base_dir / f"{prompt_name}.md"
        if prompt_path.exists():
            log.debug("Loading prompt file", path=str(prompt_path))
            return prompt_path.read_text()

    return None


def load_system_prompt(
    prompt_path: Path | None = None,
    config: ReachyConfig | None = None,
    prompts_dir: Path | None = None,
) -> str:
    """Load and render the system prompt from external files.

    Search order:
    1. Explicit prompt_path if provided
    2. prompts/system/default.md
    3. prompts/system/personality.md (full personality)
    4. Legacy paths (CLAUDE.md, config/CLAUDE.md)

    Args:
        prompt_path: Optional path to specific prompt file.
        config: Optional configuration for dynamic context.
        prompts_dir: Optional prompts directory override.

    Returns:
        Rendered system prompt string.
    """
    context = get_default_context(config)
    base_dir = prompts_dir or PROMPTS_DIR

    # 1. Explicit path
    if prompt_path and prompt_path.exists():
        log.info("Loading system prompt from explicit path", path=str(prompt_path))
        template = prompt_path.read_text()
        return render_template(template, context)

    # 2. Default prompt from prompts folder
    default_prompt = load_prompt_file("system/default.md", base_dir)
    if default_prompt:
        log.info("Loading system prompt", path="prompts/system/default.md")
        return render_template(default_prompt, context)

    # 3. Personality prompt (fuller version)
    personality_prompt = load_prompt_file("system/personality.md", base_dir)
    if personality_prompt:
        log.info("Loading system prompt", path="prompts/system/personality.md")
        return render_template(personality_prompt, context)

    # 4. Legacy paths for backwards compatibility
    legacy_paths = [
        Path("CLAUDE.md"),
        Path("config/CLAUDE.md"),
        Path.home() / ".reachy" / "CLAUDE.md",
    ]

    for path in legacy_paths:
        if path.exists():
            log.info("Loading system prompt from legacy path", path=str(path))
            template = path.read_text()
            return render_template(template, context)

    # 5. Minimal fallback (should not happen with proper prompts folder)
    log.warning("No prompt files found, using minimal fallback")
    name = config.agent.name if config else "Jarvis"
    return f"You are {name}, an embodied AI assistant robot. Be helpful and expressive."


def load_persona_prompt(
    persona: Any,  # PersonaConfig, but avoid circular import
    config: ReachyConfig | None = None,
    prompts_dir: Path | None = None,
) -> str:
    """Load and render a persona-specific system prompt.

    Used for persona-based wake word switching.
    Falls back to default system prompt if persona prompt not found or on error.

    Args:
        persona: PersonaConfig instance with prompt_path attribute
        config: Optional configuration for dynamic context
        prompts_dir: Optional prompts directory override

    Returns:
        Rendered persona prompt string
    """
    context = get_default_context(config)
    base_dir = prompts_dir or PROMPTS_DIR
    persona_name = getattr(persona, "name", "unknown")

    def _try_load_prompt(prompt_path: Path) -> str | None:
        """Attempt to load and render a prompt file with error handling."""
        if not prompt_path.exists():
            return None
        try:
            log.info(
                "Loading persona prompt",
                persona=persona_name,
                path=str(prompt_path),
            )
            template = prompt_path.read_text(encoding="utf-8")
            return render_template(template, context)
        except (OSError, UnicodeDecodeError) as e:
            log.warning(
                "Failed to read persona prompt file",
                persona=persona_name,
                path=str(prompt_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None
        except (TypeError, AttributeError, KeyError) as e:
            # Specific exceptions from template rendering: type conversion errors,
            # missing attributes, or invalid context keys
            log.warning(
                "Failed to render persona prompt template",
                persona=persona_name,
                path=str(prompt_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            return None

    # Try persona-specific prompt path from multiple locations
    if hasattr(persona, "prompt_path") and persona.prompt_path:
        # Try relative to project root (base_dir.parent)
        result = _try_load_prompt(base_dir.parent / persona.prompt_path)
        if result is not None:
            return result

        # Try relative to prompts dir
        result = _try_load_prompt(base_dir / persona.prompt_path)
        if result is not None:
            return result

        # Try direct path from cwd
        result = _try_load_prompt(Path(persona.prompt_path))
        if result is not None:
            return result

    # Fallback to default system prompt
    log.warning(
        "Persona prompt not found, using default",
        persona=persona_name,
        prompt_path=getattr(persona, "prompt_path", None),
    )
    return load_system_prompt(config=config, prompts_dir=prompts_dir)


class AgentOptionsBuilder:
    """Builder for Claude Agent SDK options.

    Constructs the options dictionary for initializing the Claude Agent
    with Reachy-specific configuration.
    """

    def __init__(self, config: ReachyConfig | None = None) -> None:
        """Initialize the options builder.

        Args:
            config: Reachy configuration instance.
        """
        self.config = config
        self._options: dict[str, Any] = {}
        self._mcp_servers: list[Any] = []

    def with_model(self, model: str | None = None) -> AgentOptionsBuilder:
        """Set the Claude model to use.

        Args:
            model: Model identifier. Uses config default if None.

        Returns:
            Self for chaining.
        """
        if model:
            self._options["model"] = model
        elif self.config:
            self._options["model"] = self.config.agent.model.value
        else:
            self._options["model"] = ClaudeModel.SONNET.value

        return self

    def with_max_tokens(self, max_tokens: int | None = None) -> AgentOptionsBuilder:
        """Set maximum tokens for responses.

        Args:
            max_tokens: Token limit. Uses config default if None.

        Returns:
            Self for chaining.
        """
        if max_tokens:
            self._options["max_tokens"] = max_tokens
        elif self.config:
            self._options["max_tokens"] = self.config.agent.max_tokens
        else:
            self._options["max_tokens"] = 1024

        return self

    def with_system_prompt(
        self,
        prompt: str | None = None,
        prompt_path: Path | None = None,
    ) -> AgentOptionsBuilder:
        """Set the system prompt.

        Args:
            prompt: Direct prompt string.
            prompt_path: Path to CLAUDE.md file.

        Returns:
            Self for chaining.
        """
        if prompt:
            self._options["system_prompt"] = prompt
        else:
            self._options["system_prompt"] = load_system_prompt(
                prompt_path, self.config
            )

        return self

    def with_mcp_server(self, server: Any) -> AgentOptionsBuilder:
        """Add an MCP server.

        Args:
            server: MCP server instance.

        Returns:
            Self for chaining.
        """
        self._mcp_servers.append(server)
        return self

    def with_api_key(self, api_key: str | None = None) -> AgentOptionsBuilder:
        """Set the Anthropic API key.

        Args:
            api_key: API key string. Uses environment if None.

        Returns:
            Self for chaining.
        """
        import os

        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if key:
            self._options["api_key"] = key

        return self

    def build(self) -> dict[str, Any]:
        """Build the final options dictionary.

        Returns:
            Options dictionary for Claude Agent SDK.
        """
        options = dict(self._options)

        if self._mcp_servers:
            options["mcp_servers"] = self._mcp_servers

        log.info(
            "Built agent options",
            model=options.get("model"),
            max_tokens=options.get("max_tokens"),
            mcp_server_count=len(self._mcp_servers),
        )

        return options


def create_agent_options(
    config: ReachyConfig | None = None,
    mcp_servers: list[Any] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Create agent options with sensible defaults.

    Convenience function that builds options with common settings.

    Args:
        config: Reachy configuration.
        mcp_servers: List of MCP servers to register.
        api_key: Optional API key override.

    Returns:
        Options dictionary for Claude Agent SDK.
    """
    builder = (
        AgentOptionsBuilder(config)
        .with_model()
        .with_max_tokens()
        .with_system_prompt()
        .with_api_key(api_key)
    )

    if mcp_servers:
        for server in mcp_servers:
            builder.with_mcp_server(server)

    return builder.build()


# ─────────────────────────────────────────────────────────────────
# SDK-Specific Factory Functions
# ─────────────────────────────────────────────────────────────────


def build_mcp_server_config(
    daemon_url: str = "http://localhost:8000",
    enable_memory: bool = True,
) -> dict[str, dict[str, Any]]:
    """Build MCP server configuration for SDK.

    Creates stdio-based MCP server configurations that the SDK
    will manage (launch subprocesses, handle transport).

    Args:
        daemon_url: URL of the Reachy daemon for robot control.
        enable_memory: Whether to include memory MCP server.

    Returns:
        Dictionary mapping server names to their stdio configurations.
    """
    python_executable = sys.executable
    servers: dict[str, dict[str, Any]] = {}

    # Reachy MCP server (robot control - 23 tools)
    servers["reachy"] = {
        "type": "stdio",
        "command": python_executable,
        "args": ["-m", "reachy_agent.mcp_servers.reachy", daemon_url],
    }

    # Memory MCP server (4 tools)
    if enable_memory:
        servers["memory"] = {
            "type": "stdio",
            "command": python_executable,
            "args": ["-m", "reachy_agent.mcp_servers.memory"],
        }

    return servers


def build_sdk_agent_options(
    system_prompt: str,
    mcp_servers: dict[str, dict[str, Any]] | None = None,
    permission_hook: HookFunction | None = None,
    allowed_tools: list[str] | None = None,
    max_turns: int = 10,
    daemon_url: str = "http://localhost:8000",
    enable_memory: bool = True,
) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions for the SDK.

    Creates a fully-configured ClaudeAgentOptions instance for use
    with ClaudeSDKClient. This is the primary factory for SDK usage.

    Args:
        system_prompt: System prompt for Claude.
        mcp_servers: MCP server configuration. Uses defaults if None.
        permission_hook: Optional PreToolUse hook for permissions.
        allowed_tools: List of allowed MCP tools. Defaults to empty list if None
            (SDK behavior: empty list means no tool filtering).
        max_turns: Maximum agent turns per query.
        daemon_url: Reachy daemon URL (used if mcp_servers is None).
        enable_memory: Enable memory MCP server (used if mcp_servers is None).

    Returns:
        Configured ClaudeAgentOptions instance.

    Example:
        >>> options = build_sdk_agent_options(
        ...     system_prompt="You are Reachy, a helpful robot.",
        ...     permission_hook=my_permission_hook,
        ... )
        >>> async with ClaudeSDKClient(options=options) as client:
        ...     await client.query("Hello!")
    """
    # Use provided servers or build defaults
    servers = mcp_servers or build_mcp_server_config(daemon_url, enable_memory)

    # Build hooks if permission_hook provided
    hooks: dict[str, list[HookMatcher]] | None = None
    if permission_hook is not None:
        hooks = {
            "PreToolUse": [HookMatcher(matcher=None, hooks=[permission_hook])]
        }

    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        mcp_servers=servers,
        hooks=hooks,
        allowed_tools=allowed_tools or [],
        max_turns=max_turns,
    )
