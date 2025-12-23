# Technical Requirements Document: Reachy Agent

**Created**: December 2024
**Version**: 1.0
**Complexity**: Complex (Distributed Embedded AI System)
**PRD Reference**: PRD.md

---

## Executive Summary

Reachy Agent is an embodied AI system that transforms a Reachy Mini desktop robot into an autonomous Claude-powered agent. The system runs on a Raspberry Pi 4, integrating the Claude Agent SDK with custom perception, memory, and expression subsystems via MCP (Model Context Protocol) servers.

**Key Technical Challenges**:
1. ARM64 compatibility for Claude Agent SDK on Raspberry Pi
2. Real-time audio/vision processing within 2GB RAM budget
3. Tiered permission system for safe autonomous operation
4. Graceful degradation when offline or under thermal throttling
5. Multi-modal perception (audio, vision, IMU) feeding a unified agent loop

---

## Architecture

### Pattern

**Layered Monolith with MCP Sidecar Pattern**

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLOUD LAYER                                     │
│  ┌─────────────────┐                                                    │
│  │  Anthropic API  │◀──────── HTTPS ────────────────────────────┐      │
│  │  (Claude)       │                                             │      │
│  └─────────────────┘                                             │      │
└──────────────────────────────────────────────────────────────────┼──────┘
                                                                    │
┌──────────────────────────────────────────────────────────────────┼──────┐
│                    RASPBERRY PI 4 (ARM64)                        │      │
│                                                                   │      │
│  ┌────────────────────────────────────────────────────────────────┼────┐│
│  │                     APPLICATION LAYER                          │    ││
│  │  ┌──────────────────────────────────────────────────────────┐  │    ││
│  │  │              Claude Agent SDK (Python)                    │◀─┘    ││
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │       ││
│  │  │  │ Agent Loop  │  │   Hooks     │  │ Permissions │       │       ││
│  │  │  │ (asyncio)   │  │ PreToolUse  │  │   Tiers     │       │       ││
│  │  │  └──────┬──────┘  └─────────────┘  └─────────────┘       │       ││
│  │  └─────────┼────────────────────────────────────────────────┘       ││
│  │            │ MCP Protocol (in-process)                              ││
│  │            ▼                                                         ││
│  │  ┌──────────────────────────────────────────────────────────┐       ││
│  │  │              REACHY AGENT CORE                            │       ││
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐     │       ││
│  │  │  │Perception│ │  Memory  │ │Personality│ │ Privacy  │     │       ││
│  │  │  │ System   │ │  System  │ │  Engine   │ │  Layer   │     │       ││
│  │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘     │       ││
│  │  └──────────────────────────────────────────────────────────┘       ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                              │                                           │
│                              │ HTTP localhost:8000                       │
│                              ▼                                           │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                    REACHY DAEMON (Pollen Robotics)                   ││
│  │                         FastAPI Server                                ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                    │              │              │                       │
│              ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐                  │
│              │  Motors   │ │  Camera   │ │   Audio   │                  │
│              │  (6 DOF)  │ │   + IMU   │ │  (4-mic)  │                  │
│              └───────────┘ └───────────┘ └───────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

**Rationale**:
- Layered monolith chosen over microservices for MVP due to Pi resource constraints
- MCP protocol provides clean boundaries between agent and robot control
- Single asyncio process reduces memory overhead vs multiple services
- Can migrate to systemd services in v1.0+ if fault isolation needed

### Component Structure

| Component | Responsibility | Communication |
|-----------|---------------|---------------|
| **Claude Agent SDK** | Agent loop, tool execution, context | In-process Python |
| **Reachy MCP Server** | Robot body control tools | MCP (in-process) |
| **Perception System** | Audio, vision, IMU processing | Async queues |
| **Memory System** | Short/long-term storage | ChromaDB + SQLite |
| **Permission Hooks** | Tool execution gating | SDK hooks API |
| **Expression Engine** | Antenna/emotion sequences | Internal API |
| **Resilience Layer** | Health, fallback, recovery | Monitoring thread |

### Data Flow

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

---

## Technology Stack

### Backend Runtime

| Choice | Alternative Considered | Rationale |
|--------|----------------------|-----------|
| **Python 3.10+** | Python 3.11, 3.12 | 3.10 is stable on Pi OS, match patterns available, Agent SDK compatible |

