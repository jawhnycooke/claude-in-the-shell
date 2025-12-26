"""Main agent loop for Reachy Agent.

Implements the core Perceive → Think → Act cycle using the
official Claude Agent SDK (ClaudeSDKClient) with permission enforcement.

The agent connects to MCP servers via ClaudeAgentOptions and uses
SDK hooks for 4-tier permission enforcement.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookContext,
    HookMatcher,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from reachy_agent.agent.options import load_system_prompt
from reachy_agent.behaviors.idle import IdleBehaviorConfig, IdleBehaviorController
from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient
from reachy_agent.memory import MemoryManager, build_memory_context
from reachy_agent.memory.types import SessionSummary, UserProfile
from reachy_agent.permissions.tiers import PermissionEvaluator, PermissionTier
from reachy_agent.utils.logging import bind_context, clear_context, get_logger

if TYPE_CHECKING:
    from reachy_agent.utils.config import ReachyConfig

log = get_logger(__name__)

# Type alias for SDK hook input
HookInput = dict[str, Any]
HookJSONOutput = dict[str, Any]


class AgentState(str, Enum):
    """Current state of the agent."""

    INITIALIZING = "initializing"
    READY = "ready"
    PROCESSING = "processing"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class AgentContext:
    """Context information passed to the agent loop."""

    current_time: datetime = field(default_factory=datetime.now)
    user_input: str = ""
    conversation_id: str = ""
    turn_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_context_string(self) -> str:
        """Convert context to string for injection into prompts."""
        return f"""
