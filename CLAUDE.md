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
| **Agent Loop** | Perceive → Think → Act cycle + MCP client | `src/reachy_agent/agent/agent.py` |
| **Reachy MCP Server** | Exposes robot body as MCP tools (23 tools) | `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py` |
| **Daemon Client** | HTTP client for Reachy daemon API | `src/reachy_agent/mcp_servers/reachy/daemon_client.py` |
| **Mock Daemon** | Testing without hardware | `src/reachy_agent/mcp_servers/reachy/daemon_mock.py` |
| **Permission Hooks** | 4-tier permission enforcement | `src/reachy_agent/permissions/` |
| **Simulation Client** | High-level robot control | `src/reachy_agent/simulation/reachy_client.py` |

### Permission Tiers

1. **Autonomous** - Body control, observation, reading data (no confirmation)
2. **Notify** - Reversible actions like lights, messages (execute + notify)
3. **Confirm** - Irreversible actions like creating events/PRs (require confirmation)
4. **Forbidden** - Security-critical operations (always blocked)

### Attention States

- **Passive** - Wake word detection only, minimal CPU
- **Alert** - Motion detected, periodic Claude check-ins
- **Engaged** - Active listening, full Claude API interaction

## Reachy MCP Tools (23 tools)

The Reachy MCP server exposes these tools organized by category:

| Category | Tools |
|----------|-------|
| **Movement** | `move_head`, `look_at`, `look_at_world`, `look_at_pixel`, `rotate` |
| **Expression** | `play_emotion`, `play_recorded_move`, `set_antenna_state`, `nod`, `shake`, `rest` |
| **Audio** | `speak`, `listen` |
| **Perception** | `capture_image`, `get_sensor_data`, `look_at_sound` |
| **Lifecycle** | `wake_up`, `sleep` |
| **Status** | `get_status`, `get_pose` |
| **Control** | `set_motor_mode`, `cancel_action` |

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

- `claude-agent-sdk` - Agent loop and MCP integration
- `mcp` - Model Context Protocol Python SDK
- `chromadb` - Vector storage for memory
- `porcupine` / `openwakeword` - Wake word detection
- `pyroomacoustics` - Spatial audio (sound localization)
- `piper-tts` - Local TTS fallback
- `opencv-python` - Vision processing

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

```bash
# Start the agent
python -m reachy_agent run

# With debug logging
REACHY_DEBUG=1 python -m reachy_agent run

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