### Core Frameworks

| Component | Choice | Alternative | Rationale |
|-----------|--------|-------------|-----------|
| Agent SDK | `claude-agent-sdk` | Direct API calls | Native loop management, hooks, MCP integration |
| MCP Server | `mcp` Python SDK | Custom protocol | Standard protocol, SDK support, community servers |
| Async Runtime | `asyncio` | `trio`, `uvloop` | Standard library, SDK compatible, lower complexity |
| HTTP Client | `httpx` | `aiohttp`, `requests` | Async native, good API, type hints |

### Perception Stack

| Component | Choice | Alternative | Rationale |
|-----------|--------|-------------|-----------|
| Wake Word | **OpenWakeWord** | Porcupine, Vosk | Open source, customizable, no license costs |
| Audio Processing | `PyAudio` + `numpy` | `sounddevice` | Reachy SDK compatibility, well-documented |
| Spatial Audio | `pyroomacoustics` | Custom DOA | Proven algorithms, academic backing |
| Vision | `opencv-python` | Pillow, picamera2 | Reachy daemon compatibility, OpenCV ecosystem |
| Face Detection | `MediaPipe` | YOLO, dlib | Lightweight, Google maintained, good Pi perf |

### Memory Stack

| Component | Choice | Alternative | Rationale |
|-----------|--------|-------------|-----------|
| Vector Store | **ChromaDB** | Qdrant, Milvus, FAISS | Lightweight, persistent, Python native |
| Structured Data | **SQLite** | PostgreSQL, TinyDB | Zero config, file-based, sufficient for single-user |
| Embeddings | **Hybrid** | Local only, API only | Local (sentence-transformers) for real-time, API for periodic re-indexing |
| Local Model | `all-MiniLM-L6-v2` | BGE, E5 | ~90MB, good quality/size tradeoff for Pi |

### Offline Fallback Stack

| Component | Choice | Alternative | Rationale |
|-----------|--------|-------------|-----------|
| Local LLM | **Ollama + Llama 3.2 3B** | llama.cpp, Phi-3 | Easy setup, 3B fits RAM, decent quality |
| Local STT | `whisper.cpp` (small) | Vosk, faster-whisper | Best quality for size, C++ optimized |
| Local TTS | **Piper** | Coqui, eSpeak | Neural quality, Pi optimized, fast |
| Local Vision | `SmolVLM2` or YOLO | MediaPipe only | VLM for descriptions, YOLO for detection |

### Infrastructure

| Component | Choice | Rationale |
|-----------|--------|-----------|
| OS | Raspberry Pi OS (64-bit) | Official, ARM64, Reachy tested |
| Process Management | **Single asyncio (MVP)** | Lower memory, simpler debugging, migrate to systemd v1.0+ |
| Service Init | systemd (agent.service) | Boot integration, auto-restart |
| Logging | Python `logging` + `structlog` | Structured JSON logs, file rotation |

### Configuration

| Aspect | Choice | Rationale |
|--------|--------|-----------|
| Format | **YAML + JSON Schema** | Human-readable editing, machine validation |
| Validation | `pydantic` | Type-safe Python models from schema |
| Secrets | Environment variables | Never in config files, .env.example template |

### Dashboard (P2)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Backend | FastAPI | Already used by daemon, async native |
| Frontend | **React** | Full SPA flexibility, WebSocket support |
| Real-time | WebSocket | FastAPI native, status streaming |

---

## Data Architecture

