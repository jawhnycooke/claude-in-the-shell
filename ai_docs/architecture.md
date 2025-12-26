# Architecture Reference

Consolidated system design reference for the Reachy Agent codebase.

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Agent SDK (ClaudeSDKClient)            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │  Agent Loop  │  │    Hooks     │  │  Permissions │           │
│  │  (Perceive → │  │ (PreToolUse) │  │    Tiers     │           │
│  │   Think →    │  │              │  │              │           │
│  │   Act)       │  │              │  │              │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────────┘
                              │ MCP Protocol (stdio)
            ┌─────────────────┼─────────────────┐
            ▼                                   ▼
┌─────────────────────────────────┐  ┌─────────────────────────────┐
│    Reachy MCP Server (23)       │  │    Memory MCP Server (4)     │
│  ┌─────────────────────────────┐│  │  ┌─────────────────────────┐│
│  │  ListTools → 23 tools       ││  │  │ search_memories         ││
│  │  CallTool  → Protocol exec  ││  │  │ store_memory            ││
│  └─────────────────────────────┘│  │  │ get_user_profile        ││
└─────────────────────────────────┘  │  │ update_user_profile     ││
            │ HTTP :8000              │  └─────────────────────────┘│
            ▼                         └────────────┬────────────────┘
┌─────────────────────────────────┐               │
│     Reachy Daemon (FastAPI)     │     ┌─────────┴─────────┐
│  Motors  │  Camera  │   Audio   │     ▼                   ▼
└─────────────────────────────────┘  ChromaDB            SQLite
                                    (Vector)           (Profiles)
```

### MCP Protocol Architecture (True MCP via SDK)

The agent uses the **official Claude Agent SDK** (`ClaudeSDKClient`) which manages MCP servers as subprocesses:

```
agent.py (ReachyAgent)
    │
    ├── ClaudeSDKClient (manages MCP lifecycle)
    │     │
    │     ├── MCP Server: reachy (subprocess)
    │     │     │ stdio transport
    │     │     ▼
    │     │   reachy_mcp.py → 23 tools
    │     │     │
    │     │     └── ReachyDaemonClient → Daemon HTTP API
    │     │
    │     └── MCP Server: memory (subprocess)
    │           │ stdio transport
    │           ▼
    │         memory_mcp.py → 4 tools
    │           │
    │           ├── ChromaDB (semantic vectors)
    │           └── SQLite (structured profiles)
    │
    └── PreToolUse Hook → 4-tier permission enforcement
```

**SDK manages:**
- **Subprocess lifecycle** - Spawns/terminates MCP servers automatically
- **Tool discovery** - Calls `ListTools` at startup, prefixes with `mcp__<server>__`
- **Hook execution** - Runs PreToolUse hooks before each tool call
- **Session continuity** - Maintains context across multiple queries

**Key Benefits:**
- **Single source of truth** - Tools defined only in MCP servers
- **Dynamic discovery** - Agent discovers tools at runtime via `ListTools`
- **Community publishable** - `reachy-mcp` can be pip-installed as standalone
- **Easy integrations** - Add Home Assistant MCP, GitHub MCP, etc.

## Component Structure

| Component | Responsibility | Location |
|-----------|---------------|----------|
| **Agent Core** | ClaudeSDKClient-based Perceive → Think → Act cycle | `src/reachy_agent/agent/agent.py` |
| **Reachy MCP Server** | Robot body control tools (23 tools) | `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py` |
| **Memory MCP Server** | Semantic memory + user profiles (4 tools) | `src/reachy_agent/mcp_servers/memory/memory_mcp.py` |
| **MCP Entry Point** | Standalone subprocess launcher | `src/reachy_agent/mcp_servers/reachy/__main__.py` |
| **Permission Hooks** | 4-tier permission enforcement (SDK PreToolUse) | `src/reachy_agent/permissions/hooks.py` |
| **Memory Manager** | ChromaDB + SQLite storage backends | `src/reachy_agent/memory/` |
| **Daemon Client** | HTTP client for hardware API | `src/reachy_agent/mcp_servers/reachy/daemon_client.py` |
| **Simulation Client** | High-level robot client | `src/reachy_agent/simulation/reachy_client.py` |

## Data Flow

```
User speaks
    │
    ▼
