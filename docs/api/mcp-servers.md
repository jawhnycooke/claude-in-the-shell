# MCP Servers API

The MCP servers expose robot control and memory capabilities to Claude via the Model Context Protocol.

## Reachy MCP Server

The Reachy MCP server provides 23 tools for robot control.

### Server Module

::: reachy_agent.mcp_servers.reachy.reachy_mcp
    options:
      show_source: true
      members:
        - create_reachy_mcp_server

### Daemon Client

::: reachy_agent.mcp_servers.reachy.daemon_client.ReachyDaemonClient
    options:
      show_source: true
      members:
        - __init__
        - move_head
        - look_at
        - play_emotion
        - speak
        - nod
        - shake
        - wake_up
        - sleep
        - rest
        - get_status
        - get_pose
        - close

### Mock Daemon

::: reachy_agent.mcp_servers.reachy.daemon_mock
    options:
      show_source: true
      members:
        - create_mock_daemon_app

## Memory MCP Server

The Memory MCP server provides 4 tools for persistent memory and user profiles.

### Server Module

::: reachy_agent.mcp_servers.memory.memory_mcp
    options:
      show_source: true

## Running MCP Servers

### As Subprocess (SDK Integration)

The Claude Agent SDK automatically manages MCP servers as subprocesses:

```python
mcp_servers = {
    "reachy": {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "reachy_agent.mcp_servers.reachy", daemon_url],
    },
    "memory": {
        "type": "stdio",
        "command": sys.executable,
        "args": ["-m", "reachy_agent.mcp_servers.memory"],
    },
}
```

### Standalone (MCP Inspector)

For testing with MCP Inspector:

```bash
# Start mock daemon
python -m reachy_agent.mcp_servers.reachy.daemon_mock

# Run MCP Inspector
npx @modelcontextprotocol/inspector \
  .venv/bin/python -m reachy_agent.mcp_servers.reachy
```

## Tool Reference

For complete tool documentation, see:

- [MCP Tools Quick Reference](../../ai_docs/mcp-tools-quick-ref.md)
- [Memory System](../../ai_docs/memory-system.md)