### Core Entities

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "definitions": {
    "Memory": {
      "type": "object",
      "description": "A stored memory in ChromaDB",
      "properties": {
        "id": {
          "type": "string",
          "description": "Unique memory identifier",
          "pattern": "^mem_[0-9]+\\.[0-9]+$"
        },
        "content": {
          "type": "string",
          "description": "The memory text content"
        },
        "embedding": {
          "type": "array",
          "items": {"type": "number"},
          "description": "384-dim vector from sentence-transformers"
        },
        "metadata": {
          "$ref": "#/definitions/MemoryMetadata"
        }
      },
      "required": ["id", "content", "metadata"]
    },
    "MemoryMetadata": {
      "type": "object",
      "properties": {
        "timestamp": {
          "type": "string",
          "format": "date-time"
        },
        "type": {
          "type": "string",
          "enum": ["observation", "preference", "instruction", "interaction", "event"]
        },
        "source": {
          "type": "string",
          "enum": ["user", "system", "perception", "agent"]
        },
        "importance": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "expires_at": {
          "type": "string",
          "format": "date-time",
          "description": "Optional TTL for temporary memories"
        }
      },
      "required": ["timestamp", "type", "source"]
    },
    "PersonalityState": {
      "type": "object",
      "description": "Current personality/mood state",
      "properties": {
        "mood": {
          "type": "string",
          "enum": ["happy", "neutral", "tired", "curious", "alert", "playful"]
        },
        "energy": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "description": "0 = exhausted, 1 = fully energized"
        },
        "last_interaction": {
          "type": "string",
          "format": "date-time"
        },
        "interaction_count_today": {
          "type": "integer",
          "minimum": 0
        }
      },
      "required": ["mood", "energy"]
    },
    "AttentionState": {
      "type": "object",
      "description": "Current attention level",
      "properties": {
        "level": {
          "type": "string",
          "enum": ["passive", "alert", "engaged"]
        },
        "since": {
          "type": "string",
          "format": "date-time"
        },
        "trigger": {
          "type": "string",
          "description": "What caused current state"
        }
      },
      "required": ["level", "since"]
    },
    "ToolExecution": {
      "type": "object",
      "description": "Audit log entry for tool execution",
      "properties": {
        "id": {
          "type": "string",
          "format": "uuid"
        },
        "timestamp": {
          "type": "string",
          "format": "date-time"
        },
        "tool_name": {
          "type": "string"
        },
        "tool_input": {
          "type": "object"
        },
        "permission_tier": {
          "type": "integer",
          "minimum": 1,
          "maximum": 4
        },
        "decision": {
          "type": "string",
          "enum": ["allowed", "notified", "confirmed", "denied"]
        },
        "result": {
          "type": "string",
          "enum": ["success", "error", "timeout"]
        },
        "duration_ms": {
          "type": "integer"
        }
      },
      "required": ["id", "timestamp", "tool_name", "permission_tier", "decision"]
    },
    "Expression": {
      "type": "object",
      "description": "Antenna/body expression definition",
      "properties": {
        "name": {
          "type": "string"
        },
        "left_antenna": {
          "$ref": "#/definitions/AntennaMotion"
        },
        "right_antenna": {
          "$ref": "#/definitions/AntennaMotion"
        },
        "head_motion": {
          "$ref": "#/definitions/HeadMotion"
        },
        "duration_ms": {
          "type": "integer",
          "minimum": 100
        }
      },
      "required": ["name", "left_antenna", "right_antenna"]
    },
    "AntennaMotion": {
      "type": "object",
      "properties": {
        "start_angle": {"type": "number", "minimum": 0, "maximum": 90},
        "end_angle": {"type": "number", "minimum": 0, "maximum": 90},
        "pattern": {
          "type": "string",
          "enum": ["static", "wiggle", "wave", "pulse"]
        },
        "easing": {
          "type": "string",
          "enum": ["linear", "ease_in", "ease_out", "ease_in_out"]
        }
      }
    },
    "HeadMotion": {
      "type": "object",
      "properties": {
        "pitch": {"type": "number", "minimum": -30, "maximum": 30},
        "yaw": {"type": "number", "minimum": -45, "maximum": 45},
        "roll": {"type": "number", "minimum": -15, "maximum": 15}
      }
    }
  }
}
```

### Storage Strategy

| Data Type | Storage | Retention | Backup |
|-----------|---------|-----------|--------|
| Long-term memories | ChromaDB (SQLite backend) | Configurable (default 90 days) | External SSD |
| Audit logs | SQLite | 7 days rolling | External SSD |
| Personality state | SQLite | Permanent | External SSD |
| Session context | In-memory | Session only | None |
| Configuration | YAML files | Permanent | Git |

### Schema Migrations

- Use `alembic` for SQLite schema versioning
- ChromaDB collections are append-only, version in metadata
- Config schema version in YAML header

---

## MCP Server Specifications

### Reachy Body Control MCP

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Reachy MCP Tools",
  "description": "MCP tools for controlling Reachy Mini robot body",
  "tools": {
    "move_head": {
      "description": "Move Reachy's head to look in a direction",
      "inputSchema": {
        "type": "object",
        "properties": {
          "direction": {
            "type": "string",
            "enum": ["left", "right", "up", "down", "front"],
            "description": "Direction to look"
          },
          "speed": {
            "type": "string",
            "enum": ["slow", "normal", "fast"],
            "default": "normal"
          },
          "degrees": {
            "type": "number",
            "minimum": 0,
            "maximum": 45,
            "description": "Optional: specific angle in degrees"
          }
        },
        "required": ["direction"]
      },
      "permissionTier": 1
    },
    "play_emotion": {
      "description": "Display an emotional expression through movement and antennas",
      "inputSchema": {
        "type": "object",
        "properties": {
          "emotion": {
            "type": "string",
            "enum": ["happy", "sad", "curious", "excited", "confused", "thinking", "surprised", "tired", "alert"],
            "description": "Emotion to express"
          },
          "intensity": {
            "type": "number",
            "minimum": 0.1,
            "maximum": 1.0,
            "default": 0.7
          }
        },
        "required": ["emotion"]
      },
      "permissionTier": 1
    },
    "speak": {
      "description": "Speak text aloud through Reachy's speaker",
      "inputSchema": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string",
            "maxLength": 500,
            "description": "Text to speak"
          },
          "voice": {
            "type": "string",
            "default": "default"
          },
          "speed": {
            "type": "number",
            "minimum": 0.5,
            "maximum": 2.0,
            "default": 1.0
          }
        },
        "required": ["text"]
      },
      "permissionTier": 1
    },
    "capture_image": {
      "description": "Capture an image from Reachy's camera",
      "inputSchema": {
        "type": "object",
        "properties": {
          "analyze": {
            "type": "boolean",
            "default": false,
            "description": "Whether to analyze the image content via vision model"
          },
          "save": {
            "type": "boolean",
            "default": false,
            "description": "Whether to save the image to disk"
          }
        }
      },
      "permissionTier": 1
    },
    "set_antenna_state": {
      "description": "Control antenna positions for expression",
      "inputSchema": {
        "type": "object",
        "properties": {
          "left_angle": {
            "type": "number",
            "minimum": 0,
            "maximum": 90
          },
          "right_angle": {
            "type": "number",
            "minimum": 0,
            "maximum": 90
          },
          "wiggle": {
            "type": "boolean",
            "default": false
          },
          "duration_ms": {
            "type": "integer",
            "default": 500
          }
        }
      },
      "permissionTier": 1
    },
    "get_sensor_data": {
      "description": "Get current sensor readings",
      "inputSchema": {
        "type": "object",
        "properties": {
          "sensors": {
            "type": "array",
            "items": {
              "type": "string",
              "enum": ["imu", "audio_level", "temperature", "all"]
            },
            "default": ["all"]
          }
        }
      },
      "permissionTier": 1
    },
    "look_at_sound": {
      "description": "Turn to face the direction of detected sound",
      "inputSchema": {
        "type": "object",
        "properties": {
          "timeout_ms": {
            "type": "integer",
            "default": 2000
          }
        }
      },
      "permissionTier": 1
    },
    "dance": {
      "description": "Perform a choreographed dance routine",
      "inputSchema": {
        "type": "object",
        "properties": {
          "routine": {
            "type": "string",
            "description": "Name of dance routine",
            "enum": ["celebrate", "greeting", "thinking", "custom"]
          },
          "duration_seconds": {
            "type": "number",
            "minimum": 1,
            "maximum": 30,
            "default": 5
          }
        },
        "required": ["routine"]
      },
      "permissionTier": 1
    }
  }
}
```

