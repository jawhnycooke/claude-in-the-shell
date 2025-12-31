"""Main agent loop for Reachy Agent.

Implements the core Perceive → Think → Act cycle using the
official Claude Agent SDK (ClaudeSDKClient) with permission enforcement.

The agent connects to MCP servers via ClaudeAgentOptions and uses
SDK hooks for 4-tier permission enforcement.
"""

from __future__ import annotations

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
from reachy_agent.behaviors import (
    BlendControllerConfig,
    BreathingConfig,
    BreathingMotion,
    HeadPose,
    HeadWobble,
    IdleBehaviorConfig,
    IdleBehaviorController,
    MotionBlendController,
    WobbleConfig,
)
from reachy_agent.mcp_servers.integrations import (
    build_github_mcp_config,
    get_all_github_tools,
    get_github_token,
    is_binary_available,
    is_docker_available,
)
from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient
from reachy_agent.memory import MemoryManager, build_memory_context
from reachy_agent.memory.types import SessionSummary, UserProfile
from reachy_agent.permissions.tiers import PermissionEvaluator, PermissionTier
from reachy_agent.utils.logging import bind_context, clear_context, get_logger

if TYPE_CHECKING:
    from reachy_agent.mcp_servers.reachy.sdk_client import ReachySDKClient
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
        enable_github: bool = False,
        github_toolsets: list[str] | None = None,
        enable_motion_blend: bool = True,
        blend_config: BlendControllerConfig | None = None,
        breathing_config: BreathingConfig | None = None,
        wobble_config: WobbleConfig | None = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            config: Reachy configuration.
            daemon_url: URL of the Reachy daemon.
            api_key: Anthropic API key. Uses ANTHROPIC_API_KEY env var if not provided.
            enable_idle_behavior: Whether to enable idle look-around behavior.
            idle_config: Optional idle behavior configuration.
            enable_memory: Whether to enable memory system for personalization.
            enable_github: Whether to enable GitHub MCP server integration.
            github_toolsets: List of GitHub toolsets to enable (repos, issues, etc.).
            enable_motion_blend: Whether to enable motion blending system.
            blend_config: Optional motion blend controller configuration.
            breathing_config: Optional breathing motion configuration.
            wobble_config: Optional head wobble configuration.
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

        # Motion blending system
        self._enable_motion_blend = enable_motion_blend
        self._blend_config = blend_config
        self._breathing_config = breathing_config
        self._wobble_config = wobble_config
        self._blend_controller: MotionBlendController | None = None
        self._breathing_motion: BreathingMotion | None = None
        self._head_wobble: HeadWobble | None = None
        self._sdk_client: ReachySDKClient | None = None

        # Memory system
        self._enable_memory = enable_memory
        self._memory_manager: MemoryManager | None = None
        self._user_profile: UserProfile | None = None
        self._last_session: SessionSummary | None = None

        # GitHub MCP integration
        self._enable_github = enable_github
        self._github_toolsets = github_toolsets

        # Voice mode flag - when True, skip speak tool (pipeline handles TTS)
        self._voice_mode: bool = False
        # Queue to capture speak tool text for pipeline TTS when in voice mode
        self._voice_mode_speak_queue: list[str] = []

        # Motion degraded mode - set when robot wake-up fails
        self._motion_degraded: bool = False

    @property
    def idle_controller(self) -> IdleBehaviorController | None:
        """Get the idle behavior controller if enabled."""
        return self._idle_controller

    @property
    def blend_controller(self) -> MotionBlendController | None:
        """Get the motion blend controller if enabled."""
        return self._blend_controller

    @property
    def head_wobble(self) -> HeadWobble | None:
        """Get the head wobble motion source if enabled."""
        return self._head_wobble

    @property
    def is_idle_behavior_active(self) -> bool:
        """Check if idle behavior is currently running (not paused)."""
        if self._idle_controller is None:
            return False
        return self._idle_controller.is_running

    @property
    def is_motion_blend_active(self) -> bool:
        """Check if motion blending is currently running."""
        if self._blend_controller is None:
            return False
        return self._blend_controller.is_running

    @property
    def voice_mode(self) -> bool:
        """Check if voice mode is active (pipeline handles TTS)."""
        return self._voice_mode

    def set_voice_mode(self, enabled: bool) -> None:
        """Enable or disable voice mode.

        When voice mode is enabled, the `speak` tool is skipped because
        the voice pipeline handles TTS directly. This avoids redundant
        TTS calls and reduces latency.

        Args:
            enabled: True to enable voice mode, False to disable.
        """
        self._voice_mode = enabled
        log.info("Voice mode updated", voice_mode=enabled)

    def get_voice_mode_speak_text(self) -> str:
        """Get captured speak tool text and clear the queue.

        In voice mode, speak tool calls are intercepted and their text
        is stored for the pipeline to speak via TTS. This method returns
        all queued text joined with spaces and clears the queue.

        Returns:
            Concatenated speak tool text, or empty string if none.
        """
        if not self._voice_mode_speak_queue:
            return ""
        text = " ".join(self._voice_mode_speak_queue)
        self._voice_mode_speak_queue.clear()
        log.info(
            "voice_mode_speak_text_retrieved",
            text_length=len(text),
            text_preview=text[:50] + "..." if len(text) > 50 else text,
        )
        return text

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

        # GitHub MCP server (if enabled)
        # Prefers native binary over Docker for better Pi compatibility
        if self._enable_github:
            if not get_github_token():
                log.warning(
                    "GitHub MCP requested but no token found. "
                    "Set GITHUB_PERSONAL_ACCESS_TOKEN, GITHUB_TOKEN, or GH_TOKEN."
                )
            elif not is_binary_available() and not is_docker_available():
                log.warning(
                    "GitHub MCP requested but neither binary nor Docker available. "
                    "Install github-mcp-server binary or Docker."
                )
            else:
                try:
                    github_config = build_github_mcp_config(
                        toolsets=self._github_toolsets
                    )
                    servers["github"] = github_config
                    mode = "binary" if is_binary_available() else "docker"
                    log.info(
                        "GitHub MCP server configured",
                        mode=mode,
                        toolsets=self._github_toolsets or ["default"],
                    )
                except Exception as e:
                    log.warning("Failed to configure GitHub MCP", error=str(e))

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

        # Add GitHub tools if enabled and configured
        github_available = (is_binary_available() or is_docker_available()) and get_github_token()
        if self._enable_github and github_available:
            github_tools = get_all_github_tools(toolsets=self._github_toolsets)
            for tool in github_tools:
                allowed.append(f"mcp__github__{tool}")
            log.debug(
                "Added GitHub tools to allowlist",
                count=len(github_tools),
            )

        return allowed

    async def _permission_hook(
        self,
        input_data: HookInput,
        tool_use_id: str | None,  # noqa: ARG002 - SDK hook signature
        context: HookContext,  # noqa: ARG002 - SDK hook signature
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

        # Voice mode: capture speak tool text and skip daemon execution
        # The pipeline will speak this text via TTS instead
        if self._voice_mode and original_tool == "speak":
            # Capture the speak text for pipeline to use
            speak_text = tool_input.get("text", "") if isinstance(tool_input, dict) else ""
            if speak_text:
                self._voice_mode_speak_queue.append(speak_text)
                log.info(
                    "voice_mode_speak_captured",
                    tool_name=tool_name,
                    text_length=len(speak_text),
                    text_preview=speak_text[:50] + "..." if len(speak_text) > 50 else speak_text,
                    queue_size=len(self._voice_mode_speak_queue),
                )
            else:
                log.warning(
                    "voice_mode_speak_empty",
                    tool_name=tool_name,
                    tool_input=tool_input,
                )
            # Deny the daemon speak but Claude sees success
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "Voice mode active - text captured for pipeline TTS",
                }
            }

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
        # Get model from config (defaults defined in config.py)
        model = self.config.agent.model.value if self.config else None

        return ClaudeAgentOptions(
            # Model selection from config
            model=model,
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

            # Initialize daemon client (shared by behaviors)
            self._daemon_client = ReachyDaemonClient(base_url=self.daemon_url)

            # Ensure robot is awake before starting behaviors
            await self._ensure_robot_awake()

            # Initialize motion blending system if enabled
            if self._enable_motion_blend:
                await self._initialize_motion_blend()
            elif self._enable_idle_behavior:
                # Fallback: standalone idle behavior without blend controller
                self._idle_controller = IdleBehaviorController(
                    daemon_client=self._daemon_client,
                    config=self._idle_config,
                )
                await self._idle_controller.start()
                log.info("Idle behavior controller started (standalone mode)")

            # Create and connect SDK client (persistent connection for low latency)
            options = self._build_sdk_options()
            self._client = ClaudeSDKClient(options)
            await self._client.connect()
            log.info("SDK client connected (persistent mode)")

            # Get the model being used for logging
            model = "claude-haiku-4-5-20251001"  # Default
            if self.config and hasattr(self.config, "agent"):
                model = self.config.agent.model.value

            self.state = AgentState.READY
            log.info(
                "Agent loop initialized with Claude Agent SDK",
                model=model,
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
        chroma_path = memory_config.chroma_path if memory_config else "~/.reachy/memory/chroma"
        sqlite_path = memory_config.sqlite_path if memory_config else "~/.reachy/memory/reachy.db"
        embedding_model = memory_config.embedding_model if memory_config else "all-MiniLM-L6-v2"
        retention_days = memory_config.retention_days if memory_config else 90

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

    async def _ensure_robot_awake(self) -> bool:
        """Ensure the robot is awake and ready for motion commands.

        Checks daemon status and calls wake_up if robot is not initialized.
        This is required for motion tools to work properly.

        Returns:
            True if robot is ready, False if wake-up failed (degraded mode).
        """
        if self._daemon_client is None:
            log.warning("No daemon client available - motion in degraded mode")
            self._motion_degraded = True
            return False

        try:
            # Get current robot status
            status = await self._daemon_client.get_status()
            state = status.get("state", "unknown")
            log.info("Robot daemon status", state=state)

            if state == "not_initialized":
                log.info("Robot not initialized, calling wake_up")
                await self._daemon_client.wake_up()
                log.info("Robot wake_up complete")

            return True

        except Exception as e:
            log.error(
                "robot_wake_up_failed",
                error=str(e),
                hint="Check daemon connection and robot power",
            )
            self._motion_degraded = True
            return False

    async def _initialize_motion_blend(self) -> None:
        """Initialize the motion blending system.

        Sets up:
        - ReachySDKClient (direct SDK for low-latency motion via Zenoh)
        - MotionBlendController (orchestrator)
        - BreathingMotion (primary, idle animation)
        - IdleBehaviorController (primary, look-around)
        - HeadWobble (secondary, speech animation)

        The blend controller sends composed poses via SDK (preferred)
        or HTTP daemon (fallback).
        """
        log.info("Initializing motion blending system")

        try:
            # Try to connect SDK client for low-latency motion control
            # SDK uses Zenoh pub/sub (1-5ms) vs HTTP REST (10-50ms)
            try:
                from reachy_agent.mcp_servers.reachy.sdk_client import (
                    ReachySDKClient,
                    SDKClientConfig,
                )

                # Get SDK config from config if available
                sdk_config_dict = {}
                if self.config:
                    sdk_config_dict = getattr(self.config, "sdk", {})
                    if hasattr(sdk_config_dict, "to_dict"):
                        sdk_config_dict = sdk_config_dict.to_dict()
                    elif not isinstance(sdk_config_dict, dict):
                        sdk_config_dict = {}

                sdk_config = SDKClientConfig.from_dict(sdk_config_dict)
                self._sdk_client = ReachySDKClient(sdk_config)

                if await self._sdk_client.connect():
                    log.info(
                        "SDK client connected - using Zenoh for motion control",
                        robot_name=sdk_config.robot_name,
                    )
                else:
                    log.warning(
                        "SDK connection failed, using HTTP fallback",
                        error=self._sdk_client.last_error,
                    )
                    self._sdk_client = None

            except ImportError as e:
                log.warning(
                    "reachy_mini SDK not available, using HTTP for motion",
                    error=str(e),
                )
                self._sdk_client = None

            # Create callback to send poses to daemon via HTTP (fallback)
            async def send_pose_to_daemon(pose: HeadPose) -> None:
                """Send composed pose to Reachy daemon via HTTP.

                Uses set_full_pose to send head and antennas atomically,
                avoiding issues where separate API calls reset each other's targets.

                Note: This is the fallback path; SDK is preferred when available.
                """
                if self._daemon_client is None:
                    return
                try:
                    # Send head pose and antennas in a single API call
                    await self._daemon_client.set_full_pose(
                        roll=pose.roll,
                        pitch=pose.pitch,
                        yaw=pose.yaw,
                        left_antenna=pose.left_antenna,
                        right_antenna=pose.right_antenna,
                    )
                except Exception as e:
                    log.debug("Error sending pose to daemon via HTTP", error=str(e))

            # Create blend controller with SDK client (preferred) and HTTP callback (fallback)
            self._blend_controller = MotionBlendController(
                config=self._blend_config,
                send_pose_callback=send_pose_to_daemon,
                sdk_client=self._sdk_client,
            )

            # Create and register breathing motion (primary)
            self._breathing_motion = BreathingMotion(config=self._breathing_config)
            self._blend_controller.register_source("breathing", self._breathing_motion)

            # Create and register idle behavior (primary)
            if self._enable_idle_behavior:
                # Use blend mode - don't give it daemon_client directly
                self._idle_controller = IdleBehaviorController(
                    daemon_client=None,  # Blend controller handles daemon
                    config=self._idle_config,
                )
                self._blend_controller.register_source("idle", self._idle_controller)

            # Create and register head wobble (secondary)
            self._head_wobble = HeadWobble(config=self._wobble_config)
            self._blend_controller.register_source("wobble", self._head_wobble)

            # Start the blend controller
            await self._blend_controller.start()

            # Set default primary motion based on config
            # Use idle if enabled, otherwise breathing if enabled, otherwise none
            breathing_enabled = (
                self._breathing_config.enabled if self._breathing_config else True
            )

            primary_motion = None
            if self._enable_idle_behavior:
                primary_motion = "idle"
                log_msg = "Using idle behavior as primary motion"
            elif breathing_enabled:
                primary_motion = "breathing"
                log_msg = "Using breathing as primary motion"
            else:
                log_msg = "No primary motion enabled (both idle and breathing disabled)"

            if primary_motion:
                await self._blend_controller.set_primary(primary_motion)
            log.info(log_msg)

            log.info(
                "Motion blending system initialized",
                sources=list(self._blend_controller._sources.keys()),
                active_primary=self._blend_controller.active_primary,
                breathing_enabled=breathing_enabled,
                idle_enabled=self._enable_idle_behavior,
            )

        except Exception as e:
            log.warning("Motion blending failed to initialize", error=str(e))
            # Motion blending is optional - continue without it
            self._blend_controller = None
            self._enable_motion_blend = False

    def set_listening_state(self, listening: bool) -> None:
        """Set whether the robot is listening to the user.

        When listening, antenna motion is frozen to avoid distraction.

        Args:
            listening: Whether the robot is listening.
        """
        if self._blend_controller:
            self._blend_controller.set_listening(listening)

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

        # Set listening state and pause idle behavior during user interaction
        self.set_listening_state(True)
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
            # Exit listening state and resume idle behavior after processing
            self.set_listening_state(False)
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

            # Send query to Claude using persistent connection
            await self._client.query(augmented_input)

            # Process response stream
            async for message in self._client.receive_response():
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

        # Stop motion blend controller (also stops registered sources)
        if self._blend_controller:
            await self._blend_controller.stop()
            log.info("Motion blend controller stopped")

        # Disconnect Reachy SDK client (for motion control)
        if self._sdk_client:
            try:
                await self._sdk_client.disconnect()
                log.info("Reachy SDK client disconnected")
            except Exception as e:
                log.warning("Error disconnecting Reachy SDK client", error=str(e))

        # Stop idle behavior controller (if running standalone)
        if self._idle_controller and not self._blend_controller:
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

        # Disconnect persistent SDK client
        if self._client:
            try:
                await self._client.disconnect()
                log.info("SDK client disconnected")
            except Exception as e:
                log.warning("Error disconnecting SDK client", error=str(e))

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
