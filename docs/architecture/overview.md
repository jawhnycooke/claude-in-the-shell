# Reachy Agent Architecture

This document describes the architecture of Reachy Agent, an embodied AI system that transforms the Reachy Mini desktop robot into an autonomous Claude-powered assistant.

## System Overview

```mermaid
flowchart TB
    subgraph Cloud["Cloud Services"]
        CLAUDE[("Claude API<br/>api.anthropic.com")]
        HA["Home Assistant"]
        GH["GitHub API"]
        CAL["Google Calendar"]
    end

    subgraph Agent["Reachy Agent (Raspberry Pi 4)"]
        SDK["Claude Agent SDK"]

        subgraph Core["Agent Core"]
            LOOP["Agent Loop<br/>(Perceive→Think→Act)"]
            PERM["Permission System<br/>(4 Tiers)"]
            MEM["Memory System<br/>(ChromaDB + SQLite)"]
        end

        subgraph MCP["MCP Servers"]
            REACHY_MCP["Reachy MCP<br/>(23 tools)"]
            HA_MCP["Home Assistant MCP"]
            GH_MCP["GitHub MCP"]
        end

        subgraph Perception["Perception Layer"]
            WAKE["Wake Word<br/>(OpenWakeWord)"]
            AUDIO["Spatial Audio<br/>(4-mic array)"]
            VISION["Vision<br/>(OpenCV)"]
        end
    end

    subgraph Hardware["Reachy Mini Hardware"]
        DAEMON["Reachy Daemon<br/>(FastAPI :8000)"]

        subgraph Physical["Physical Components"]
            HEAD["Head<br/>(6 DOF)"]
            BODY["Body<br/>(360° rotation)"]
            ANT["Antennas<br/>(expression)"]
            CAM["Camera"]
            MIC["4-Mic Array"]
            SPK["Speaker"]
        end
    end

    CLAUDE <--> SDK
    SDK --> LOOP
    LOOP <--> PERM
    LOOP <--> MEM
    LOOP --> MCP

    REACHY_MCP --> DAEMON
    HA_MCP --> HA
    GH_MCP --> GH

    DAEMON --> Physical
    Perception --> LOOP

    CAM --> VISION
    MIC --> AUDIO
    MIC --> WAKE

    style CLAUDE fill:#f9a825
    style SDK fill:#7c4dff
    style REACHY_MCP fill:#00bcd4
    style DAEMON fill:#4caf50
```

## Component Layers

### Layer 1: Cloud Intelligence

The system uses Claude API for natural language understanding and reasoning:

```mermaid
sequenceDiagram
    participant U as User
    participant W as Wake Word
    participant A as Agent Loop
    participant C as Claude API
    participant T as MCP Tools

    U->>W: "Hey Reachy"
    W->>A: Wake signal
    A->>A: Record audio
    U->>A: "Turn left and nod"
    A->>C: User request + context
    C->>A: Tool calls: [move_head, nod]
    A->>T: Execute move_head("left")
    T-->>A: Success
    A->>T: Execute nod()
    T-->>A: Success
    A->>C: Tool results
    C->>A: "I've turned left and nodded!"
    A->>U: Speak response
```

### Layer 2: Agent Core

The agent core manages the perception-action loop:

```mermaid
stateDiagram-v2
    [*] --> Passive

    Passive --> Alert: Motion detected
    Passive --> Engaged: Wake word heard

    Alert --> Passive: 30s timeout
    Alert --> Engaged: Wake word heard
    Alert --> Engaged: Face detected

    Engaged --> Alert: 60s silence
    Engaged --> Engaged: User speaking

    note right of Passive
        - Wake word detection only
        - Minimal CPU usage
        - Antennas down
    end note

    note right of Alert
        - Motion/face tracking
        - Periodic Claude check-ins
        - Antennas mid-position
    end note

    note right of Engaged
        - Full agent loop active
        - Continuous listening
        - Antennas up (privacy indicator)
    end note
```

### Layer 3: MCP Protocol (True MCP Architecture)

MCP (Model Context Protocol) provides a standardized interface between Claude and tools.
**Key change:** The agent now uses **true MCP protocol** with subprocess communication:

```mermaid
flowchart LR
    subgraph Agent["Agent Core (agent.py)"]
        SDK["ReachyAgentLoop"]
        CLIENT["MCP ClientSession<br/>(stdio transport)"]
    end

    subgraph MCP["MCP Layer (subprocess)"]
        direction TB
        PROTO["MCP Protocol<br/>(JSON-RPC over stdio)"]

        subgraph Servers["MCP Servers"]
            R["reachy-mcp<br/>(23 tools)"]
            H["homeassistant-mcp"]
            G["github-mcp"]
        end
    end

    subgraph Backends["Backend Services"]
        RD["Reachy Daemon<br/>:8000"]
        HA["Home Assistant"]
        GH["GitHub API"]
    end

    SDK --> CLIENT
    CLIENT <-->|"ListTools<br/>CallTool"| PROTO
    PROTO <--> Servers
    R -->|HTTP| RD
    H -->|REST API| HA
    G -->|REST API| GH

    style PROTO fill:#e1bee7
    style CLIENT fill:#c8e6c9
```