### External MCP Integrations (MVP Priority)

| Integration | MCP Server | Permission Tier | MVP Status |
|-------------|------------|-----------------|------------|
| **Home Assistant** | `homeassistant-mcp` | 2 (notify) / 3 (security) | ✅ MVP |
| **Google Calendar** | Custom or `gcal-mcp` | 1 (read) / 3 (create) | ✅ MVP |
| **GitHub** | `github-mcp` | 1 (read) / 3 (create) | ✅ MVP |
| Slack | `slack-mcp` | 2 (notify) | v1.0 |
| Spotify | `spotify-mcp` | 2 (notify) | v1.0 |
| Weather | Custom | 1 (read) | ✅ MVP |

---

## Permission System

### Tier Definitions

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Permission Configuration",
  "type": "object",
  "properties": {
    "tiers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "tier": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4
          },
          "name": {
            "type": "string",
            "enum": ["autonomous", "notify", "confirm", "forbidden"]
          },
          "description": {
            "type": "string"
          },
          "behavior": {
            "type": "object",
            "properties": {
              "execute": {"type": "boolean"},
              "notify_user": {"type": "boolean"},
              "require_confirmation": {"type": "boolean"},
              "confirmation_timeout_seconds": {"type": "integer"}
            }
          }
        }
      }
    },
    "rules": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "pattern": {
            "type": "string",
            "description": "Tool name pattern with wildcards"
          },
          "tier": {
            "type": "integer",
            "minimum": 1,
            "maximum": 4
          },
          "reason": {
            "type": "string"
          }
        },
        "required": ["pattern", "tier", "reason"]
      }
    }
  }
}
```

### Default Permission Rules

```yaml
# config/permissions.yaml
tiers:
  - tier: 1
    name: autonomous
    description: Execute immediately without notification
    behavior:
      execute: true
      notify_user: false
      require_confirmation: false

  - tier: 2
    name: notify
    description: Execute and notify user
    behavior:
      execute: true
      notify_user: true
      require_confirmation: false

  - tier: 3
    name: confirm
    description: Request confirmation before execution
    behavior:
      execute: true
      notify_user: true
      require_confirmation: true
      confirmation_timeout_seconds: 60

  - tier: 4
    name: forbidden
    description: Never execute, explain why
    behavior:
      execute: false
      notify_user: true
      require_confirmation: false