## Current Context
- Time: {self.current_time.strftime('%Y-%m-%d %H:%M:%S')}
- Day: {self.current_time.strftime('%A')}
- Conversation turn: {self.turn_number}
"""


@dataclass
class AgentResponse:
    """Response from the agent loop."""

    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    context: AgentContext | None = None
    error: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None

    @property
    def success(self) -> bool:
        """Whether the response was successful."""
        return self.error is None


class ReachyAgentLoop:
    """Main agent loop for Reachy embodied AI.

    Uses the official Claude Agent SDK (ClaudeSDKClient) for:
    - Session continuity across multiple exchanges
    - Hook-based permission enforcement (PreToolUse)
    - MCP server integration via ClaudeAgentOptions
    - Interrupt support for robot control

    The core interaction cycle:
    1. Perceive - Gather input from user/sensors
    2. Think - Process with Claude via SDK
    3. Act - Execute tool calls with permission enforcement
    """

    def __init__(
        self,
        config: ReachyConfig | None = None,
        daemon_url: str = "http://localhost:8000",
        api_key: str | None = None,
        enable_idle_behavior: bool = True,
        idle_config: IdleBehaviorConfig | None = None,
        enable_memory: bool = True,
    ) -> None:
        """Initialize the agent loop.

        Args:
            config: Reachy configuration.
            daemon_url: URL of the Reachy daemon.
            api_key: Anthropic API key. Uses ANTHROPIC_API_KEY env var if not provided.
            enable_idle_behavior: Whether to enable idle look-around behavior.
            idle_config: Optional idle behavior configuration.
            enable_memory: Whether to enable memory system for personalization.
        """
        self.config = config
        self.daemon_url = daemon_url
        self.state = AgentState.INITIALIZING

        # SDK client (replaces manual anthropic.AsyncAnthropic)
        self._client: ClaudeSDKClient | None = None
        self._api_key = api_key

        # Permission evaluator for SDK hooks
        self._permission_evaluator = PermissionEvaluator()

        # Agent state
        self._turn_counter = 0
        self._system_prompt: str = ""

        # Idle behavior controller
        self._enable_idle_behavior = enable_idle_behavior
        self._idle_config = idle_config
        self._idle_controller: IdleBehaviorController | None = None
        self._daemon_client: ReachyDaemonClient | None = None

        # Memory system
        self._enable_memory = enable_memory
        self._memory_manager: MemoryManager | None = None
        self._user_profile: UserProfile | None = None
        self._last_session: SessionSummary | None = None

    @property
    def idle_controller(self) -> IdleBehaviorController | None:
        """Get the idle behavior controller if enabled."""
        return self._idle_controller

    @property
    def is_idle_behavior_active(self) -> bool:
        """Check if idle behavior is currently running (not paused)."""
        if self._idle_controller is None:
            return False
        return self._idle_controller.is_running

    def _build_mcp_servers(self) -> dict[str, dict[str, Any]]:
        """Build MCP server configuration for SDK.

        Returns:
            Dictionary mapping server names to their stdio configurations.
        """
        python_executable = sys.executable
        servers: dict[str, dict[str, Any]] = {}

        # Reachy MCP server (robot control)
        servers["reachy"] = {
            "type": "stdio",
            "command": python_executable,
            "args": ["-m", "reachy_agent.mcp_servers.reachy", self.daemon_url],
        }

        # Memory MCP server (if enabled)
        if self._enable_memory:
            servers["memory"] = {
                "type": "stdio",
                "command": python_executable,
                "args": ["-m", "reachy_agent.mcp_servers.memory"],
            }

        return servers

    def _build_allowed_tools(self) -> list[str]:
        """Build list of allowed MCP tools.

        SDK prefixes MCP tools as: mcp__<server>__<tool>

        Returns:
            List of fully qualified tool names.
        """
        # Reachy MCP tools (23 tools)
        reachy_tools = [
            "move_head",
            "play_emotion",
            "speak",
            "nod",
            "shake",
            "wake_up",
            "sleep",
            "rest",
            "rotate",
            "look_at",
            "listen",
            "dance",
            "capture_image",
            "set_antenna_state",
            "get_sensor_data",
            "look_at_sound",
            "get_status",
            "cancel_action",
            "get_pose",
            "tilt_head",
            "express_emotion",
            "wiggle_antenna",
            "set_led_color",
        ]

        # Memory MCP tools (4 tools)
        memory_tools = [
            "search_memories",
            "store_memory",
            "get_user_profile",
            "update_user_profile",
        ]

        allowed = []

        # Add Reachy tools
        for tool in reachy_tools:
            allowed.append(f"mcp__reachy__{tool}")

        # Add Memory tools if enabled
        if self._enable_memory:
            for tool in memory_tools:
                allowed.append(f"mcp__memory__{tool}")

        return allowed

    async def _permission_hook(
        self,
        input_data: HookInput,
        tool_use_id: str | None,
        context: HookContext,
    ) -> HookJSONOutput:
        """4-tier permission enforcement via SDK PreToolUse hook.

        Enforces:
        - AUTONOMOUS: Allow without confirmation
        - NOTIFY: Log and allow
        - CONFIRM: Ask user (returns "ask" decision)
        - FORBIDDEN: Block (returns "deny" decision)

        Args:
            input_data: Hook input with tool_name and tool_input.
            tool_use_id: Optional tool use ID.
            context: Hook context.

        Returns:
            Hook output with permission decision.
        """
        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Strip SDK prefix to get original tool name for evaluation
        # SDK format: mcp__server__tool → extract tool
        original_tool = tool_name
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__")
            if len(parts) >= 3:
                original_tool = parts[2]

        # Evaluate permission tier
        decision = self._permission_evaluator.evaluate(original_tool)

        log.info(
            "SDK permission hook",
            tool_name=tool_name,
            original_tool=original_tool,
            tier=decision.tier.name,
            allowed=decision.allowed,
        )

        if decision.tier == PermissionTier.FORBIDDEN:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"Tool {original_tool} is forbidden: {decision.reason}",
                }
            }

        if decision.needs_confirmation:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": f"Confirm {original_tool}? {decision.reason}",
                }
            }

        if decision.should_notify:
            log.info(
                "Notify tier tool execution",
                tool=original_tool,
                input=tool_input,
            )

        # AUTONOMOUS or NOTIFY: allow
        return {}

    def _build_sdk_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions for the SDK client.

        Returns:
            Configured ClaudeAgentOptions instance.
        """
        return ClaudeAgentOptions(
            # System prompt with memory context
            system_prompt=self._system_prompt,
            # MCP servers (SDK handles stdio transport)
            mcp_servers=self._build_mcp_servers(),
            # Permission hooks
            hooks={
                "PreToolUse": [
                    HookMatcher(matcher=None, hooks=[self._permission_hook])
                ]
            },
            # Allowed tools
            allowed_tools=self._build_allowed_tools(),
            # Limits
            max_turns=10,
        )

    async def initialize(self) -> None:
        """Initialize the agent and its components.

        Loads system prompt, initializes memory, starts idle behavior,
        and connects to MCP servers via SDK.
        """
        log.info("Initializing Reachy agent loop with Claude Agent SDK")

        try:
            # Load system prompt
            self._system_prompt = load_system_prompt(config=self.config)

            # Initialize memory system if enabled
            if self._enable_memory:
                await self._initialize_memory()

            # Update system prompt with memory context
            if self._enable_memory and (self._user_profile or self._last_session):
                memory_context = build_memory_context(
                    profile=self._user_profile,
                    last_session=self._last_session,
                )
                if memory_context:
                    self._system_prompt = f"{self._system_prompt}\n\n{memory_context}"

            # Initialize idle behavior controller if enabled
            if self._enable_idle_behavior:
                self._daemon_client = ReachyDaemonClient(base_url=self.daemon_url)
                self._idle_controller = IdleBehaviorController(
                    daemon_client=self._daemon_client,
                    config=self._idle_config,
                )
                await self._idle_controller.start()
                log.info("Idle behavior controller started")

            # Create SDK client (don't connect yet - connect on first query)
            options = self._build_sdk_options()
            self._client = ClaudeSDKClient(options)

            self.state = AgentState.READY
            log.info(
                "Agent loop initialized with Claude Agent SDK",
                idle_behavior=self._enable_idle_behavior,
                memory_enabled=self._enable_memory,
                mcp_servers=list(self._build_mcp_servers().keys()),
            )

        except Exception as e:
            self.state = AgentState.ERROR
            log.error("Failed to initialize agent loop", error=str(e))
            raise

    async def _initialize_memory(self) -> None:
        """Initialize the memory system.

        Loads user profile, last session, and starts a new session.
        Memory context will be auto-injected into system prompt.
        """
        log.info("Initializing memory system")

        # Get memory paths from config or use defaults
        memory_config = getattr(self.config, "memory", None) if self.config else None
        if memory_config is not None:
            chroma_path = memory_config.chroma_path
            sqlite_path = memory_config.sqlite_path
            embedding_model = memory_config.embedding_model
            retention_days = memory_config.retention_days
        else:
            chroma_path = "~/.reachy/memory/chroma"
            sqlite_path = "~/.reachy/memory/reachy.db"
            embedding_model = "all-MiniLM-L6-v2"
            retention_days = 90

        try:
            # Create and initialize memory manager
            self._memory_manager = MemoryManager(
                chroma_path=chroma_path,
                sqlite_path=sqlite_path,
                embedding_model=embedding_model,
                retention_days=retention_days,
            )
            await self._memory_manager.initialize()

            # Load user profile and last session for context injection
            self._user_profile = await self._memory_manager.get_profile()
            self._last_session = await self._memory_manager.get_last_session()

            # Start a new session
            await self._memory_manager.start_session()

            log.info(
                "Memory system initialized",
                user_name=self._user_profile.name,
                has_last_session=self._last_session is not None,
            )

        except Exception as e:
            log.warning("Memory system failed to initialize", error=str(e))
            # Memory is optional - continue without it
            self._memory_manager = None
            self._enable_memory = False

    async def process_input(
        self,
        user_input: str,
        context: AgentContext | None = None,
    ) -> AgentResponse:
        """Process user input through the agent loop.

        This is the main entry point for the Perceive → Think → Act cycle.
        Uses ClaudeSDKClient for session continuity and hook-based permissions.

        Args:
            user_input: Text input from the user.
            context: Optional context information.

        Returns:
            AgentResponse with the result.
        """
        if self.state != AgentState.READY:
            return AgentResponse(
                text="",
                error=f"Agent not ready. Current state: {self.state.value}",
            )

        if self._client is None:
            return AgentResponse(
                text="",
                error="Agent client not initialized",
            )

        self.state = AgentState.PROCESSING
        self._turn_counter += 1

        # Pause idle behavior during user interaction
        if self._idle_controller:
            await self._idle_controller.pause()

        # Create context if not provided
        if context is None:
            context = AgentContext(
                user_input=user_input,
                turn_number=self._turn_counter,
            )
        else:
            context.user_input = user_input
            context.turn_number = self._turn_counter

        # Bind logging context
        bind_context(
            turn=self._turn_counter,
            input_length=len(user_input),
        )

        log.info("Processing user input via SDK", input_preview=user_input[:50])

        try:
            # Build augmented input with context
            augmented_input = self._build_augmented_input(user_input, context)

            # Process with SDK client
            response = await self._process_with_sdk(augmented_input, context)

            self.state = AgentState.READY
            return response

        except Exception as e:
            log.error("Error processing input", error=str(e))
            self.state = AgentState.READY  # Recover to ready state
            return AgentResponse(
                text="",
                error=str(e),
                context=context,
            )

        finally:
            clear_context()
            # Resume idle behavior after processing completes
            if self._idle_controller:
                await self._idle_controller.resume()

    async def _process_with_sdk(
        self,
        augmented_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """Process input with Claude Agent SDK.

        Uses ClaudeSDKClient for:
        - Session continuity (remembers conversation)
        - Automatic tool execution via MCP
        - Hook-based permission enforcement

        Args:
            augmented_input: Input with context injected.
            context: Agent context.

        Returns:
            AgentResponse from Claude.
        """
        if self._client is None:
            return AgentResponse(
                text="",
                error="SDK client not initialized",
                context=context,
            )

        log.info("Processing with Claude Agent SDK")

        tool_calls_made: list[dict[str, Any]] = []
        response_text = ""
        cost_usd: float | None = None
        duration_ms: int | None = None

        try:
            # Use SDK client as context manager for this query
            async with ClaudeSDKClient(options=self._build_sdk_options()) as client:
                # Send query to Claude
                await client.query(augmented_input)

                # Process response stream
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_text += block.text
                            elif isinstance(block, ToolUseBlock):
                                log.info(
                                    "SDK tool call",
                                    tool=block.name,
                                    input=block.input,
                                )
                                tool_calls_made.append({
                                    "tool": block.name,
                                    "input": block.input,
                                })
                            elif isinstance(block, ToolResultBlock):
                                log.debug(
                                    "Tool result",
                                    tool_use_id=block.tool_use_id,
                                )

                    elif isinstance(message, ResultMessage):
                        cost_usd = message.total_cost_usd
                        duration_ms = message.duration_ms
                        log.info(
                            "SDK query completed",
                            cost_usd=cost_usd,
                            duration_ms=duration_ms,
                            num_turns=message.num_turns,
                        )

            return AgentResponse(
                text=response_text,
                tool_calls=tool_calls_made,
                context=context,
                cost_usd=cost_usd,
                duration_ms=duration_ms,
            )

        except Exception as e:
            log.error("SDK error", error=str(e))
            return AgentResponse(
                text="",
                error=f"SDK error: {e}",
                context=context,
            )

    def _build_augmented_input(
        self,
        user_input: str,
        context: AgentContext,
    ) -> str:
        """Build input with injected context.

        Injects:
        - Current time and conversation context

        Note: Memory context is now injected into system prompt,
        not per-message, for better SDK compatibility.

        Args:
            user_input: Original user input.
            context: Context to inject.

        Returns:
            Augmented input string.
        """
        parts = []

        # Add agent context (time, turn number)
        parts.append(context.to_context_string())

        # Add user input
        parts.append(f"\nUser: {user_input}")

        return "\n".join(parts)

    async def shutdown(self, session_summary: str = "") -> None:
        """Shutdown the agent loop gracefully.

        Args:
            session_summary: Optional summary of the session for memory.
        """
        log.info("Shutting down agent loop")
        self.state = AgentState.SHUTDOWN

        # Stop idle behavior controller
        if self._idle_controller:
            await self._idle_controller.stop()
            log.info("Idle behavior controller stopped")

        # Save session and close memory system
        if self._memory_manager:
            try:
                await self._memory_manager.end_session(
                    summary_text=session_summary,
                    key_topics=[],  # Could be populated by conversation analysis
                )
                await self._memory_manager.close()
                log.info("Memory system closed")
            except Exception as e:
                log.warning("Error closing memory system", error=str(e))

        # SDK client manages its own cleanup via context manager
        # No explicit MCP cleanup needed - SDK handles it

        # Close daemon client if used
        if self._daemon_client:
            await self._daemon_client.close()

        log.info("Agent loop shutdown complete")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[ReachyAgentLoop, None]:
        """Context manager for agent session.

        Handles initialization and cleanup automatically.

        Yields:
            Initialized agent loop.
        """
        try:
            await self.initialize()
            yield self
        finally:
            await self.shutdown()


async def create_agent_loop(
    config: ReachyConfig | None = None,
    daemon_url: str = "http://localhost:8000",
) -> ReachyAgentLoop:
    """Create and initialize an agent loop.

    Convenience function that creates and initializes the agent.

    Args:
        config: Reachy configuration.
        daemon_url: URL of the Reachy daemon.

    Returns:
        Initialized ReachyAgentLoop.
    """
    loop = ReachyAgentLoop(config=config, daemon_url=daemon_url)
    await loop.initialize()
    return loop