**MCP Protocol Flow:**
1. Agent spawns MCP server as subprocess (`python -m reachy_agent.mcp_servers.reachy`)
2. Agent discovers tools dynamically via `ListTools` (23 tools)
3. Agent executes tools via `CallTool` over stdio transport
4. MCP server calls Daemon HTTP API

### Layer 4: Permission System

Actions are classified into 4 permission tiers:

```mermaid
flowchart TD
    REQ["Tool Request"] --> EVAL["Permission Evaluator"]

    EVAL --> T1{"Tier 1?<br/>Autonomous"}
    EVAL --> T2{"Tier 2?<br/>Notify"}
    EVAL --> T3{"Tier 3?<br/>Confirm"}
    EVAL --> T4{"Tier 4?<br/>Forbidden"}

    T1 -->|Yes| EXEC["Execute Immediately"]
    T2 -->|Yes| EXECN["Execute + Notify User"]
    T3 -->|Yes| ASK["Ask for Confirmation"]
    T4 -->|Yes| BLOCK["Block + Log"]

    ASK -->|Approved| EXEC
    ASK -->|Denied| BLOCK

    EXEC --> LOG["Audit Log"]
    EXECN --> LOG
    BLOCK --> LOG

    style T1 fill:#c8e6c9
    style T2 fill:#fff9c4
    style T3 fill:#ffe0b2
    style T4 fill:#ffcdd2
```

**Permission Tier Examples:**

| Tier | Category | Tools | Rationale |
|------|----------|-------|-----------|
| 1 | Autonomous | `move_head`, `play_emotion`, `capture_image` | Body control is safe, reversible |
| 2 | Notify | `homeassistant.*`, `send_notification` | User should know about actions |
| 3 | Confirm | `github.create_pr`, `calendar.create_event` | Irreversible external changes |
| 4 | Forbidden | `execute_code`, `delete_*`, `admin_*` | Security-critical operations |

### Layer 5: Hardware Interface

The Reachy Daemon provides a REST API to control hardware:

```mermaid
flowchart TB
    subgraph Agent["Reachy Agent"]
        CLIENT["ReachyMiniClient<br/>(HTTP Client)"]
    end

    subgraph Daemon["Reachy Daemon (FastAPI)"]
        API["REST API<br/>:8000"]

        subgraph Backends["Backend Selector"]
            HW["RobotBackend<br/>(Real Hardware)"]
            SIM["MujocoBackend<br/>(Simulation)"]
        end

        subgraph Controllers["Motor Controllers"]
            HEAD_C["Head Controller"]
            BODY_C["Body Controller"]
            ANT_C["Antenna Controller"]
        end
    end

    subgraph Hardware["Physical/Simulated"]
        MOTORS["Dynamixel Servos"]
        MUJOCO["MuJoCo Physics"]
    end

    CLIENT -->|"POST /api/move/goto"| API
    CLIENT -->|"POST /api/move/play/wake_up"| API
    CLIENT -->|"GET /api/daemon/status"| API

    API --> Backends
    HW --> Controllers
    SIM --> Controllers

    HEAD_C --> MOTORS
    HEAD_C --> MUJOCO
    BODY_C --> MOTORS
    BODY_C --> MUJOCO
    ANT_C --> MOTORS
    ANT_C --> MUJOCO

    style SIM fill:#e3f2fd
    style HW fill:#e8f5e9
```

## Data Flow

### Request Lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant P as Perception
    participant L as Agent Loop
    participant M as Memory
    participant E as Permission Eval
    participant T as MCP Tool
    participant D as Reachy Daemon

    U->>P: Voice input
    P->>L: Transcribed text
    L->>M: Fetch context
    M-->>L: Relevant memories
    L->>L: Build prompt
    L->>L: Call Claude API

    loop For each tool call
        L->>E: Check permission
        E-->>L: Decision (tier)

        alt Autonomous/Notify
            L->>T: Execute tool
            T->>D: HTTP request
            D-->>T: Result
            T-->>L: Tool response
        else Confirm
            L->>U: Request confirmation
            U-->>L: Approve/Deny
        else Forbidden
            L->>L: Log blocked attempt
        end
    end

    L->>M: Store interaction
    L->>U: Speak response