rules:
  # Tier 1: Autonomous (body control, observation)
  - pattern: "mcp__reachy__*"
    tier: 1
    reason: "Body control"
  - pattern: "mcp__calendar__get_*"
    tier: 1
    reason: "Read-only calendar access"
  - pattern: "mcp__weather__*"
    tier: 1
    reason: "Weather information"
  - pattern: "mcp__github__get_*"
    tier: 1
    reason: "Read-only GitHub access"

  # Tier 2: Notify (reversible actions)
  - pattern: "mcp__homeassistant__turn_on_*"
    tier: 2
    reason: "Smart home control"
  - pattern: "mcp__homeassistant__turn_off_*"
    tier: 2
    reason: "Smart home control"
  - pattern: "mcp__slack__send_message"
    tier: 2
    reason: "Communication"
  - pattern: "mcp__spotify__*"
    tier: 2
    reason: "Media control"

  # Tier 3: Confirm (irreversible or sensitive)
  - pattern: "mcp__calendar__create_*"
    tier: 3
    reason: "Creates calendar data"
  - pattern: "mcp__github__create_*"
    tier: 3
    reason: "Creates repository data"
  - pattern: "mcp__homeassistant__unlock_*"
    tier: 3
    reason: "Security action"
  - pattern: "Bash"
    tier: 3
    reason: "System access"

  # Tier 4: Forbidden
  - pattern: "mcp__homeassistant__disarm_*"
    tier: 4
    reason: "Security critical - never autonomous"
  - pattern: "mcp__email__send"
    tier: 4
    reason: "Impersonation risk"
  - pattern: "mcp__banking__*"
    tier: 4
    reason: "Financial operations"