┌─────────────────┐
│  Wake Word      │ (OpenWakeWord - local)
│  Detection      │
└────────┬────────┘
         │ "Hey Reachy"
         ▼
┌─────────────────┐
│  Audio Pipeline │ (PyAudio → Whisper API or local)
│  STT            │
└────────┬────────┘
         │ Transcribed text
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Memory System  │────▶│  Context        │
│  (ChromaDB)     │     │  Building       │
└─────────────────┘     └────────┬────────┘
                                 │ Enriched prompt
                                 ▼
                        ┌─────────────────┐
                        │  Claude Agent   │
                        │  SDK Loop       │
                        └────────┬────────┘
                                 │ Tool calls
                                 ▼
                        ┌─────────────────┐
                        │  Permission     │
                        │  Hooks          │
                        └────────┬────────┘
                                 │ Allowed tools
                                 ▼
                        ┌─────────────────┐
                        │  Reachy MCP     │
                        │  Server         │
                        └────────┬────────┘
                                 │ HTTP
                                 ▼
                        ┌─────────────────┐
                        │  Reachy Daemon  │
                        │  (Hardware)     │
                        └─────────────────┘
```

## Permission Tiers

| Tier | Name | Behavior | Examples |
|------|------|----------|----------|
| 1 | **Autonomous** | Execute immediately | Body control, sensors, reading data |
| 2 | **Notify** | Execute + notify user | Smart home control, notifications |
| 3 | **Confirm** | Ask before executing | Create calendar events, GitHub PRs |
| 4 | **Forbidden** | Never execute | Disarm security, banking, email send |

### Permission Flow

```
Tool Request → Permission Evaluator → Decision
                    │
        ┌───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼
    Tier 1      Tier 2      Tier 3      Tier 4
   Execute    Execute +   Confirm →   Block +
              Notify      Execute     Log
```

## Attention States

| State | Trigger | CPU Usage | Claude API |
|-------|---------|-----------|------------|
| **Passive** | Default | Minimal | None |
| **Alert** | Motion detected | Low | Periodic check-ins |
| **Engaged** | Wake word heard | Full | Active conversation |

State transitions:
- Passive → Alert: Motion detected
- Passive → Engaged: Wake word heard
- Alert → Passive: 30s timeout
- Alert → Engaged: Wake word or face detected
- Engaged → Alert: 60s silence

## Key Source Files

### Agent Core

| File | Purpose |
|------|---------|
| `src/reachy_agent/agent/agent.py` | Main agent loop + MCP client implementation |
| `src/reachy_agent/agent/options.py` | Agent SDK configuration |

### MCP Servers

| File | Purpose |
|------|---------|
| `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py` | Reachy tool definitions (23 tools) |
| `src/reachy_agent/mcp_servers/reachy/__main__.py` | Reachy subprocess entry point |
| `src/reachy_agent/mcp_servers/reachy/daemon_client.py` | HTTP client for daemon API |
| `src/reachy_agent/mcp_servers/reachy/daemon_mock.py` | Mock server for testing |
| `src/reachy_agent/mcp_servers/memory/memory_mcp.py` | Memory tool definitions (4 tools) |
| `src/reachy_agent/mcp_servers/memory/__main__.py` | Memory subprocess entry point |

### Memory System

| File | Purpose |
|------|---------|
| `src/reachy_agent/memory/manager.py` | High-level MemoryManager facade |
| `src/reachy_agent/memory/storage/vector_store.py` | ChromaDB vector storage |
| `src/reachy_agent/memory/storage/sqlite_store.py` | SQLite profile/session storage |
| `src/reachy_agent/memory/types.py` | Memory, UserProfile, SessionSummary types |

### Entry Points

| Command | File | Purpose |
|---------|------|---------|
| `python -m reachy_agent run` | `src/reachy_agent/main.py` | Run full agent |
| `python -m reachy_agent web` | `src/reachy_agent/web/app.py` | Web dashboard |
| `python -m reachy_agent.mcp_servers.reachy` | `__main__.py` | Standalone MCP server |

### Permissions

| File | Purpose |
|------|---------|
| `src/reachy_agent/permissions/tiers.py` | Tier definitions and evaluation |
| `src/reachy_agent/permissions/hooks.py` | PreToolUse/PostToolUse hooks |
| `config/permissions.yaml` | Permission rules configuration |

### Utilities

| File | Purpose |
|------|---------|
| `src/reachy_agent/utils/logging.py` | Structured logging with structlog |
| `src/reachy_agent/utils/config.py` | Configuration management |

## Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| LLM | Claude API | Reasoning, tool selection |
| Agent SDK | `claude-agent-sdk` | ClaudeSDKClient, hooks, MCP integration |
| Protocol | MCP (stdio) | Tool communication via subprocess |
| HTTP | `httpx` | Async HTTP client |
| Validation | `pydantic` | Type-safe config |
| Logging | `structlog` | Structured logs |
| Vector DB | `chromadb` | Semantic memory embeddings |
| Embeddings | `sentence-transformers` | Text to vectors |
| Structured DB | SQLite | User profiles, sessions |
| CLI | `rich` + `typer` | Terminal UI |

## Hardware Reference

**Reachy Mini Wireless** (Raspberry Pi 4):
- Head: 6 DOF (degrees of freedom)
- Body: 360° rotation on base
- 2 animated antennas for expression
- Wide-angle camera
- 4-microphone array + 5W speaker
- Accelerometer/IMU
- WiFi connectivity

## Deployment Modes

### Development (Simulation)

```
┌─────────────────────────────────────────┐
│         Development Machine              │
│  ┌─────────────┐   ┌─────────────────┐  │
│  │ Reachy      │   │ reachy-mini     │  │
│  │ Agent       │──▶│ daemon --sim    │  │
│  └─────────────┘   └────────┬────────┘  │
│                             │           │
│                    ┌────────▼────────┐  │
│                    │  MuJoCo Physics │  │
│                    └─────────────────┘  │
└─────────────────────────────────────────┘
```

### Production (Hardware)

```
┌─────────────────────────────────────────┐
│         Raspberry Pi 4                   │
│  ┌─────────────┐   ┌─────────────────┐  │
│  │ reachy-     │   │ reachy-daemon   │  │
│  │ agent.svc   │──▶│ .service        │  │
│  └─────────────┘   └────────┬────────┘  │
└───────────────────────────────┼─────────┘
                        ┌───────▼───────┐
                        │ Reachy Mini   │
                        │ Hardware      │
                        └───────────────┘
