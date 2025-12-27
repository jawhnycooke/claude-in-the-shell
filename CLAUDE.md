# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reachy Agent transforms the Reachy Mini desktop robot into an autonomous AI agent by running the Claude Agent SDK on its Raspberry Pi 4. The robot uses MCP (Model Context Protocol) servers to interact with both physical hardware (motors, camera, microphones) and external services (Home Assistant, GitHub, Slack, etc.).

## Development Environment

```bash
# Environment setup (uv preferred)
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# Quality checks
uvx black . --line-length 88
uvx isort . --profile black
uvx mypy . --strict
uvx ruff check .
uvx pytest -v --cov=. --cov-report=html
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Agent SDK                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Agent Loop  │  │    Hooks     │  │  Permissions │           │
│  │  (Perceive → │  │ (PreToolUse) │  │    Tiers     │           │
│  │   Think →    │  │              │  │              │           │
│  │   Act)       │  │              │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │ MCP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Reachy Agent Core                             │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │ Perception │ │   Memory   │ │Personality │ │   Privacy    │  │
│  │ (audio,    │ │ (ChromaDB) │ │  (mood,    │ │  (audit,     │  │
│  │  vision)   │ │            │ │   energy)  │ │  indicators) │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP :8000
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Reachy Daemon (FastAPI) - Pollen Robotics          │
│  Motors/Servos  │  Camera/IMU  │  Audio (4-mic array, speaker)  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **Agent Loop** | ClaudeSDKClient-based Perceive → Think → Act cycle | `src/reachy_agent/agent/agent.py` |
| **Reachy MCP Server** | Exposes robot body as MCP tools (23 tools) | `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py` |
| **Memory MCP Server** | Semantic memory + user profiles (4 tools) | `src/reachy_agent/mcp_servers/memory/memory_mcp.py` |
| **GitHub MCP** | Optional GitHub integration (50+ tools) | `src/reachy_agent/mcp_servers/integrations/github_mcp.py` |
| **Daemon Client** | HTTP client for Reachy daemon API | `src/reachy_agent/mcp_servers/reachy/daemon_client.py` |
| **Mock Daemon** | Testing without hardware | `src/reachy_agent/mcp_servers/reachy/daemon_mock.py` |
| **Permission Hooks** | 4-tier permission enforcement (SDK hooks) | `src/reachy_agent/permissions/` |
| **Memory Manager** | ChromaDB + SQLite storage backends | `src/reachy_agent/memory/` |
| **Motion Blend Controller** | Orchestrates motion sources at 100Hz | `src/reachy_agent/behaviors/blend_controller.py` |
| **Breathing Motion** | Idle breathing animation (Z-axis + antennas) | `src/reachy_agent/behaviors/breathing.py` |
| **Head Wobble** | Audio-reactive speech animation | `src/reachy_agent/behaviors/wobble.py` |
| **Idle Behavior** | Look-around behavior when idle | `src/reachy_agent/behaviors/idle.py` |

### Permission Tiers

1. **Autonomous** - Body control, observation, reading data (no confirmation)
2. **Notify** - Reversible actions like lights, messages (execute + notify)
3. **Confirm** - Irreversible actions like creating events/PRs (require confirmation)
4. **Forbidden** - Security-critical operations (always blocked)

### Attention States

- **Passive** - Wake word detection only, minimal CPU
- **Alert** - Motion detected, periodic Claude check-ins
- **Engaged** - Active listening, full Claude API interaction

## MCP Tools (27 tools total)

### Reachy MCP Server (23 tools)

The Reachy MCP server exposes robot control tools organized by category:

| Category | Tools |
|----------|-------|
| **Movement** | `move_head`, `look_at`, `look_at_world`, `look_at_pixel`, `rotate` |
| **Expression** | `play_emotion`, `play_recorded_move`, `set_antenna_state`, `nod`, `shake`, `dance` |
| **Audio** | `speak`, `listen` |
| **Perception** | `capture_image`, `get_sensor_data`, `look_at_sound` |
| **Lifecycle** | `wake_up`, `sleep`, `rest` |
| **Status** | `get_status`, `get_pose` |
| **Control** | `set_motor_mode`, `cancel_action` |

### Memory MCP Server (4 tools)

The Memory MCP server provides semantic memory and user profile management:

| Tool | Description |
|------|-------------|
| `search_memories` | Semantic search over stored memories |
| `store_memory` | Save a new memory with type classification |
| `get_user_profile` | Retrieve user preferences and info |
| `update_user_profile` | Update user preferences |

### GitHub MCP Integration (Optional, 50+ tools)

External integration with the [official GitHub MCP server](https://github.com/github/github-mcp-server):

```python
# Enable in ReachyAgentLoop
agent = ReachyAgentLoop(
    enable_github=True,  # Requires GITHUB_TOKEN env var
    github_toolsets=["repos", "issues", "pull_requests", "actions"],
)
```

Binary preferred over Docker for Pi compatibility. Install at `~/.reachy/bin/github-mcp-server`.

### Native SDK Emotions

The `play_emotion` tool prefers native SDK emotions from `pollen-robotics/reachy-mini-emotions-library` (HuggingFace) with synchronized audio, falling back to custom compositions.

See `ai_docs/mcp-tools-quick-ref.md` for complete parameter details.

## Hardware Reference

**Reachy Mini Wireless** (Raspberry Pi 4):
- Head: 6 DOF, body: 360° rotation
- 2 animated antennas for expression
- Wide-angle camera
- 4-microphone array + 5W speaker
- Accelerometer/IMU
- WiFi connectivity

## Key Dependencies

- `claude-agent-sdk` - Official Claude Agent SDK (ClaudeSDKClient, hooks, MCP integration)
- `chromadb` - Vector storage for semantic memory
- `sentence-transformers` - Text embeddings for memory search
- `httpx` - Async HTTP client for daemon communication
- `pydantic` - Configuration and data validation
- `structlog` - Structured logging
- `rich` - Terminal UI for CLI
- (optional) `porcupine` / `openwakeword` - Wake word detection
- (optional) `piper-tts` - Local TTS fallback

## AI Agent Reference (ai_docs/)

The `ai_docs/` folder contains curated reference materials for AI agents working on this codebase:

| Document | Purpose |
|----------|---------|
| [code-standards.md](ai_docs/code-standards.md) | Linting, logging, type checking requirements |
| [architecture.md](ai_docs/architecture.md) | System design and component relationships |
| [mcp-tools-quick-ref.md](ai_docs/mcp-tools-quick-ref.md) | MCP tools with parameters and permissions |
| [agent-behavior.md](ai_docs/agent-behavior.md) | Personality guidelines and expression patterns |
| [dev-commands.md](ai_docs/dev-commands.md) | Common development commands cheat sheet |

**When to use**: Consult these docs before writing code, implementing tools, or working on agent behavior.

## Planning Documents (docs/planning/)

Historical planning and requirements documents are archived in `docs/planning/`:

| Document | Purpose |
|----------|---------|
| [PRD.md](docs/planning/PRD.md) | Product Requirements Document |
| [TECH_REQ.md](docs/planning/TECH_REQ.md) | Technical Requirements Document |
| [EPCC_PLAN.md](docs/planning/EPCC_PLAN.md) | Implementation roadmap (EPCC workflow) |
| [EPCC_CODE.md](docs/planning/EPCC_CODE.md) | Phase 1 implementation log |
| [REACHY_CLAUDE_AGENT_SDK.md](docs/planning/REACHY_CLAUDE_AGENT_SDK.md) | Research and feasibility analysis |

**When to use**: Reference these for understanding original requirements and design decisions.

## Configuration Files

| File | Purpose |
|------|---------|
| `config/default.yaml` | Default configuration |
| `config/permissions.yaml` | Permission tier rules |
| `config/expressions.yaml` | Antenna/emotion definitions |
| `.env` | API keys and secrets (never commit) |

## Testing

```bash
# Run all tests
uvx pytest -v