```

---

## Security

### Authentication & Authorization

| Aspect | Implementation |
|--------|---------------|
| API Keys | Environment variables, never in config |
| Inter-process | localhost only, no auth needed |
| Daemon API | HTTP on localhost:8000, no external exposure |
| Dashboard (P2) | Optional basic auth or local-only |

### Data Protection

| Data Type | Protection |
|-----------|-----------|
| API keys | Environment variables, `.env` in `.gitignore` |
| Audio recordings | Ephemeral (not stored by default) |
| Images | Ephemeral unless explicitly saved |
| Memories | Local encrypted SQLite (optional) |
| Audit logs | Local only, 7-day retention |

### OWASP Considerations

| Risk | Mitigation |
|------|-----------|
| Injection | Pydantic validation on all inputs, no shell interpolation |
| Broken Auth | Local-only operation, no remote access by default |
| Sensitive Data | No cloud storage, local-first architecture |
| Security Misconfiguration | Secure defaults, setup wizard validation |

---

## Performance & Scalability

### Performance Budgets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Wake word detection | < 500ms | From utterance end to detection callback |
| Voice-to-response | < 3s | From speech end to first audio output |
| Motion smoothness | 30 FPS | Servo update rate |
| Memory usage | < 2GB RAM | Total process memory |
| Startup time | < 60s | From boot to ready |
| API response (daemon) | < 100ms | Local HTTP calls |

### Resource Constraints (Pi 4)

| Resource | Budget | Allocation |
|----------|--------|-----------|
| RAM (4GB) | 2GB app, 1GB OS, 1GB buffer | ChromaDB ~200MB, Models ~500MB, Agent ~300MB |
| CPU (4 cores) | 2 cores perception, 1 core agent, 1 core system | Avoid thermal throttling |
| Storage | 32GB min, 64GB recommended | 8GB models, 2GB memories, 4GB logs |

### Scaling Strategy

**Single user, single device** - no horizontal scaling needed for MVP.

Future considerations (v2.0+):
- Multi-robot coordination via shared MCP server
- Offload vision processing to edge device
- Distributed memory across robots

---

## Resilience & Fault Tolerance

### Graceful Degradation Modes

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Degradation Modes",
  "type": "object",
  "properties": {
    "modes": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "trigger": {"type": "string"},
          "capabilities": {
            "type": "object",
            "properties": {
              "claude_api": {"type": "boolean"},
              "speech_recognition": {"type": "string", "enum": ["cloud", "local", "none"]},
              "text_to_speech": {"type": "string", "enum": ["cloud", "local", "none"]},
              "vision": {"type": "string", "enum": ["full", "basic", "none"]},
              "memory": {"type": "string", "enum": ["full", "local", "none"]},
              "body_control": {"type": "boolean"}
            }
          }
        }
      }
    }
  }
}
```

### Degradation Ladder

| Mode | Trigger | Claude API | STT | TTS | Vision | Body |
|------|---------|-----------|-----|-----|--------|------|
| **Full** | Normal operation | ✅ Cloud | ✅ Cloud | ✅ Cloud | ✅ Full | ✅ |
| **Offline** | No internet | ❌ Ollama | Whisper.cpp | Piper | Basic | ✅ |
| **Thermal** | CPU > 80°C | ✅ Cloud | ✅ Cloud | ✅ Cloud | ❌ Off | ⚠️ Slow |
| **Low Power** | Battery < 20% | ❌ Ollama | Vosk | Piper | ❌ Off | ⚠️ Slow |
| **Safe Mode** | Critical error | ❌ Off | ❌ Off | Canned | ❌ Off | ⚠️ Safe pose |

### Health Monitoring

| Check | Interval | Threshold | Action |
|-------|----------|-----------|--------|
| CPU temperature | 5s | > 80°C | Enter thermal mode |
| Memory usage | 30s | > 90% | Clear caches, compact context |
| API latency | Per-call | > 5s | Log warning, consider offline |
| Disk space | 5m | < 1GB | Rotate logs, warn user |
| Daemon health | 10s | 3 failures | Restart daemon, notify |

---

## Configuration Schemas

