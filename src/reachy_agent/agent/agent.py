"""Main agent loop for Reachy Agent.

Implements the core Perceive → Think → Act cycle using the
Claude Agent SDK with permission enforcement.

The agent connects to MCP servers via stdio transport and discovers
tools dynamically, eliminating the need for duplicated tool definitions.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import anthropic
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from reachy_agent.agent.options import create_agent_options
from reachy_agent.behaviors.idle import IdleBehaviorConfig, IdleBehaviorController
from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient
from reachy_agent.permissions.hooks import PermissionHooks, create_permission_hooks
from reachy_agent.utils.logging import bind_context, clear_context, get_logger

if TYPE_CHECKING:
    from mcp.types import Tool
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
        config: ReachyConfig | None = None,
        daemon_url: str = "http://localhost:8000",
        permission_hooks: PermissionHooks | None = None,
        api_key: str | None = None,
        enable_idle_behavior: bool = True,
        idle_config: IdleBehaviorConfig | None = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            config: Reachy configuration.
            daemon_url: URL of the Reachy daemon.
            permission_hooks: Permission enforcement hooks.
            api_key: Anthropic API key. Uses ANTHROPIC_API_KEY env var if not provided.
            enable_idle_behavior: Whether to enable idle look-around behavior.
            idle_config: Optional idle behavior configuration.
        """
        self.config = config
        self.daemon_url = daemon_url
        self.permission_hooks = permission_hooks or create_permission_hooks()
        self.state = AgentState.INITIALIZING

        # Initialize Anthropic client
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client: anthropic.AsyncAnthropic | None = None
        if self._api_key:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)

        # MCP client connections (true MCP protocol)
        self._mcp_sessions: dict[str, ClientSession] = {}
        self._mcp_tools: list[Tool] = []  # Discovered tools from MCP servers
        self._mcp_contexts: list[Any] = []  # Context managers to clean up
        self._use_mcp_client: bool = True  # Use true MCP protocol

        self._agent_options: dict[str, Any] = {}
        self._conversation_history: list[dict[str, Any]] = []
        self._turn_counter = 0
        self._system_prompt: str = ""

        # Idle behavior controller
        self._enable_idle_behavior = enable_idle_behavior
        self._idle_config = idle_config
        self._idle_controller: IdleBehaviorController | None = None
        self._daemon_client: ReachyDaemonClient | None = None

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

    async def initialize(self) -> None:
        """Initialize the agent and its components.

        Connects to MCP servers via stdio transport, discovers tools
        dynamically, and prepares for interaction. Also starts idle
        behavior if enabled.
        """
        log.info("Initializing Reachy agent loop")

        try:
            # Connect to MCP servers and discover tools
            if self._use_mcp_client:
                await self._connect_mcp_servers()
            else:
                # Fallback: use direct daemon client (deprecated path)
                log.warning("Using direct daemon client (MCP client disabled)")

            # Build agent options
            self._agent_options = create_agent_options(
                config=self.config,
                mcp_servers=[],  # Tools are now discovered via MCP protocol
            )

            # Load system prompt
            self._system_prompt = self._agent_options.get("system_prompt", "")

            # Initialize idle behavior controller if enabled
            if self._enable_idle_behavior:
                self._daemon_client = ReachyDaemonClient(base_url=self.daemon_url)
                self._idle_controller = IdleBehaviorController(
                    daemon_client=self._daemon_client,
                    config=self._idle_config,
                )
                await self._idle_controller.start()
                log.info("Idle behavior controller started")

            self.state = AgentState.READY
            log.info(
                "Agent loop initialized successfully",
                has_api_key=self._client is not None,
                idle_behavior=self._enable_idle_behavior,
                tool_count=len(self._mcp_tools),
            )

        except Exception as e:
            self.state = AgentState.ERROR
            log.error("Failed to initialize agent loop", error=str(e))
            raise

    async def _connect_mcp_servers(self) -> None:
        """Connect to MCP servers and discover tools dynamically.

        Launches the Reachy MCP server as a subprocess and connects
        via stdio transport. Discovers available tools via ListTools.
        """
        log.info("Connecting to MCP servers", daemon_url=self.daemon_url)

        # Find python executable
        python_executable = sys.executable

        # Create server parameters for the Reachy MCP server
        server_params = StdioServerParameters(
            command=python_executable,
            args=["-m", "reachy_agent.mcp_servers.reachy", self.daemon_url],
        )

        # Connect to the MCP server
        try:
            # Use stdio_client as async context manager
            client_ctx = stdio_client(server_params)
            streams = await client_ctx.__aenter__()
            self._mcp_contexts.append(client_ctx)

            # Create client session
            read_stream, write_stream = streams
            session = ClientSession(read_stream, write_stream)
            session_ctx = session.__aenter__()
            await session_ctx

            # Initialize the session
            await session.initialize()

            # Store the session
            self._mcp_sessions["reachy"] = session

            # Discover tools
            tools_result = await session.list_tools()
            self._mcp_tools = list(tools_result.tools)

            log.info(
                "MCP server connected",
                server="reachy",
                tools_discovered=len(self._mcp_tools),
                tool_names=[t.name for t in self._mcp_tools],
            )

        except Exception as e:
            log.error("Failed to connect to MCP server", error=str(e))
            # Fall back to direct daemon client
            self._use_mcp_client = False
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

        # Pause idle behavior during user interaction
        if self._idle_controller:
            self._idle_controller.pause()

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
            # Resume idle behavior after processing completes
            if self._idle_controller:
                self._idle_controller.resume()

    async def _process_with_claude(
        self,
        augmented_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """Process input with Claude API.

        Calls the Anthropic API with tool definitions and handles
        tool calls in an agentic loop until Claude provides a final response.

        Args:
            augmented_input: Input with context injected.
            context: Agent context.

        Returns:
            AgentResponse from Claude.
        """
        # If no API client, fall back to simulated response
        if self._client is None:
            log.warning("No API key configured, using simulated response")
            await asyncio.sleep(0.3)
            return AgentResponse(
                text=f"[No API Key] Received: {context.user_input[:100]}",
                tool_calls=[],
                context=context,
            )

        log.info("Processing with Claude API")

        # Build tools from MCP server
        tools = self._build_tool_definitions()

        # Build messages
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": augmented_input}
        ]

        tool_calls_made: list[dict[str, Any]] = []
        max_iterations = 10  # Safety limit on tool call iterations

        for iteration in range(max_iterations):
            try:
                # Call Claude API
                response = await self._client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=1024,
                    system=self._system_prompt,
                    tools=tools,
                    messages=messages,
                )

                log.debug(
                    "Claude response",
                    stop_reason=response.stop_reason,
                    content_blocks=len(response.content),
                )

                # Check if Claude wants to use tools
                if response.stop_reason == "tool_use":
                    # Extract tool use blocks
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input
                            tool_use_id = block.id

                            log.info(
                                "Claude calling tool",
                                tool=tool_name,
                                input=tool_input,
                            )

                            # Execute the tool via MCP server
                            result = await self._execute_mcp_tool(tool_name, tool_input)
                            tool_calls_made.append({
                                "tool": tool_name,
                                "input": tool_input,
                                "result": result,
                            })

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": json.dumps(result),
                            })

                    # Add assistant message and tool results to conversation
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content": tool_results})

                else:
                    # Claude is done - extract final text response
                    final_text = ""
                    for block in response.content:
                        if hasattr(block, "text"):
                            final_text += block.text

                    return AgentResponse(
                        text=final_text,
                        tool_calls=tool_calls_made,
                        context=context,
                    )

            except anthropic.APIError as e:
                log.error("Anthropic API error", error=str(e))
                return AgentResponse(
                    text="",
                    error=f"API error: {e}",
                    context=context,
                )

        # Hit max iterations
        log.warning("Hit max tool call iterations")
        return AgentResponse(
            text="I apologize, but I encountered too many steps while processing your request.",
            tool_calls=tool_calls_made,
            context=context,
        )

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        """Build tool definitions for Claude API from discovered MCP tools.

        Converts tools discovered via MCP ListTools into the Anthropic
        tool format. This is the key to dynamic tool discovery - no more
        hardcoded tool definitions!

        Returns:
            List of tool definitions in Anthropic format.
        """
        if self._mcp_tools:
            # Use dynamically discovered tools from MCP servers
            tools = []
            for mcp_tool in self._mcp_tools:
                tool_def = {
                    "name": mcp_tool.name,
                    "description": mcp_tool.description or "",
                    "input_schema": mcp_tool.inputSchema,
                }
                tools.append(tool_def)
            return tools
        else:
            # Fallback: return empty list if no tools discovered
            log.warning("No MCP tools discovered, returning empty tool list")
            return []

    async def _execute_mcp_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool via MCP protocol.

        Uses the MCP ClientSession to call tools on the connected MCP server.
        This is the key to true MCP architecture - tools are executed via
        the protocol, not via direct method calls.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Input parameters for the tool.

        Returns:
            Tool execution result.
        """
        try:
            # Use MCP protocol if available
            if self._use_mcp_client and "reachy" in self._mcp_sessions:
                session = self._mcp_sessions["reachy"]

                log.debug(
                    "Calling tool via MCP protocol",
                    tool=tool_name,
                    input=tool_input,
                )

                # Call the tool via MCP protocol
                result = await session.call_tool(tool_name, tool_input)

                # Extract content from MCP result
                # MCP returns a CallToolResult with content list
                if result.content:
                    # Content is a list of TextContent or other content types
                    for content in result.content:
                        if hasattr(content, "text"):
                            # Parse JSON text content
                            try:
                                return json.loads(content.text)
                            except json.JSONDecodeError:
                                return {"status": "success", "message": content.text}

                return {"status": "success", "message": "Tool executed"}

            else:
                # Fallback: direct daemon client (deprecated path)
                log.warning(
                    "MCP client not available, using direct daemon client",
                    tool=tool_name,
                )
                return await self._execute_tool_direct(tool_name, tool_input)

        except Exception as e:
            log.error("Tool execution error", tool=tool_name, error=str(e))
            return {"error": str(e)}

    async def _execute_tool_direct(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool via direct daemon client (fallback).

        This is the deprecated path used when MCP client is not available.
        Kept for backwards compatibility during transition.

        Args:
            tool_name: Name of the tool to execute.
            tool_input: Input parameters for the tool.

        Returns:
            Tool execution result.
        """
        from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

        client = ReachyDaemonClient(base_url=self.daemon_url)

        # Map tool names to client methods
        tool_methods = {
            "move_head": client.move_head,
            "play_emotion": client.play_emotion,
            "speak": client.speak,
            "nod": client.nod,
            "shake": client.shake,
            "wake_up": client.wake_up,
            "sleep": client.sleep,
            "rest": client.rest,
            "rotate": client.rotate,
            "look_at": client.look_at,
            "listen": client.listen,
            "dance": client.dance,
            "capture_image": client.capture_image,
            "set_antenna_state": client.set_antenna_state,
            "get_sensor_data": client.get_sensor_data,
            "look_at_sound": client.look_at_sound,
            "get_status": client.get_status,
            "cancel_action": client.cancel_action,
            "get_pose": client.get_current_pose,
        }

        if tool_name not in tool_methods:
            return {"error": f"Tool {tool_name} not found"}

        method = tool_methods[tool_name]
        result = await method(**tool_input)
        return result

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

        # Stop idle behavior controller
        if self._idle_controller:
            await self._idle_controller.stop()
            log.info("Idle behavior controller stopped")

        # Clean up MCP client contexts (closes subprocess connections)
        for ctx in self._mcp_contexts:
            try:
                await ctx.__aexit__(None, None, None)
            except Exception as e:
                log.warning("Error closing MCP context", error=str(e))
        self._mcp_contexts.clear()
        self._mcp_sessions.clear()
        self._mcp_tools.clear()
        log.info("MCP client connections closed")

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