```

## MCP Tools by Category (27 total)

### Reachy MCP Server (23 tools)

| Category | Tools | Mock Support |
|----------|-------|--------------|
| **Movement** (5) | move_head, look_at, look_at_world, look_at_pixel, rotate | 3/5 (IK tools need real daemon) |
| **Expression** (6) | play_emotion, play_recorded_move, set_antenna_state, nod, shake, rest | 5/6 (recorded moves need real daemon) |
| **Audio** (2) | speak, listen | 2/2 |
| **Perception** (3) | capture_image, get_sensor_data, look_at_sound | 3/3 |
| **Lifecycle** (3) | wake_up, sleep, rest | 3/3 |
| **Status** (2) | get_status, get_pose | 2/2 |
| **Control** (2) | set_motor_mode, cancel_action | 1/2 (motor mode needs real daemon) |

### Memory MCP Server (4 tools)

| Category | Tools | Storage |
|----------|-------|---------|
| **Semantic** (2) | search_memories, store_memory | ChromaDB (vectors) |
| **Profile** (2) | get_user_profile, update_user_profile | SQLite (structured) |

### Native SDK Emotions

The agent prefers native SDK emotions from `pollen-robotics/reachy-mini-emotions-library` when available, falling back to custom compositions:

| Emotion | Native SDK Move | Has Audio |
|---------|-----------------|-----------|
| curious | curious1 | ✓ |
| happy/joy | cheerful1 | ✓ |
| sad | downcast1 | ✓ |
| surprised | amazed1 | ✓ |
| excited | enthusiastic1 | ✓ |
| scared | fear1 | ✓ |

### Native SDK Dances

| Dance Routine | Native SDK Move |
|---------------|-----------------|
| celebrate | dance1 |
| party | dance2 |
| groove | dance3 |

## Security Model

| Trust Level | Components |
|-------------|------------|
| High | Agent Core, Reachy Daemon |
| Medium | MCP Servers, Claude API |
| Low | External Services, User Input |

**Principles:**
1. Least Privilege: Each MCP server has minimal permissions
2. Defense in Depth: Permission tiers + validation + audit
3. Fail Secure: Unknown tools default to highest restriction
4. Privacy by Design: Antenna states indicate listening status
