# Agent Module API

The agent module provides the core agent loop implementation using the Claude Agent SDK.

## ReachyAgentLoop

::: reachy_agent.agent.agent.ReachyAgentLoop
    options:
      show_source: true
      members:
        - __init__
        - initialize
        - shutdown
        - process_input
        - session

## AgentState

::: reachy_agent.agent.agent.AgentState

## AgentContext

::: reachy_agent.agent.agent.AgentContext

## AgentResponse

::: reachy_agent.agent.agent.AgentResponse

## Usage Example

```python
from reachy_agent.agent.agent import ReachyAgentLoop

# Using context manager (recommended)
async with ReachyAgentLoop(
    daemon_url="http://localhost:8765",
    enable_memory=True,
).session() as agent:
    response = await agent.process_input("Hello, Reachy!")
    print(response.text)

# Manual lifecycle
agent = ReachyAgentLoop(daemon_url="http://localhost:8765")
await agent.initialize()
try:
    response = await agent.process_input("Wave at me!")
    if response.success:
        print(response.text)
finally:
    await agent.shutdown()
```

## Configuration

The agent can be configured via:

- Constructor parameters
- `config/default.yaml`
- Environment variables

See [Options Module](#options-module) for configuration details.

## Options Module

::: reachy_agent.agent.options
    options:
      show_source: true
      members:
        - load_system_prompt
