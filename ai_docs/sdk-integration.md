# Claude Agent SDK Integration

The Reachy Agent uses the official Claude Agent SDK (`claude-agent-sdk`) for session management, MCP integration, and hook-based permission enforcement.

## Why ClaudeSDKClient?

The SDK provides significant advantages over raw Anthropic API calls:

| Feature | Raw API | SDK |
|---------|---------|-----|
| Session continuity | Manual | Built-in |
| MCP server lifecycle | Manual subprocess | Automatic |
| Tool name prefixing | Manual | `mcp__<server>__<tool>` |
| Permission hooks | External | Native PreToolUse/PostToolUse |
| Streaming | Manual | Built-in |
| Interrupt support | Complex | Built-in |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     ReachyAgentLoop                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ ClaudeSDKClient                                              ││
│  │   │                                                          ││
│  │   ├── ClaudeAgentOptions                                     ││
│  │   │     ├── system_prompt                                    ││
│  │   │     ├── mcp_servers: {reachy, memory}                    ││
│  │   │     ├── hooks: {PreToolUse: [permission_hook]}           ││
│  │   │     ├── allowed_tools: [mcp__reachy__*, ...]             ││
│  │   │     └── max_turns: 10                                    ││
│  │   │                                                          ││
│  │   └── Session state (persisted across queries)               ││
│  └─────────────────────────────────────────────────────────────┘│
│                               │                                  │
│               ┌───────────────┼───────────────┐                  │
│               ▼                               ▼                  │
│  ┌─────────────────────────┐   ┌─────────────────────────┐      │
│  │ MCP: reachy (subprocess)│   │ MCP: memory (subprocess)│      │
│  │ 23 tools                │   │ 4 tools                 │      │
│  └─────────────────────────┘   └─────────────────────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

## MCP Server Configuration

The SDK manages MCP servers as subprocesses with stdio transport:

```python
def _build_mcp_servers(self) -> dict[str, dict[str, Any]]:
    """Build MCP server configuration for SDK."""
    python_executable = sys.executable

    return {
        # Reachy MCP server (robot control)
        "reachy": {
            "type": "stdio",
            "command": python_executable,
            "args": ["-m", "reachy_agent.mcp_servers.reachy", self.daemon_url],
        },
        # Memory MCP server
        "memory": {
            "type": "stdio",
            "command": python_executable,
            "args": ["-m", "reachy_agent.mcp_servers.memory"],
        },
    }
```

**Key points:**
- SDK spawns each server as a subprocess
- Communication via stdio (stdin/stdout)
- Server lifecycle managed automatically
- Tools discovered via MCP `ListTools` protocol

## Tool Naming Convention

SDK prefixes tool names with server context:

```
Original:  move_head
SDK name:  mcp__reachy__move_head

Pattern:   mcp__<server>__<tool>
```

**Example allowed_tools list:**

```python
allowed_tools = [
    "mcp__reachy__move_head",
    "mcp__reachy__play_emotion",
    "mcp__reachy__speak",
    # ... 20 more reachy tools
    "mcp__memory__search_memories",
    "mcp__memory__store_memory",
    "mcp__memory__get_user_profile",
    "mcp__memory__update_user_profile",
]
```

## Permission Hooks

The SDK provides hook injection points. Reachy uses PreToolUse for 4-tier permission enforcement:

### Hook Definition

```python
async def _permission_hook(
    self,
    input_data: HookInput,
    tool_use_id: str | None,
    context: HookContext,
) -> HookJSONOutput:
    """4-tier permission enforcement via SDK PreToolUse hook."""
    tool_name = input_data.get("tool_name", "")

    # Strip SDK prefix: mcp__reachy__move_head → move_head
    original_tool = tool_name
    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__")
        if len(parts) >= 3:
            original_tool = parts[2]

    # Evaluate permission tier
    decision = self._permission_evaluator.evaluate(original_tool)

    # Return based on tier
    if decision.tier == PermissionTier.FORBIDDEN:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Tool {original_tool} is forbidden",
            }
        }

    if decision.needs_confirmation:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": f"Confirm {original_tool}?",
            }
        }

    # AUTONOMOUS or NOTIFY: allow
    return {}
```

### Hook Return Values

| Return | Effect |
|--------|--------|
| `{}` (empty) | Allow execution |
| `{"hookSpecificOutput": {"permissionDecision": "deny"}}` | Block execution |
| `{"hookSpecificOutput": {"permissionDecision": "ask"}}` | Request user confirmation |

