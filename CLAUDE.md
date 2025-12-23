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
| **Agent Loop** | Perceive → Think → Act cycle | `src/agent/loop.py` |
| **Reachy MCP Server** | Exposes robot body as MCP tools | `src/mcp_servers/reachy/` |
| **Perception System** | Wake word, spatial audio, vision | `src/perception/` |
| **Memory System** | ChromaDB for long-term, SQLite structured | `src/memory/` |
| **Permission Hooks** | 4-tier permission enforcement | `src/permissions/` |
| **Expressions** | Antenna/emotion sequences | `src/expressions/` |

### Permission Tiers

1. **Autonomous** - Body control, observation, reading data (no confirmation)
2. **Notify** - Reversible actions like lights, messages (execute + notify)
3. **Confirm** - Irreversible actions like creating events/PRs (require confirmation)
4. **Forbidden** - Security-critical operations (always blocked)

### Attention States

- **Passive** - Wake word detection only, minimal CPU
- **Alert** - Motion detected, periodic Claude check-ins
- **Engaged** - Active listening, full Claude API interaction

## Reachy MCP Tools

The Reachy MCP server exposes these tools to Claude:

| Tool | Description |
|------|-------------|
| `move_head` | Control head position (left/right/up/down/front) |
| `play_emotion` | Trigger expression sequences (happy, sad, curious, etc.) |
| `speak` | Output audio through speaker |
| `dance` | Execute choreographed routines |
| `capture_image` | Get frame from camera |
| `set_antenna_state` | Control antenna positions for expression |
| `get_sensor_data` | Read IMU, audio levels, temperature |
| `look_at_sound` | Turn toward detected sound source |

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
python -m src.main

# With debug logging
REACHY_DEBUG=1 python -m src.main

# Run setup wizard
python scripts/setup_wizard.py
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
