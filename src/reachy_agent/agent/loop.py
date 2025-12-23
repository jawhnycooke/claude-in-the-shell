"""Main agent loop for Reachy Agent.

Implements the core Perceive → Think → Act cycle using the
Claude Agent SDK with permission enforcement.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncGenerator

from reachy_agent.agent.options import create_agent_options
from reachy_agent.mcp_servers.reachy import create_reachy_mcp_server
from reachy_agent.permissions.hooks import PermissionHooks, create_permission_hooks
from reachy_agent.permissions.tiers import PermissionEvaluator
from reachy_agent.utils.logging import bind_context, clear_context, get_logger

if TYPE_CHECKING:
    from reachy_agent.utils.config import ReachyConfig

log = get_logger(__name__)


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

    @property
    def success(self) -> bool:
        """Whether the response was successful."""
        return self.error is None


class ReachyAgentLoop:
    """Main agent loop for Reachy embodied AI.

    Implements the core interaction cycle:
    1. Perceive - Gather input from user/sensors
    2. Think - Process with Claude via Agent SDK
    3. Act - Execute tool calls with permission enforcement
    """

    def __init__(
        self,
        config: "ReachyConfig | None" = None,
        daemon_url: str = "http://localhost:8000",
        permission_hooks: PermissionHooks | None = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            config: Reachy configuration.
            daemon_url: URL of the Reachy daemon.
            permission_hooks: Permission enforcement hooks.
        """
        self.config = config
        self.daemon_url = daemon_url
        self.permission_hooks = permission_hooks or create_permission_hooks()
        self.state = AgentState.INITIALIZING

        self._mcp_server = None
        self._agent_options: dict[str, Any] = {}
        self._conversation_history: list[dict[str, Any]] = []
        self._turn_counter = 0

    async def initialize(self) -> None:
        """Initialize the agent and its components.

        Sets up MCP servers, configures the agent, and prepares
        for interaction.
        """
        log.info("Initializing Reachy agent loop")

        try:
            # Create MCP server for Reachy body control
            self._mcp_server = create_reachy_mcp_server(
                config=self.config,
                daemon_url=self.daemon_url,
            )

            # Build agent options
            self._agent_options = create_agent_options(
                config=self.config,
                mcp_servers=[self._mcp_server],
            )

            self.state = AgentState.READY
            log.info("Agent loop initialized successfully")

        except Exception as e:
            self.state = AgentState.ERROR
            log.error("Failed to initialize agent loop", error=str(e))
            raise

    async def process_input(
        self,
        user_input: str,
        context: AgentContext | None = None,
    ) -> AgentResponse:
        """Process user input through the agent loop.

        This is the main entry point for the Perceive → Think → Act cycle.

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

        self.state = AgentState.PROCESSING
        self._turn_counter += 1

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

        log.info("Processing user input", input_preview=user_input[:50])

        try:
            # Build the prompt with context
            augmented_input = self._build_augmented_input(user_input, context)

            # Add to conversation history
            self._conversation_history.append({
                "role": "user",
                "content": augmented_input,
            })

            # Process with Claude (simulated for now - actual SDK integration in Phase 2)
            response = await self._process_with_claude(augmented_input, context)

            # Add response to history
            self._conversation_history.append({
                "role": "assistant",
                "content": response.text,
            })

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

    async def _process_with_claude(
        self,
        augmented_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """Process input with Claude API.

        Note: This is a simplified implementation for Phase 1.
        Full Agent SDK integration will be completed in Phase 2
        when running on actual hardware.

        Args:
            augmented_input: Input with context injected.
            context: Agent context.

        Returns:
            AgentResponse from Claude.
        """
        # For Phase 1, we simulate the agent response
        # This will be replaced with actual Agent SDK calls
        log.info("Processing with Claude (simulated for Phase 1)")

        # Simulate thinking time
        await asyncio.sleep(0.5)

        # Return a placeholder response
        # In Phase 2, this will use the actual Claude Agent SDK
        return AgentResponse(
            text=f"[Simulated Response] Received: {context.user_input[:100]}",
            tool_calls=[],
            context=context,
        )

    def _build_augmented_input(
        self,
        user_input: str,
        context: AgentContext,
    ) -> str:
        """Build input with injected context.

        Args:
            user_input: Original user input.
            context: Context to inject.

        Returns:
            Augmented input string.
        """
        context_str = context.to_context_string()
        return f"{context_str}\n\nUser: {user_input}"

    async def execute_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool with permission enforcement.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Input parameters for the tool.

        Returns:
            Tool execution result.
        """
        log.info("Executing tool", tool_name=tool_name)

        # Pre-tool permission check
        pre_result = await self.permission_hooks.pre_tool_use(tool_name, tool_input)

        if pre_result and "error" in pre_result:
            log.warning("Tool blocked by permissions", tool_name=tool_name)
            return pre_result

        execution_id = pre_result.get("_execution_id") if pre_result else None

        try:
            # Execute the tool via MCP server
            # This is handled by the Agent SDK in production
            result = {"status": "success", "message": f"Executed {tool_name}"}

            # Post-tool audit
            await self.permission_hooks.post_tool_use(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=result,
                execution_id=execution_id,
            )

            return result

        except Exception as e:
            await self.permission_hooks.post_tool_use(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_result=None,
                execution_id=execution_id,
                error=e,
            )
            raise

    async def shutdown(self) -> None:
        """Shutdown the agent loop gracefully."""
        log.info("Shutting down agent loop")
        self.state = AgentState.SHUTDOWN

        # Clean up resources
        if self._mcp_server:
            # MCP server cleanup will be implemented as needed
            pass

        log.info("Agent loop shutdown complete")

    @asynccontextmanager
    async def session(self) -> AsyncGenerator["ReachyAgentLoop", None]:
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
    config: "ReachyConfig | None" = None,
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