### Hook Registration

```python
def _build_sdk_options(self) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=self._system_prompt,
        mcp_servers=self._build_mcp_servers(),
        hooks={
            "PreToolUse": [
                HookMatcher(matcher=None, hooks=[self._permission_hook])
            ]
        },
        allowed_tools=self._build_allowed_tools(),
        max_turns=10,
    )
```

**HookMatcher:**
- `matcher=None`: Apply to all tools
- `matcher="mcp__reachy__*"`: Apply only to reachy tools

## Session Management

The SDK maintains session state automatically:

```python
# Create client (session starts)
options = self._build_sdk_options()
self._client = ClaudeSDKClient(options)

# Each query maintains context
response1 = await self._client.query("Hello!")
response2 = await self._client.query("Remember what I just said?")
# response2 has context from response1
```

### Context Manager Pattern

```python
@asynccontextmanager
async def session(self) -> AsyncGenerator[ReachyAgentLoop, None]:
    """Context manager for agent lifecycle."""
    await self.initialize()
    try:
        yield self
    finally:
        await self.shutdown()

# Usage
async with ReachyAgentLoop(config=config).session() as agent:
    response = await agent.process_input("Hello!")
```

## Response Handling

The SDK returns structured messages:

```python
async def process_input(self, user_input: str) -> AgentResponse:
    """Process user input and return response."""
    result = await self._client.query(user_input)

    # Extract text content
    text_content = ""
    tool_calls = []

    for message in result.messages:
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_content += block.text
                elif isinstance(block, ToolUseBlock):
                    tool_calls.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

    return AgentResponse(text=text_content, tool_calls=tool_calls)
```

## Memory Context Injection

Memory context is injected into the system prompt at initialization:

```python
async def initialize(self) -> None:
    # Load base system prompt
    self._system_prompt = load_system_prompt(config=self.config)

    # Initialize memory and get context
    if self._enable_memory:
        await self._initialize_memory()

        # Build and append memory context
        memory_context = build_memory_context(
            profile=self._user_profile,
            last_session=self._last_session,
        )
        if memory_context:
            self._system_prompt = f"{self._system_prompt}\n\n{memory_context}"
```

## Imports Reference

```python
from claude_agent_sdk import (
    AssistantMessage,      # Response message type
    ClaudeAgentOptions,    # Configuration container
    ClaudeSDKClient,       # Main SDK client
    HookContext,           # Hook execution context
    HookMatcher,           # Hook pattern matcher
    ResultMessage,         # Query result
    TextBlock,             # Text content block
    ToolResultBlock,       # Tool result block
    ToolUseBlock,          # Tool invocation block
)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/reachy_agent/agent/agent.py:L21-31` | SDK imports |
| `src/reachy_agent/agent/agent.py:L171-195` | MCP server config |
| `src/reachy_agent/agent/agent.py:L253-323` | Permission hook |
| `src/reachy_agent/agent/agent.py:L325-346` | SDK options builder |
| `src/reachy_agent/agent/agent.py:L348-398` | Initialization |
| `src/reachy_agent/agent/options.py` | System prompt loader |

## SDK vs Raw API Comparison

### Before (Raw API)

```python
# Manual session management
client = anthropic.AsyncAnthropic()
messages = []

# Manual tool handling
response = await client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=system_prompt,
    messages=messages,
    tools=tools,  # Manual tool definition
)

# Manual tool execution loop
while response.stop_reason == "tool_use":
    # Execute tools manually...
    # Append results to messages...
    response = await client.messages.create(...)
```

### After (SDK)

```python
# SDK handles everything
options = ClaudeAgentOptions(
    system_prompt=system_prompt,
    mcp_servers=mcp_config,  # Auto-discovery
    hooks={"PreToolUse": [...]},
)
client = ClaudeSDKClient(options)

# Simple query, tools handled automatically
result = await client.query("Do something")
```

## Debugging

Enable SDK debug logging:

```bash
REACHY_DEBUG=1 python -m reachy_agent run
```

Check MCP server status:

```python
# In agent loop
log.info("MCP servers configured", servers=list(self._build_mcp_servers().keys()))
```

Test hooks in isolation:

```python
# Create evaluator
evaluator = PermissionEvaluator()

# Test evaluation
decision = evaluator.evaluate("move_head")
print(f"Tier: {decision.tier}, Allowed: {decision.allowed}")
```
