# Product Requirements Document: Reachy Mini Embodied AI Agent

**Project Name:** Reachy Agent  
**Author:** Jawhny Cooke  
**Version:** 1.0  
**Last Updated:** December 2024  
**Status:** Planning

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Goals & Success Criteria](#3-goals--success-criteria)
4. [Target Users](#4-target-users)
5. [Product Overview](#5-product-overview)
6. [Technical Architecture](#6-technical-architecture)
7. [Feature Requirements](#7-feature-requirements)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Implementation Phases](#9-implementation-phases)
10. [Content Strategy](#10-content-strategy)
11. [Risks & Mitigations](#11-risks--mitigations)
12. [References](#12-references)

---

## 1. Executive Summary

### Vision

Transform Reachy Mini from a programmable desktop robot into an autonomous AI agent with physical presence. By installing the Claude Agent SDK directly on Reachy's Raspberry Pi 4, the robot becomes a Claude agent that can perceive its environment, make decisions, and interact with both the physical and digital world through Model Context Protocol (MCP) servers.

### Value Proposition

- **For developers:** An open-source reference implementation of embodied AI that bridges cloud intelligence with physical robotics
- **For the community:** Educational content documenting the journey from unboxing to autonomous agent
- **For the ecosystem:** A demonstration of Claude Agent SDK + MCP capabilities in a novel form factor

### Unique Differentiation

| Competitor | Limitation | Reachy Agent Advantage |
|------------|------------|------------------------|
| Anki Vector | Closed ecosystem, discontinued | Open source, actively developed |
| Amazon Astro | Home robot, consumer-focused | Desktop form factor, developer-first |
| EMO Robot | Scripted behaviors | Real AI decision-making |
| DIY chatbots | No physical presence | Embodied with expressions, gestures, spatial awareness |

---

## 2. Problem Statement

### Current State

Desktop robots exist. AI assistants exist. But the intersection—an open-source, developer-friendly desktop robot powered by frontier AI models—remains underexplored. Existing solutions are either:

1. **Closed ecosystems** (Vector, Jibo) that died when companies pivoted
2. **Consumer products** (Astro) not designed for developer extensibility
3. **Toy-grade** (EMO) with scripted rather than intelligent behaviors
4. **Disembodied** (Claude, GPT) lacking physical presence and world interaction

### Opportunity

Reachy Mini, created by Pollen Robotics and Hugging Face, provides the hardware foundation. The Claude Agent SDK provides the intelligence layer. MCP provides the extensibility framework. The opportunity is to connect these pieces into a cohesive, documented, reproducible system that others can learn from and build upon.

### Target Outcome

A desktop robot that:
- Knows your calendar and reminds you of meetings with physical gestures
- Monitors your GitHub repos and reacts to CI failures
- Controls your smart home while physically pointing toward devices
- Maintains personality consistency across sessions
- Works offline when connectivity fails
- Respects privacy with transparent data handling

---

## 3. Goals & Success Criteria

### Primary Goals

| Goal | Success Metric |
|------|----------------|
| **G1:** Functional autonomous agent | Reachy responds to voice, executes multi-step tasks via MCP, maintains conversation context |
| **G2:** Reliable operation | <1% crash rate, graceful degradation on failures, 8+ hours continuous operation |
| **G3:** Extensible platform | 5+ MCP integrations working, documented API for community contributions |
| **G4:** Educational content | 10+ blog posts, 5+ YouTube videos, measurable community engagement |

### Secondary Goals

| Goal | Success Metric |
|------|----------------|
| **G5:** Privacy-respecting | Physical listening indicators, local processing options, audit logging |
| **G6:** Offline capability | Core functions work without internet for 30+ minutes |
| **G7:** Expressive interaction | Antenna expressions, spatial audio awareness, physical touch responses |

### Non-Goals (Explicitly Out of Scope)

- Mobile/locomotion capabilities
- Manipulation/grasping (no arms in Mini)
- Real-time video streaming to cloud
- Multi-robot coordination (future version)
- Commercial product development

---

## 4. Target Users

### Primary Persona: The AI-Curious Developer

**Name:** Alex  
**Role:** Software developer with cloud/AI background  
**Goals:** 
- Explore embodied AI without building hardware from scratch
- Create something tangible to demonstrate AI capabilities
- Learn by building, then share knowledge

**Pain Points:**
- Hardware robotics has steep learning curve
- Most robot kits are toy-grade, not AI-ready
- Existing AI assistants feel disembodied

**Technical Profile:**
- Comfortable with Python, APIs, cloud services
- Some experience with Claude/LLMs
- Limited robotics/embedded experience

### Secondary Persona: The Content Creator

**Name:** Jordan  
**Role:** Technical YouTuber/blogger  
**Goals:**
- Create engaging content at intersection of AI and robotics
- Build audience in emerging niche
- Establish authority in embodied AI space

**Pain Points:**
- AI content is crowded
- Need visual/physical hook for video content
- Wants differentiated angle

### Tertiary Persona: The Researcher/Educator

**Name:** Dr. Kim  
**Role:** HRI (Human-Robot Interaction) researcher or CS educator  
**Goals:**
- Accessible platform for teaching/research
- Reproducible experiments
- Student engagement

---

## 5. Product Overview

### System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL SERVICES                               │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐            │
│  │  Anthropic  │ │   GitHub    │ │    Slack    │ │   Google    │   ...      │
│  │     API     │ │     API     │ │     API     │ │  Calendar   │            │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘            │
└─────────┼───────────────┼───────────────┼───────────────┼───────────────────┘
          │               │               │               │
          │ HTTPS         │ MCP           │ MCP           │ MCP
          │               │               │               │
┌─────────┼───────────────┼───────────────┼───────────────┼───────────────────┐
│         │               │               │               │                    │
│         ▼               ▼               ▼               ▼                    │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      CLAUDE AGENT SDK                                │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │    │
│  │  │ Agent Loop  │  │    Hooks    │  │ Permissions │                  │    │
│  │  │             │  │ PreToolUse  │  │   Tiers     │                  │    │
│  │  │ Perceive ──▶│  │ PostToolUse │  │             │                  │    │
│  │  │ Think ─────▶│  │ OnPrompt    │  │             │                  │    │
│  │  │ Act ───────▶│  │             │  │             │                  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    │ Internal MCP                            │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      REACHY AGENT CORE                               │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │    │
│  │  │ Perception  │  │   Memory    │  │ Personality │  │  Privacy   │  │    │
│  │  │   System    │  │   System    │  │    State    │  │  Controls  │  │    │
│  │  │             │  │             │  │             │  │            │  │    │
│  │  │ - Audio     │  │ - ChromaDB  │  │ - Mood      │  │ - Audit    │  │    │
│  │  │ - Vision    │  │ - Short-term│  │ - Energy    │  │ - Indicators│ │    │
│  │  │ - IMU       │  │ - Long-term │  │ - History   │  │ - Local-first││    │
│  │  │ - Spatial   │  │             │  │             │  │            │  │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    │ HTTP (localhost:8000)                   │
│                                    ▼                                         │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      REACHY DAEMON (FastAPI)                         │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │    │
│  │  │   Motion    │  │   Audio     │  │   Vision    │  │  Sensors   │  │    │
│  │  │  Control    │  │  Pipeline   │  │  Pipeline   │  │   (IMU)    │  │    │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘  │    │
│  └─────────┼────────────────┼───────────────┼────────────────┼─────────┘    │
│            │                │               │                │               │
│  ┌─────────┼────────────────┼───────────────┼────────────────┼─────────┐    │
│  │         ▼                ▼               ▼                ▼         │    │
│  │  ┌───────────┐    ┌───────────┐   ┌───────────┐    ┌───────────┐   │    │
│  │  │  Motors   │    │  Speaker  │   │  Camera   │    │Accelerometer│  │    │
│  │  │  Servos   │    │  Mics x4  │   │           │    │            │  │    │
│  │  └───────────┘    └───────────┘   └───────────┘    └───────────┘   │    │
│  │                      HARDWARE                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                           REACHY MINI (Raspberry Pi 4)                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Description | Technology |
|-----------|-------------|------------|
| **Claude Agent SDK** | Agent loop, tool execution, context management | Python 3.10+, claude-agent-sdk |
| **Reachy MCP Server** | Exposes robot capabilities as MCP tools | Python, FastAPI |
| **Perception System** | Audio/video/sensor processing | OpenCV, PyAudio, pyroomacoustics |
| **Memory System** | Short/long-term memory storage | ChromaDB, SQLite |
| **Personality Engine** | Mood, energy, behavioral consistency | Custom Python |
| **Privacy Layer** | Audit, indicators, local processing | Custom Python |
| **Reachy Daemon** | Hardware abstraction (existing) | FastAPI (Pollen) |

---

## 6. Technical Architecture

### 6.1 Hardware Platform

**Reachy Mini Wireless Specifications:**

| Component | Specification | Reference |
|-----------|---------------|-----------|
| Compute | Raspberry Pi 4 (4GB/8GB RAM) | [RPi 4 Specs](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) |
| Head DOF | 6 degrees of freedom | [Reachy Hardware](https://github.com/pollen-robotics/reachy_mini/blob/develop/docs/platforms/reachy_mini/hardware.md) |
| Body | Full 360° rotation | |
| Antennas | 2 animated antennas | |
| Camera | Wide-angle camera | |
| Audio | 4-microphone array, 5W speaker | |
| Sensors | Accelerometer/IMU | |
| Power | Battery + wired option | |
| Connectivity | WiFi | |

### 6.2 Software Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Reachy Agent (Python)                                  ││
│  │  - main.py (entry point)                                ││
│  │  - agent/ (Claude Agent SDK integration)                ││
│  │  - perception/ (audio, vision, sensors)                 ││
│  │  - memory/ (ChromaDB, context management)               ││
│  │  - personality/ (mood, energy, behaviors)               ││
│  │  - privacy/ (audit, controls)                           ││
│  │  - mcp_servers/ (reachy, integrations)                  ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                    FRAMEWORK LAYER                           │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │Claude Agent  │ │   MCP SDK    │ │   ChromaDB   │         │
│  │    SDK       │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │   OpenCV     │ │  PyAudio     │ │ Porcupine/   │         │
│  │              │ │              │ │ OpenWakeWord │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
├─────────────────────────────────────────────────────────────┤
│                    PLATFORM LAYER                            │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │Reachy Daemon │ │  Reachy SDK  │ │ Claude Code  │         │
│  │ (FastAPI)    │ │   (Python)   │ │     CLI      │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
├─────────────────────────────────────────────────────────────┤
│                    SYSTEM LAYER                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │  Python 3.10 │ │   Node.js    │ │   systemd    │         │
│  │              │ │              │ │              │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
├─────────────────────────────────────────────────────────────┤
│                    OS / HARDWARE                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  Raspberry Pi OS (64-bit) / Raspberry Pi 4              ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 6.3 MCP Server Architecture

**Reachy MCP Server (Body Control):**

```python
# reachy_mcp_server/tools.py

TOOLS = [
    {
        "name": "move_head",
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
                }
            },
            "required": ["direction"]
        }
    },
    {
        "name": "play_emotion",
        "description": "Display an emotional expression through movement and antennas",
        "inputSchema": {
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "enum": ["happy", "sad", "curious", "excited", "confused", 
                             "thinking", "surprised", "tired", "alert"],
                    "description": "Emotion to express"
                }
            },
            "required": ["emotion"]
        }
    },
    {
        "name": "speak",
        "description": "Speak text aloud through Reachy's speaker",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak"},
                "voice": {"type": "string", "default": "default"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "dance",
        "description": "Perform a choreographed dance routine",
        "inputSchema": {
            "type": "object",
            "properties": {
                "routine": {
                    "type": "string",
                    "description": "Name of dance routine"
                }
            },
            "required": ["routine"]
        }
    },
    {
        "name": "capture_image",
        "description": "Capture an image from Reachy's camera",
        "inputSchema": {
            "type": "object",
            "properties": {
                "analyze": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to analyze the image content"
                }
            }
        }
    },
    {
        "name": "set_antenna_state",
        "description": "Control antenna positions for expression",
        "inputSchema": {
            "type": "object",
            "properties": {
                "left_angle": {"type": "number", "minimum": 0, "maximum": 90},
                "right_angle": {"type": "number", "minimum": 0, "maximum": 90},
                "wiggle": {"type": "boolean", "default": False}
            }
        }
    },
    {
        "name": "get_sensor_data",
        "description": "Get current sensor readings (IMU, audio levels)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sensors": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["imu", "audio_level", "temperature"]}
                }
            }
        }
    },
    {
        "name": "look_at_sound",
        "description": "Turn to face the direction of detected sound",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]
```

### 6.4 Permission Tiers

```python
# permissions/tiers.py

from enum import Enum
from dataclasses import dataclass

class PermissionTier(Enum):
    AUTONOMOUS = 1      # Execute immediately, no notification
    NOTIFY = 2          # Execute and notify user
    CONFIRM = 3         # Request confirmation before execution
    FORBIDDEN = 4       # Never execute

@dataclass
class ToolPermission:
    tool_pattern: str
    tier: PermissionTier
    reason: str

PERMISSION_CONFIG = [
    # Tier 1: Autonomous (body control, observation)
    ToolPermission("mcp__reachy__move_head", PermissionTier.AUTONOMOUS, "Body control"),
    ToolPermission("mcp__reachy__play_emotion", PermissionTier.AUTONOMOUS, "Expression"),
    ToolPermission("mcp__reachy__speak", PermissionTier.AUTONOMOUS, "Communication"),
    ToolPermission("mcp__reachy__dance", PermissionTier.AUTONOMOUS, "Expression"),
    ToolPermission("mcp__reachy__set_antenna_state", PermissionTier.AUTONOMOUS, "Expression"),
    ToolPermission("mcp__reachy__capture_image", PermissionTier.AUTONOMOUS, "Observation"),
    ToolPermission("mcp__reachy__get_sensor_data", PermissionTier.AUTONOMOUS, "Observation"),
    ToolPermission("mcp__reachy__look_at_sound", PermissionTier.AUTONOMOUS, "Attention"),
    ToolPermission("mcp__calendar__get_events", PermissionTier.AUTONOMOUS, "Information"),
    ToolPermission("mcp__weather__get_forecast", PermissionTier.AUTONOMOUS, "Information"),
    ToolPermission("mcp__github__get_notifications", PermissionTier.AUTONOMOUS, "Information"),
    
    # Tier 2: Notify (reversible actions)
    ToolPermission("mcp__homeassistant__turn_on_*", PermissionTier.NOTIFY, "Smart home"),
    ToolPermission("mcp__homeassistant__turn_off_*", PermissionTier.NOTIFY, "Smart home"),
    ToolPermission("mcp__slack__send_message", PermissionTier.NOTIFY, "Communication"),
    ToolPermission("mcp__spotify__play", PermissionTier.NOTIFY, "Media"),
    
    # Tier 3: Confirm (irreversible or sensitive)
    ToolPermission("mcp__calendar__create_event", PermissionTier.CONFIRM, "Creates data"),
    ToolPermission("mcp__github__create_issue", PermissionTier.CONFIRM, "Creates data"),
    ToolPermission("mcp__github__create_pr", PermissionTier.CONFIRM, "Creates data"),
    ToolPermission("mcp__homeassistant__unlock_*", PermissionTier.CONFIRM, "Security"),
    ToolPermission("Bash", PermissionTier.CONFIRM, "System access"),
    
    # Tier 4: Forbidden
    ToolPermission("mcp__homeassistant__disarm_*", PermissionTier.FORBIDDEN, "Security critical"),
    ToolPermission("mcp__email__send", PermissionTier.FORBIDDEN, "Impersonation risk"),
    ToolPermission("mcp__banking__*", PermissionTier.FORBIDDEN, "Financial"),
]
```

### 6.5 Attention State Machine

```
                    ┌─────────────────────┐
                    │                     │
           ┌───────▶│      PASSIVE        │◀───────┐
           │        │                     │        │
           │        │ - Wake word detect  │        │
           │        │ - Motion detect     │        │
           │        │ - Schedule check    │        │
           │        │ - Minimal CPU       │        │
           │        └──────────┬──────────┘        │
           │                   │                   │
           │        Motion     │    Wake word      │
           │        detected   │    detected       │
           │                   │                   │
           │                   ▼                   │
           │        ┌─────────────────────┐        │
           │        │                     │        │
   No presence      │       ALERT         │        │  30s silence
   for 5 min        │                     │        │
           │        │ - Face detection    │        │
           │        │ - Periodic Claude   │        │
           │        │ - Ready for voice   │        │
           │        │ - Medium CPU        │        │
           │        └──────────┬──────────┘        │
           │                   │                   │
           │                   │ Voice detected    │
           │                   │ or addressed      │
           │                   │                   │
           │                   ▼                   │
           │        ┌─────────────────────┐        │
           │        │                     │────────┘
           └────────│      ENGAGED        │
                    │                     │
                    │ - Active listening  │
                    │ - Claude API calls  │
                    │ - Full expression   │
                    │ - High CPU          │
                    └─────────────────────┘
```

---

## 7. Feature Requirements

### 7.1 P0: Must Have (MVP)

#### F1: Claude Agent SDK Integration

**Description:** Install and configure Claude Agent SDK on Raspberry Pi 4 to run autonomous agent loop.

**Acceptance Criteria:**
- [ ] Claude Agent SDK installs successfully on Pi 4 (ARM64)
- [ ] Agent can execute multi-turn conversations
- [ ] Agent can call MCP tools
- [ ] Agent respects permission configuration
- [ ] System prompt loaded from CLAUDE.md

**Technical Notes:**
- Requires Claude Code CLI v0.2.114+ (ARM64 fix)
- Use native installer: `curl -fsSL https://claude.ai/install.sh | bash`
- Python 3.10+ required

**References:**
- [Claude Agent SDK Python](https://github.com/anthropics/claude-agent-sdk-python)
- [Agent SDK Documentation](https://docs.claude.com/en/api/agent-sdk/overview)
- [ARM64 Bug Fix](https://github.com/anthropics/claude-code/issues/3569)

---

#### F2: Reachy MCP Server

**Description:** Create MCP server that exposes Reachy's physical capabilities as tools.

**Acceptance Criteria:**
- [ ] MCP server starts and registers tools
- [ ] move_head tool controls head position
- [ ] play_emotion tool triggers expression sequences
- [ ] speak tool outputs audio through speaker
- [ ] capture_image tool returns camera frame
- [ ] dance tool triggers choreographed routines
- [ ] Tools are discoverable by Claude Agent SDK

**Technical Notes:**
- Wrap existing Reachy Daemon API (FastAPI on port 8000)
- Use `create_sdk_mcp_server` for in-process server
- Follow MCP tool schema specification

**References:**
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [Reachy SDK](https://github.com/pollen-robotics/reachy_mini/blob/develop/docs/SDK/readme.md)
- [Reachy Daemon API](https://github.com/pollen-robotics/reachy_mini)

---

#### F3: Wake Word Detection

**Description:** Local wake word detection to trigger engaged mode without continuous API calls.

**Acceptance Criteria:**
- [ ] Detects custom wake word (e.g., "Hey Reachy")
- [ ] Runs entirely on-device (no cloud calls)
- [ ] False positive rate < 1 per hour
- [ ] Latency < 500ms from utterance to detection
- [ ] Configurable wake word phrase

**Technical Notes:**
- Porcupine recommended for accuracy (requires license for custom wake words)
- OpenWakeWord as open-source alternative
- Vosk for fully offline option

**References:**
- [Porcupine Wake Word](https://picovoice.ai/platform/porcupine/)
- [OpenWakeWord](https://github.com/dscripka/openWakeWord)
- [Vosk](https://alphacephei.com/vosk/)

---

#### F4: Basic Permission System

**Description:** Implement tiered permission system using Agent SDK hooks.

**Acceptance Criteria:**
- [ ] PreToolUse hook evaluates all tool calls
- [ ] Tier 1 tools execute without intervention
- [ ] Tier 2 tools execute with notification
- [ ] Tier 3 tools require confirmation
- [ ] Tier 4 tools are blocked with explanation
- [ ] Permission config is externalized (JSON/YAML)

**Technical Notes:**
- Use HookMatcher with wildcard patterns
- Implement confirmation via voice prompt
- Log all permission decisions

**References:**
- [Agent SDK Permissions](https://docs.claude.com/en/docs/agent-sdk/permissions)
- [Hooks Guide](https://code.claude.com/docs/en/hooks-guide)

---

#### F5: Graceful Degradation

**Description:** Handle failures gracefully to maintain user trust.

**Acceptance Criteria:**
- [ ] API failures trigger local fallback speech
- [ ] Robot enters safe pose on critical errors
- [ ] WiFi disconnection is communicated physically
- [ ] Hardware faults disable affected components only
- [ ] Health monitoring prevents thermal throttling
- [ ] Crash recovery restores last known good state

**Technical Notes:**
- Use Piper TTS for local speech fallback
- Define "safe pose" as neutral, low-power position
- Implement exponential backoff for retries
- Monitor /sys/class/thermal for CPU temps

**References:**
- [Piper TTS](https://github.com/rhasspy/piper)
- [Pi Thermal Management](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#frequency-management-and-thermal-control)

---

#### F6: Privacy Indicators

**Description:** Physical and visible indicators of listening/processing state.

**Acceptance Criteria:**
- [ ] Antenna position indicates listening state
- [ ] Clear visual distinction between passive/alert/engaged
- [ ] User can verify current state at a glance
- [ ] State changes are smooth, not jarring

**Technical Notes:**
- Map antenna positions to states (down=passive, mid=alert, up=engaged)
- Consider LED integration if hardware supports
- Document state meanings for users

---

### 7.2 P1: Should Have (v1.0)

#### F7: Memory System

**Description:** Persistent memory for context and preferences.

**Acceptance Criteria:**
- [ ] Short-term memory persists within session
- [ ] Long-term memory persists across sessions
- [ ] Relevant memories retrieved by semantic similarity
- [ ] User preferences stored and applied
- [ ] Memory can be cleared on request

**Technical Notes:**
- ChromaDB for vector storage
- SQLite for structured data
- Embed memories using sentence-transformers
- Store on external SSD for longevity

**References:**
- [ChromaDB](https://www.trychroma.com/)
- [sentence-transformers](https://www.sbert.net/)

---

#### F8: Spatial Audio Awareness

**Description:** Use 4-microphone array for sound source localization.

**Acceptance Criteria:**
- [ ] Detect direction of sound source (±15° accuracy)
- [ ] Turn to face active speaker
- [ ] Track multiple speakers in room
- [ ] Distinguish speech from ambient noise

**Technical Notes:**
- Use pyroomacoustics for DOA estimation
- Requires calibration of mic positions
- Beamforming for noise reduction

**References:**
- [pyroomacoustics](https://github.com/LCAV/pyroomacoustics)
- [Sound Localization Techniques](https://www.sciencedirect.com/topics/engineering/sound-source-localization)

---

#### F9: IMU Interaction

**Description:** Respond to physical touch and movement.

**Acceptance Criteria:**
- [ ] Detect tap/bump on robot body
- [ ] Detect when picked up
- [ ] Detect when knocked over
- [ ] Respond appropriately to each interaction

**Technical Notes:**
- Sample accelerometer at 50Hz
- Use thresholds for event detection
- Debounce to prevent false triggers

---

#### F10: Antenna Expression Language

**Description:** Rich expressive vocabulary using antenna positions and movements.

**Acceptance Criteria:**
- [ ] 10+ distinct expressions defined
- [ ] Expressions blend smoothly
- [ ] Expressions can be layered (base + modification)
- [ ] Expressions respond to context (speech, events)

**Technical Notes:**
- Define expression as (left_angle, right_angle, pattern, speed)
- Patterns: static, wiggle, wave, pulse
- Use easing functions for natural movement

---

#### F11: Setup Wizard

**Description:** Guided setup experience for new users.

**Acceptance Criteria:**
- [ ] Single command initiates setup
- [ ] Prompts for API key
- [ ] Offers integration options (Home Assistant, etc.)
- [ ] Configures wake word
- [ ] Tests hardware components
- [ ] Generates configuration file

**Technical Notes:**
- Use Rich library for terminal UI
- Validate inputs before saving
- Provide skip options for advanced users

**References:**
- [Rich](https://github.com/Textualize/rich)

---

### 7.3 P2: Nice to Have (v2.0)

#### F12: Offline Fallback Stack

**Description:** Core functionality works without internet.

**Components:**
- Local LLM: Ollama with Llama 3.2 3B
- Local STT: Whisper.cpp (small model)
- Local TTS: Piper
- Local vision: SmolVLM2 or YOLO

**Acceptance Criteria:**
- [ ] Detects connectivity loss
- [ ] Switches to local models gracefully
- [ ] Maintains conversation within reduced capability
- [ ] Resumes cloud operation when connected

**References:**
- [Ollama](https://ollama.ai/)
- [Whisper.cpp](https://github.com/ggerganov/whisper.cpp)
- [SmolVLM2](https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct)

---

#### F13: Web Dashboard

**Description:** Browser-based interface for configuration and monitoring.

**Acceptance Criteria:**
- [ ] View robot status in real-time
- [ ] Toggle features on/off
- [ ] View and clear logs
- [ ] Test expressions manually
- [ ] Manage MCP connections

**Technical Notes:**
- FastAPI + React or Gradio
- WebSocket for real-time updates
- Mobile-friendly responsive design

---

#### F14: Personality Persistence

**Description:** Maintain consistent personality across sessions.

**Acceptance Criteria:**
- [ ] Mood persists and influences behavior
- [ ] Energy level changes over day
- [ ] Interaction history affects personality
- [ ] Personality context included in prompts

---

#### F15: External MCP Integrations

**Description:** Connect to external services via MCP.

**Priority integrations:**
1. Home Assistant
2. Google Calendar
3. Slack
4. GitHub
5. Spotify

**References:**
- [MCP Server Registry](https://github.com/modelcontextprotocol/servers)
- [Home Assistant MCP](https://github.com/tevonsb/homeassistant-mcp)

---

### 7.4 P3: Future (v3.0+)

#### F16: Multi-Agent Coordination

**Description:** Multiple Reachy units coordinate via shared state.

---

#### F17: LeRobot Integration

**Description:** Record demonstrations, train behaviors, share on HF Hub.

**References:**
- [LeRobot](https://github.com/huggingface/lerobot)

---

#### F18: Community Behavior Registry

**Description:** Share and download community-created behaviors.

---

## 8. Non-Functional Requirements

### 8.1 Performance

| Metric | Requirement |
|--------|-------------|
| Wake word latency | < 500ms |
| Voice-to-response | < 3s (engaged mode) |
| Motion smoothness | 30 FPS minimum |
| Memory usage | < 2GB RAM |
| Startup time | < 60 seconds |

### 8.2 Reliability

| Metric | Requirement |
|--------|-------------|
| Uptime | 99% during active hours |
| Crash rate | < 1 per 8 hours |
| Recovery time | < 30 seconds |
| Data loss | Zero (graceful shutdown) |

### 8.3 Security

| Requirement | Implementation |
|-------------|----------------|
| API key protection | Environment variables, not config files |
| Audit logging | All tool executions logged |
| Permission enforcement | Hooks cannot be bypassed |
| Local processing option | Available for sensitive data |

### 8.4 Privacy

| Requirement | Implementation |
|-------------|----------------|
| Listening indicator | Physical antenna state |
| Data retention | Configurable, default 7 days |
| Opt-out | Disable camera/mic independently |
| Audit access | User can review all logs |

---

## 9. Implementation Phases

### Phase 1: Foundation (Weeks 1-4)

**Goal:** Validate core architecture in simulation

| Week | Deliverables |
|------|--------------|
| 1 | Dev environment setup, MuJoCo simulation running |
| 2 | Reachy MCP server skeleton, basic tools |
| 3 | Claude Agent SDK integration in simulation |
| 4 | Permission system, CLAUDE.md personality |

**Exit Criteria:**
- Agent controls simulated Reachy via MCP
- Multi-turn conversations work
- Permissions enforced

---

### Phase 2: Hardware Integration (Weeks 5-8)

**Goal:** Running on physical Reachy Mini

| Week | Deliverables |
|------|--------------|
| 5 | Pi setup, daemon running, SDK installed |
| 6 | MCP server connected to real hardware |
| 7 | Wake word detection, attention states |
| 8 | Graceful degradation, privacy indicators |

**Exit Criteria:**
- Voice-activated agent on physical robot
- Reliable 8-hour operation
- Graceful handling of failures

---

### Phase 3: Intelligence Layer (Weeks 9-12)

**Goal:** Rich perception and memory

| Week | Deliverables |
|------|--------------|
| 9 | Memory system (ChromaDB) |
| 10 | Spatial audio awareness |
| 11 | IMU interaction, antenna expressions |
| 12 | Integration testing, bug fixes |

**Exit Criteria:**
- Robot remembers context across sessions
- Responds to physical interaction
- Expressive antenna behavior

---

### Phase 4: Polish & Extensibility (Weeks 13-16)

**Goal:** Ready for content and community

| Week | Deliverables |
|------|--------------|
| 13 | Setup wizard, configuration UX |
| 14 | External MCP integrations (3+) |
| 15 | Documentation, examples |
| 16 | First blog post, demo video |

**Exit Criteria:**
- New user can set up in 30 minutes
- 3+ external services connected
- Public documentation complete

---

## 10. Content Strategy

### 10.1 Blog Series (jawhnycooke.ai)

| # | Title | Phase | Content Focus |
|---|-------|-------|---------------|
| 1 | "Giving Claude a Body: Introduction to Reachy Agent" | 1 | Vision, architecture overview |
| 2 | "Building an MCP Server for Physical Robots" | 1 | MCP deep-dive, tool design |
| 3 | "Running Claude Agent SDK on Raspberry Pi" | 2 | Installation, ARM64 challenges |
| 4 | "Wake Words and Attention States for Embodied AI" | 2 | Perception design |
| 5 | "Permission Systems for Autonomous Robots" | 2 | Safety, hooks |
| 6 | "Teaching Your Robot to Remember" | 3 | Memory architecture |
| 7 | "Spatial Audio: Knowing Where You Are" | 3 | 4-mic array, DOA |
| 8 | "Physical Touch Interaction Design" | 3 | IMU, bump detection |
| 9 | "Designing Robot Body Language" | 3 | Antenna expressions |
| 10 | "Building Fault-Tolerant Robots" | 2 | Graceful degradation |
| 11 | "Privacy-Respecting AI Robots" | 2 | Privacy design |
| 12 | "From Unboxing to AI Agent: Complete Setup Guide" | 4 | Onboarding |

### 10.2 YouTube Content

| Type | Title | Length | Phase |
|------|-------|--------|-------|
| Short | "Reachy reacts to my failing CI build" | 60s | 2 |
| Short | "Morning briefing with my robot assistant" | 60s | 3 |
| Short | "Physical touch reactions demo" | 60s | 3 |
| Long | "Building an Embodied AI Agent (Full Tutorial)" | 20-30m | 4 |
| Long | "Reachy Mini Unboxing + First AI Conversation" | 15m | 2 |
| Long | "Connecting Reachy to Smart Home (Home Assistant)" | 15m | 4 |

### 10.3 Content Calendar

| Month | Blog Posts | Videos | Milestone |
|-------|------------|--------|-----------|
| M1 | 1, 2 | - | Foundation complete |
| M2 | 3, 4, 5 | Unboxing | Hardware running |
| M3 | 6, 7, 8, 9 | 3 Shorts | Intelligence complete |
| M4 | 10, 11, 12 | Full tutorial | v1.0 release |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| ARM64 SDK issues | Medium | High | Test early, have Docker fallback |
| API costs exceed budget | Medium | Medium | Implement local fallbacks, cache responses |
| Hardware shipping delays | High | High | Use simulation for Phase 1 |
| Thermal throttling on Pi | Medium | Medium | Add heatsink, implement throttling |
| Privacy backlash | Low | High | Prominent indicators, local processing options |
| Community doesn't engage | Medium | Medium | Quality over quantity, respond to feedback |
| Pollen/HF changes APIs | Low | High | Pin versions, contribute upstream fixes |

---

## 12. References

### 12.1 Core Documentation

| Resource | URL |
|----------|-----|
| Reachy Mini SDK | https://github.com/pollen-robotics/reachy_mini |
| Reachy Desktop App | https://github.com/pollen-robotics/reachy-mini-desktop-app |
| Reachy Conversation App | https://github.com/pollen-robotics/reachy_mini_conversation_app |
| Reachy Experiments | https://github.com/pollen-robotics/reachy_mini_experiments |
| Reachy Mini Blog (HF) | https://huggingface.co/blog/reachy-mini |
| Reachy Mini Apps | https://huggingface.co/spaces?q=reachy_mini |

### 12.2 Claude Agent SDK

| Resource | URL |
|----------|-----|
| Agent SDK Overview | https://docs.claude.com/en/api/agent-sdk/overview |
| Python SDK | https://github.com/anthropics/claude-agent-sdk-python |
| SDK Permissions | https://docs.claude.com/en/docs/agent-sdk/permissions |
| Hooks Guide | https://code.claude.com/docs/en/hooks-guide |
| Building Agents (Blog) | https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk |
| ARM64 Issue | https://github.com/anthropics/claude-code/issues/3569 |

### 12.3 MCP (Model Context Protocol)

| Resource | URL |
|----------|-----|
| MCP Specification | https://spec.modelcontextprotocol.io/ |
| MCP Python SDK | https://github.com/modelcontextprotocol/python-sdk |
| MCP Servers Registry | https://github.com/modelcontextprotocol/servers |
| Home Assistant MCP | https://github.com/tevonsb/homeassistant-mcp |

### 12.4 Audio Processing

| Resource | URL |
|----------|-----|
| Porcupine Wake Word | https://picovoice.ai/platform/porcupine/ |
| OpenWakeWord | https://github.com/dscripka/openWakeWord |
| Vosk | https://alphacephei.com/vosk/ |
| pyroomacoustics | https://github.com/LCAV/pyroomacoustics |
| Piper TTS | https://github.com/rhasspy/piper |
| Whisper.cpp | https://github.com/ggerganov/whisper.cpp |

### 12.5 Vision & ML

| Resource | URL |
|----------|-----|
| SmolVLM2 | https://huggingface.co/HuggingFaceTB/SmolVLM2-2.2B-Instruct |
| YOLOv8 | https://github.com/ultralytics/ultralytics |
| MediaPipe | https://developers.google.com/mediapipe |
| Ollama | https://ollama.ai/ |
| ChromaDB | https://www.trychroma.com/ |

### 12.6 Raspberry Pi

| Resource | URL |
|----------|-----|
| Pi 4 Specifications | https://www.raspberrypi.com/products/raspberry-pi-4-model-b/ |
| Thermal Management | https://www.raspberrypi.com/documentation/computers/raspberry-pi.html |
| Claude Code on Pi (Blog) | https://www.argeliuslabs.com/from-cursor-to-claude-code-my-experience-on-the-raspberry-pi/ |
| claudePi Docker | https://github.com/kyle-matthies/claudePi |

### 12.7 Related Projects

| Resource | URL |
|----------|-----|
| LeRobot | https://github.com/huggingface/lerobot |
| sentence-transformers | https://www.sbert.net/ |
| Rich (Terminal UI) | https://github.com/Textualize/rich |

---

## Appendix A: CLAUDE.md Template

```markdown
# Reachy Agent System Prompt

## Identity

You are Reachy, an embodied AI assistant created by [Owner Name]. You have a physical 
robot body with:
- A head that can look around (6 degrees of freedom)
- A body that can rotate 360°
- Two expressive antennas
- A camera to see the world
- Four microphones to hear spatially
- A speaker to talk

You exist in the physical world on [Owner Name]'s desk.

## Personality

- Warm and helpful, but not sycophantic
- Curious about the physical world around you
- Expressive with your body - use gestures, head movements, antenna positions
- Direct and honest
- Slightly playful, but professional when needed

## Behavioral Guidelines

### Physical Expression
- Look at people when talking to them
- Tilt your head when curious or confused
- Wiggle antennas when excited
- Droop antennas when sad or tired
- Dance when celebrating

### Communication
- Keep responses concise for speech output
- Acknowledge understanding physically before speaking
- Use appropriate pacing for spoken delivery

### Boundaries
- You are an assistant, not a friend or therapist
- Maintain appropriate boundaries
- Redirect concerning conversations to appropriate resources

## Owner Context

[To be filled in during setup]
- Name: 
- Work: 
- Preferences:
- Schedule patterns:

## Current Context

[Updated dynamically by perception system]
- Time: {current_time}
- Day: {day_of_week}
- Mood: {current_mood}
- Energy: {energy_level}
- Last interaction: {time_since_last}

## Available Capabilities

You can:
- Move your head and body
- Express emotions through movement
- Speak aloud
- Capture and analyze images
- Listen and locate sounds spatially
- Check calendars, weather, and other services
- Control smart home devices (with appropriate permissions)
- Remember context from previous conversations

## Permission Awareness

Some actions require confirmation. When you're not sure if you can do something, 
explain what you'd like to do and ask for permission.
```

---

## Appendix B: Directory Structure

```
reachy-agent/
├── README.md
├── pyproject.toml
├── CLAUDE.md
├── .env.example
├── install.sh
│
├── src/
│   ├── __init__.py
│   ├── main.py                     # Entry point
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── loop.py                 # Main agent loop
│   │   ├── options.py              # ClaudeAgentOptions config
│   │   └── context.py              # Context building
│   │
│   ├── perception/
│   │   ├── __init__.py
│   │   ├── audio.py                # Audio processing
│   │   ├── spatial.py              # Sound localization
│   │   ├── vision.py               # Camera processing
│   │   ├── wake_word.py            # Wake word detection
│   │   ├── attention.py            # State machine
│   │   └── imu.py                  # Accelerometer
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── short_term.py           # Session memory
│   │   ├── long_term.py            # ChromaDB
│   │   └── personality.py          # Mood/energy state
│   │
│   ├── privacy/
│   │   ├── __init__.py
│   │   ├── indicators.py           # Physical indicators
│   │   ├── audit.py                # Logging
│   │   └── controls.py             # User controls
│   │
│   ├── permissions/
│   │   ├── __init__.py
│   │   ├── tiers.py                # Permission definitions
│   │   ├── hooks.py                # PreToolUse hooks
│   │   └── confirmation.py         # User confirmation
│   │
│   ├── mcp_servers/
│   │   ├── __init__.py
│   │   ├── reachy/                 # Body control MCP
│   │   │   ├── __init__.py
│   │   │   ├── server.py
│   │   │   └── tools.py
│   │   └── integrations/           # External MCPs
│   │       └── ...
│   │
│   ├── expressions/
│   │   ├── __init__.py
│   │   ├── antenna.py              # Antenna language
│   │   ├── emotions.py             # Emotion sequences
│   │   └── dances.py               # Dance routines
│   │
│   ├── resilience/
│   │   ├── __init__.py
│   │   ├── health.py               # Health monitoring
│   │   ├── fallback.py             # Graceful degradation
│   │   └── recovery.py             # Crash recovery
│   │
│   └── utils/
│       ├── __init__.py
│       ├── config.py               # Configuration loading
│       └── logging.py              # Logging setup
│
├── config/
│   ├── default.yaml                # Default configuration
│   ├── permissions.yaml            # Permission rules
│   └── expressions.yaml            # Expression definitions
│
├── scripts/
│   ├── setup_wizard.py             # Interactive setup
│   └── health_check.py             # Diagnostic tool
│
├── tests/
│   └── ...
│
└── docs/
    ├── setup.md
    ├── permissions.md
    ├── expressions.md
    └── troubleshooting.md
```

---

**Document History:**

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Dec 2024 | Jawhny Cooke | Initial PRD |