### Main Configuration

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Reachy Agent Configuration",
  "type": "object",
  "properties": {
    "version": {
      "type": "string",
      "pattern": "^[0-9]+\\.[0-9]+$"
    },
    "agent": {
      "type": "object",
      "properties": {
        "name": {
          "type": "string",
          "default": "Reachy"
        },
        "wake_word": {
          "type": "string",
          "default": "hey reachy"
        },
        "model": {
          "type": "string",
          "enum": ["claude-sonnet-4-20250514", "claude-3-5-haiku-20241022"],
          "default": "claude-sonnet-4-20250514"
        },
        "max_tokens": {
          "type": "integer",
          "default": 1024
        }
      }
    },
    "perception": {
      "type": "object",
      "properties": {
        "wake_word_engine": {
          "type": "string",
          "enum": ["openwakeword", "porcupine", "vosk"],
          "default": "openwakeword"
        },
        "wake_word_sensitivity": {
          "type": "number",
          "minimum": 0,
          "maximum": 1,
          "default": 0.5
        },
        "spatial_audio_enabled": {
          "type": "boolean",
          "default": true
        },
        "vision_enabled": {
          "type": "boolean",
          "default": true
        },
        "face_detection_enabled": {
          "type": "boolean",
          "default": true
        }
      }
    },
    "memory": {
      "type": "object",
      "properties": {
        "chroma_path": {
          "type": "string",
          "default": "~/.reachy/memory/chroma"
        },
        "sqlite_path": {
          "type": "string",
          "default": "~/.reachy/memory/reachy.db"
        },
        "embedding_model": {
          "type": "string",
          "default": "all-MiniLM-L6-v2"
        },
        "max_memories": {
          "type": "integer",
          "default": 10000
        },
        "retention_days": {
          "type": "integer",
          "default": 90
        }
      }
    },
    "attention": {
      "type": "object",
      "properties": {
        "passive_to_alert_motion_threshold": {
          "type": "number",
          "default": 0.3
        },
        "alert_to_passive_timeout_minutes": {
          "type": "integer",
          "default": 5
        },
        "engaged_to_alert_silence_seconds": {
          "type": "integer",
          "default": 30
        }
      }
    },
    "resilience": {
      "type": "object",
      "properties": {
        "thermal_threshold_celsius": {
          "type": "number",
          "default": 80
        },
        "api_timeout_seconds": {
          "type": "number",
          "default": 30
        },
        "max_retries": {
          "type": "integer",
          "default": 3
        },
        "offline_llm_model": {
          "type": "string",
          "default": "llama3.2:3b"
        }
      }
    },
    "privacy": {
      "type": "object",
      "properties": {
        "audit_logging_enabled": {
          "type": "boolean",
          "default": true
        },
        "audit_retention_days": {
          "type": "integer",
          "default": 7
        },
        "store_audio": {
          "type": "boolean",
          "default": false
        },
        "store_images": {
          "type": "boolean",
          "default": false
        }
      }
    },
    "integrations": {
      "type": "object",
      "properties": {
        "home_assistant": {
          "type": "object",
          "properties": {
            "enabled": {"type": "boolean", "default": false},
            "url": {"type": "string"},
            "token_env_var": {"type": "string", "default": "HA_TOKEN"}
          }
        },
        "google_calendar": {
          "type": "object",
          "properties": {
            "enabled": {"type": "boolean", "default": false},
            "credentials_path": {"type": "string"}
          }
        },
        "github": {
          "type": "object",
          "properties": {
            "enabled": {"type": "boolean", "default": false},
            "token_env_var": {"type": "string", "default": "GITHUB_TOKEN"},
            "repos": {
              "type": "array",
              "items": {"type": "string"}
            }
          }
        }
      }
    }
  },
  "required": ["version", "agent"]
}
```

### Expression Definitions

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Expression Library",
  "type": "object",
  "properties": {
    "expressions": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/definitions/Expression"
      }
    }
  },
  "definitions": {
    "Expression": {
      "type": "object",
      "properties": {
        "description": {"type": "string"},
        "left_antenna": {
          "type": "object",
          "properties": {
            "angle": {"type": "number"},
            "pattern": {"type": "string", "enum": ["static", "wiggle", "wave", "pulse"]},
            "speed": {"type": "number", "default": 1.0}
          }
        },
        "right_antenna": {
          "type": "object",
          "properties": {
            "angle": {"type": "number"},
            "pattern": {"type": "string"},
            "speed": {"type": "number", "default": 1.0}
          }
        },
        "head": {
          "type": "object",
          "properties": {
            "pitch": {"type": "number"},
            "yaw": {"type": "number"},
            "roll": {"type": "number"}
          }
        },
        "duration_ms": {"type": "integer", "default": 1000}
      }
    }
  }
}
```

---

## Deployment Strategy

### Development Environment