# Run specific test file
uvx pytest tests/test_mcp_server.py -v

# With coverage
uvx pytest --cov=src --cov-report=html
```

## Running the Agent

### CLI Commands

```bash
# Interactive agent (production daemon at :8000)
python -m reachy_agent run

# Interactive agent with simulation daemon
python -m reachy_agent run --daemon-url http://localhost:8765

# Run with mock daemon (no external daemon needed)
python -m reachy_agent run --mock

# Rich terminal REPL with slash commands
python -m reachy_agent repl

# Web dashboard (browser interface at :8080)
python -m reachy_agent web

# Health check
python -m reachy_agent check

# Version info
python -m reachy_agent version

# With debug logging
REACHY_DEBUG=1 python -m reachy_agent run
```

### MCP Server Standalone

```bash
# Start mock daemon for testing
python -m reachy_agent.mcp_servers.reachy.daemon_mock

# Run MCP server standalone (for MCP Inspector testing)
python -m reachy_agent.mcp_servers.reachy
```

## MCP Testing

```bash
# Start mock daemon (Terminal 1)
python -m reachy_agent.mcp_servers.reachy.daemon_mock

# Run MCP Inspector (Terminal 2)
npx @modelcontextprotocol/inspector \
  .venv/bin/python -m reachy_agent.mcp_servers.reachy
```

## External References

- [Reachy Mini SDK](https://github.com/pollen-robotics/reachy_mini)
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Specification](https://spec.modelcontextprotocol.io/)

## ARM64/Raspberry Pi Notes

Claude Code has ARM64 compatibility. If you hit architecture errors:
```bash
# Use native installer (recommended)
curl -fsSL https://claude.ai/install.sh | bash

# Or pin to known-good version
npm install -g @anthropic-ai/claude-code@0.2.114
```

Monitor thermals on Pi: `vcgencmd measure_temp`