```

## Deployment Architecture

### Development (Simulation)

```mermaid
flowchart LR
    subgraph Dev["Development Machine"]
        AGENT["Reachy Agent"]
        DAEMON["reachy-mini-daemon<br/>--sim --headless"]
        MUJOCO["MuJoCo Physics"]
    end

    subgraph Cloud
        CLAUDE["Claude API"]
    end

    AGENT <-->|MCP| DAEMON
    DAEMON --> MUJOCO
    AGENT <-->|HTTPS| CLAUDE

    style MUJOCO fill:#e3f2fd
```

### Production (Hardware)

```mermaid
flowchart LR
    subgraph Pi["Raspberry Pi 4"]
        AGENT["reachy-agent.service"]
        DAEMON["reachy-daemon.service"]
    end

    subgraph Robot["Reachy Mini"]
        HW["Hardware"]
    end

    subgraph Cloud
        CLAUDE["Claude API"]
        HA["Home Assistant"]
    end

    AGENT <-->|MCP| DAEMON
    DAEMON --> HW
    AGENT <-->|HTTPS| CLAUDE
    AGENT <-->|REST| HA

    style HW fill:#e8f5e9
```

## Key Design Decisions

| Decision | Choice | Alternatives Considered | Rationale |
|----------|--------|------------------------|-----------|
| Process Model | Single asyncio | Multiple systemd services | Simpler debugging, lower memory |
| Wake Word | OpenWakeWord | Porcupine, Snowboy | Open source, no license costs |
| Memory Store | ChromaDB + SQLite | PostgreSQL, Redis | Lightweight, embedded, no server |
| Config Format | YAML | JSON, TOML | Human-readable, supports comments |
| MCP Transport | stdio subprocess | HTTP, direct calls | True MCP protocol, dynamic discovery |
| Tool Discovery | ListTools | Hardcoded schemas | Single source of truth, extensible |

## Security Model

```mermaid
flowchart TB
    subgraph Trust["Trust Boundaries"]
        subgraph High["High Trust"]
            AGENT["Agent Core"]
            DAEMON["Reachy Daemon"]
        end

        subgraph Medium["Medium Trust"]
            MCP["MCP Servers"]
            CLOUD["Claude API"]
        end

        subgraph Low["Low Trust"]
            EXT["External Services"]
            USER["User Input"]
        end
    end

    USER -->|"Sanitized"| AGENT
    AGENT -->|"Validated"| MCP
    MCP -->|"HTTPS"| EXT
    AGENT <-->|"TLS"| CLOUD

    style High fill:#c8e6c9
    style Medium fill:#fff9c4
    style Low fill:#ffcdd2
```

**Security Principles:**
1. **Least Privilege**: Each MCP server has minimal required permissions
2. **Defense in Depth**: Permission tiers + API validation + audit logging
3. **Fail Secure**: Unknown tools default to highest restriction tier
4. **Privacy by Design**: Antenna states indicate when agent is listening

## MCP Tools Overview

The Reachy MCP server provides 23 tools organized by category:

| Category | Tools | Mock Support |
|----------|-------|--------------|
| Movement (5) | `move_head`, `look_at`, `look_at_world`, `look_at_pixel`, `rotate` | 3/5 |
| Expression (6) | `play_emotion`, `play_recorded_move`, `set_antenna_state`, `nod`, `shake`, `rest` | 5/6 |
| Audio (2) | `speak`, `listen` | 2/2 |
| Perception (3) | `capture_image`, `get_sensor_data`, `look_at_sound` | 3/3 |
| Lifecycle (3) | `wake_up`, `sleep`, `rest` | 3/3 |
| Status (2) | `get_status`, `get_pose` | 2/2 |
| Control (2) | `set_motor_mode`, `cancel_action` | 1/2 |

### Native SDK Emotions

The agent uses native SDK emotions from `pollen-robotics/reachy-mini-emotions-library` (HuggingFace) when available:

```mermaid
flowchart LR
    subgraph Agent
        EMO["play_emotion('happy')"]
    end

    subgraph Check["Emotion Lookup"]
        NATIVE{"Native SDK<br/>Available?"}
    end

    subgraph SDK["HuggingFace"]
        HF["cheerful1<br/>(with audio)"]
    end

    subgraph Custom
        CUSTOM["Custom composition<br/>(head + antennas)"]
    end

    EMO --> NATIVE
    NATIVE -->|Yes| HF
    NATIVE -->|No| CUSTOM

    style HF fill:#c8e6c9
    style CUSTOM fill:#fff9c4
```

## Next Steps

See [Phase 2 Preparation Guide](../guides/phase2-preparation.md) for hardware integration details.