```bash
# Clone and setup
git clone https://github.com/jawhnycooke/reachy-agent.git
cd reachy-agent

# Create virtual environment
uv venv && source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
uv pip install -r requirements-dev.txt

# Copy environment template
cp .env.example .env
# Edit .env with API keys

# Run in development mode
python -m src.main --dev
```

### Production Deployment (Pi)

```bash
# Install script
curl -fsSL https://raw.githubusercontent.com/jawhnycooke/reachy-agent/main/install.sh | bash

# Or manual:
# 1. Clone repository
# 2. Run setup wizard
python scripts/setup_wizard.py

# 3. Enable systemd service
sudo systemctl enable reachy-agent
sudo systemctl start reachy-agent
```

### systemd Service (for production)

```ini
# /etc/systemd/system/reachy-agent.service
[Unit]
Description=Reachy Agent
After=network.target reachy-daemon.service
Wants=reachy-daemon.service

[Service]
Type=simple
User=reachy
WorkingDirectory=/home/reachy/reachy-agent
Environment=PATH=/home/reachy/.local/bin:/usr/bin
EnvironmentFile=/home/reachy/reachy-agent/.env
ExecStart=/home/reachy/reachy-agent/.venv/bin/python -m src.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Testing Strategy

### Test Pyramid

| Level | Coverage Target | Tools |
|-------|-----------------|-------|
| Unit | 80% | pytest, pytest-asyncio |
| Integration | Key paths | pytest, MCP test client |
| E2E (simulation) | Happy paths | MuJoCo, pytest |
| E2E (hardware) | Manual | Physical robot |

### Test Categories

```bash
# Run all tests
uvx pytest -v

# Unit tests only
uvx pytest tests/unit -v

# Integration tests (requires daemon mock)
uvx pytest tests/integration -v

# With coverage
uvx pytest --cov=src --cov-report=html
```

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| ARM64 SDK issues | Medium | High | Test early, Docker fallback, pin versions |
| Thermal throttling | Medium | Medium | Heatsink, active cooling, thermal monitoring |
| API costs exceed budget | Medium | Medium | Attention state optimization, local fallbacks |
| ChromaDB corruption | Low | High | Regular backups to external SSD |
| Reachy daemon API changes | Low | High | Pin Reachy SDK version, integration tests |
| Wake word false positives | Medium | Low | Tune sensitivity, add confirmation |

---

## PRD Alignment

### Product Requirements → Technical Decisions

| PRD Requirement | Technical Approach |
|-----------------|-------------------|
| G1: Functional autonomous agent | Claude Agent SDK with MCP, async event loop |
| G2: Reliable operation (<1% crash) | Health monitoring, graceful degradation, systemd restart |
| G3: Extensible platform (5+ MCP) | MCP standard, integration registry, permission system |
| G5: Privacy-respecting | Antenna state indicators, audit logging, local-first storage |
| G6: Offline capability (30+ min) | Ollama + Piper + Whisper.cpp fallback stack |
| F1: Wake word detection (<500ms) | OpenWakeWord, local processing |
| F7: Memory system | ChromaDB + SQLite + sentence-transformers |
| NFR: <2GB RAM | Single process, lazy loading, memory budgets |

### Technical Decisions → Product Impact

| Technical Choice | Product Impact |
|-----------------|----------------|
| OpenWakeWord vs Porcupine | No license cost, fully customizable wake word |
| Single asyncio process | Simpler debugging, lower memory, less fault isolation |
| Hybrid embeddings | Real-time local, quality from periodic API reindex |
| YAML + JSON Schema config | Human-editable, machine-validatable, IDE support |

---

## Next Steps

This TRD feeds into the EPCC workflow:

**Greenfield project** - recommended path:
1. ✅ Review and approve this TRD
2. Run `/epcc-plan` to create implementation plan
3. Begin development with `/epcc-code`
4. Finalize with `/epcc-commit`

**Key implementation questions resolved:**
- Wake word: OpenWakeWord
- Embeddings: Hybrid (local + API)
- Offline LLM: Ollama + Llama 3.2 3B
- Config: YAML + JSON Schema
- TTS: Piper
- Process management: Single asyncio (MVP)
- Dashboard: FastAPI + React (P2)
- MVP integrations: Home Assistant, Google Calendar, GitHub

---

**End of TRD**
