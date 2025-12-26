# Permissions Module API

The permissions module implements the 4-tier permission system for tool execution control.

## Permission Tiers

::: reachy_agent.permissions.tiers.PermissionTier

## Permission Evaluator

::: reachy_agent.permissions.tiers.PermissionEvaluator
    options:
      show_source: true
      members:
        - __init__
        - evaluate
        - get_tier

## Permission Decision

::: reachy_agent.permissions.tiers.PermissionDecision

## Permission Hooks

::: reachy_agent.permissions.hooks.PermissionHooks
    options:
      show_source: true
      members:
        - __init__
        - pre_tool_use
        - post_tool_use

## SDK Hook Factory

::: reachy_agent.permissions.hooks.create_sdk_permission_hook
    options:
      show_source: true

## Tool Execution

::: reachy_agent.permissions.hooks.ToolExecution

## Configuration

Permissions are configured in `config/permissions.yaml`:

```yaml
# Default tier for unknown tools
default_tier: 1

# Tool-specific rules
rules:
  # Tier 1: Autonomous
  - pattern: "mcp__reachy__*"
    tier: 1
  - pattern: "mcp__memory__*"
    tier: 1

  # Tier 3: Confirm
  - pattern: "mcp__calendar__create_*"
    tier: 3

  # Tier 4: Forbidden
  - pattern: "mcp__banking__*"
    tier: 4

# Timeouts
confirmation_timeout_seconds: 60
```

## Usage Example

```python
from reachy_agent.permissions.tiers import PermissionEvaluator, PermissionTier

# Create evaluator
evaluator = PermissionEvaluator()

# Evaluate a tool
decision = evaluator.evaluate("move_head")
print(f"Tier: {decision.tier}")
print(f"Allowed: {decision.allowed}")

# Check specific properties
if decision.needs_confirmation:
    # Request user confirmation
    pass
elif decision.should_notify:
    # Log notification
    pass
```

## SDK Integration

```python
from reachy_agent.permissions.hooks import create_sdk_permission_hook
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

# Create SDK-compatible hook
permission_hook = create_sdk_permission_hook()

# Configure in SDK options
options = ClaudeAgentOptions(
    hooks={
        "PreToolUse": [
            HookMatcher(matcher=None, hooks=[permission_hook])
        ]
    },
)
```

## Permission Handlers

### CLI Handler

::: reachy_agent.permissions.handlers.cli_handler.CLIPermissionHandler

### WebSocket Handler

::: reachy_agent.permissions.handlers.web_handler.WebSocketPermissionHandler

## Audit Storage

::: reachy_agent.permissions.storage.sqlite_audit.SQLiteAuditStorage
    options:
      show_source: true
      members:
        - __init__
        - log_execution
        - get_recent_executions
        - close
