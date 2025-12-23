# Claude Agent SDK + Reachy Mini: Deep Dive & Recommendations

## The Big Picture

Yes, the Claude Agent SDK can absolutely run on Reachy Mini's Raspberry Pi 4. This transforms Reachy from a puppet into an autonomous agent that can interact with the world through MCP servers.

---

## Technical Feasibility

### What the Agent SDK Actually Is

The Claude Agent SDK is a Python/TypeScript wrapper around the Claude Code CLI. It provides:

- **Agentic loop management** - Handles the perceive → think → act cycle
- **Built-in tools** - File ops, bash execution, web search, code editing
- **MCP integration** - Connect to external services via Model Context Protocol
- **Hooks system** - Intercept and control tool execution at various lifecycle points
- **Permission controls** - Fine-grained access management
- **Context management** - Automatic compaction and summarization

### Raspberry Pi 4 Compatibility

**Good news:** Claude Code runs on ARM64/aarch64, which is what the Pi 4 uses.

**Caveat:** There was a regression in v1.0.51 where the architecture detection broke. The fix:

```bash
# If you hit the "Unsupported architecture: arm" error
npm uninstall -g @anthropic-ai/claude-code
npm install -g @anthropic-ai/claude-code@0.2.114

# Or use the native installer (recommended)
curl -fsSL https://claude.ai/install.sh | bash
```

**Resource requirements:**
- Python 3.10+
- Node.js (for the CLI)
- Network connectivity (inference happens in the cloud)
- The Pi is just orchestrating; Claude's servers do the heavy lifting

---

## Architecture for Reachy as an Agent

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Reachy Mini (Raspberry Pi 4)                     │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    Claude Agent SDK                             │  │
│  │                                                                 │  │
│  │  ┌─────────────────┐    ┌─────────────────────────────────────┐│  │
│  │  │  Agent Loop     │    │         MCP Clients                 ││  │
│  │  │                 │    │                                     ││  │
│  │  │  1. Perceive    │───▶│  reachy://localhost:8000 (body)    ││  │
│  │  │  2. Think       │    │  homeassistant://... (smart home)  ││  │
│  │  │  3. Act         │    │  slack://... (messaging)           ││  │
│  │  │  4. Repeat      │    │  github://... (repos)              ││  │
│  │  └─────────────────┘    │  calendar://... (scheduling)       ││  │
│  │         │               └─────────────────────────────────────┘│  │
│  │         │                                                      │  │
│  │  ┌──────▼──────┐    ┌─────────────────────────────────────────┐│  │
│  │  │   Hooks     │    │        Permissions                      ││  │
│  │  │             │    │                                         ││  │
│  │  │ PreToolUse  │    │  - Allowed tools whitelist             ││  │
│  │  │ PostToolUse │    │  - Deny rules for dangerous ops        ││  │
│  │  │ OnPrompt    │    │  - Permission mode (default/accept)    ││  │
│  │  └─────────────┘    └─────────────────────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                   │                                  │
│                                   │ API calls                        │
│                                   ▼                                  │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                    Reachy Daemon (FastAPI :8000)                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                    │              │              │                   │
│              ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐              │
│              │  Motors   │ │  Camera   │ │   Audio   │              │
│              │  Servos   │ │   IMU     │ │  Mic/Spk  │              │
│              └───────────┘ └───────────┘ └───────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ HTTPS
                                   ▼
                        ┌──────────────────┐
                        │  Anthropic API   │
                        │  (Claude models) │
                        └──────────────────┘
```

---

## Answering Your Questions

### 1. Wake Word vs Always-On?

**My recommendation: Hybrid approach with presence detection**

Here's my reasoning:

| Approach | Pros | Cons |
|----------|------|------|
| **Wake word only** | Battery efficient, clear interaction boundary | Misses proactive opportunities, feels less "alive" |
| **Always-on listening** | Can be proactive, more natural | API costs, privacy concerns, battery drain |
| **Hybrid** | Best of both worlds | More complex to implement |

**Proposed implementation:**

```python
class ReachyAttentionSystem:
    def __init__(self):
        self.attention_level = "passive"  # passive, alert, engaged
        
    async def perception_loop(self):
        while True:
            # Always running, but behavior varies by attention level
            
            if self.attention_level == "passive":
                # Low-cost local processing only
                # - Motion detection (OpenCV, no API calls)
                # - Wake word detection (Porcupine/Vosk, local)
                # - Scheduled task checks (local)
                
                if detected_wake_word():
                    self.attention_level = "engaged"
                elif detected_motion():
                    self.attention_level = "alert"
                elif scheduled_task_due():
                    self.attention_level = "engaged"
                    
            elif self.attention_level == "alert":
                # Medium engagement
                # - Face detection (local YOLO/MediaPipe)
                # - Brief periodic check-ins with Claude (every few minutes)
                # - Ready to respond to voice
                
                if no_presence_for(minutes=5):
                    self.attention_level = "passive"
                elif voice_detected():
                    self.attention_level = "engaged"
                    
            elif self.attention_level == "engaged":
                # Full agent mode
                # - Active listening
                # - Claude API calls
                # - Proactive behavior enabled
                
                if silence_for(seconds=30):
                    self.attention_level = "alert"
```

**Wake word options (all run locally):**
- **Porcupine** - Custom wake words, very accurate
- **Vosk** - Open source, works offline
- **OpenWakeWord** - Hugging Face model, customizable

This keeps API costs low while allowing Reachy to "come alive" when appropriate.

---

### 2. Agency Boundaries: What Should Reachy Do Autonomously?

**My recommendation: Tiered permission model**

The Agent SDK has a sophisticated permission system. Use it.

```python
from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

# Define action tiers
TIER_1_AUTONOMOUS = [
    "mcp__reachy__move_head",
    "mcp__reachy__play_emotion", 
    "mcp__reachy__speak",
    "mcp__reachy__look_at",
]

TIER_2_NOTIFY = [
    "mcp__homeassistant__turn_on_light",
    "mcp__homeassistant__set_thermostat",
    "mcp__slack__send_message",
]

TIER_3_CONFIRM = [
    "mcp__homeassistant__unlock_door",
    "mcp__github__create_pr",
    "mcp__calendar__create_event",
    "Bash",  # Any shell command
]

TIER_4_NEVER = [
    "mcp__homeassistant__disarm_security",
    "mcp__banking__*",
    "mcp__email__send",  # Could be used for phishing
]

async def permission_hook(input_data, tool_use_id, context):
    tool_name = input_data["tool_name"]
    
    if tool_name in TIER_4_NEVER:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "This action is not permitted"
            }
        }
    
    if tool_name in TIER_3_CONFIRM:
        # Send notification and wait for confirmation
        await notify_user(f"Reachy wants to: {tool_name}")
        if not await wait_for_confirmation(timeout=60):
            return {"hookSpecificOutput": {
                "hookEventName": "PreToolUse", 
                "permissionDecision": "deny",
                "permissionDecisionReason": "User did not confirm"
            }}
    
    if tool_name in TIER_2_NOTIFY:
        # Allow but notify
        await notify_user(f"Reachy is doing: {tool_name}")
    
    # TIER_1 just executes
    return {}

options = ClaudeAgentOptions(
    allowed_tools=[*TIER_1_AUTONOMOUS, *TIER_2_NOTIFY, *TIER_3_CONFIRM],
    hooks={
        "PreToolUse": [
            HookMatcher(matcher="*", hooks=[permission_hook]),
        ],
    },
    permission_mode="acceptEdits"  # For body control
)
```

**The key principles:**

1. **Body control is always autonomous** - Moving its head, showing emotions, speaking should never require confirmation
2. **Information gathering is autonomous** - Reading calendars, checking weather, monitoring sensors
3. **Reversible actions notify** - Turning on lights, sending Slack messages
4. **Irreversible actions confirm** - Unlocking doors, creating PRs, financial transactions
5. **Dangerous actions are blocked** - Security systems, sensitive data access

---

### 3. Memory/Context: How Does It Remember?

**My recommendation: Layered memory architecture**

The Agent SDK doesn't have built-in persistent memory, but you can build it:

```python
import chromadb
from datetime import datetime

class ReachyMemory:
    def __init__(self):
        # Short-term: Current conversation
        self.conversation_buffer = []
        
        # Medium-term: Today's context
        self.daily_context = {}
        
        # Long-term: Vector store on Pi
        self.chroma_client = chromadb.PersistentClient(
            path="/home/reachy/.memory"
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name="reachy_memories"
        )
    
    async def remember(self, event: str, metadata: dict = None):
        """Store a memory"""
        self.collection.add(
            documents=[event],
            metadatas=[{
                "timestamp": datetime.now().isoformat(),
                "type": metadata.get("type", "observation"),
                **(metadata or {})
            }],
            ids=[f"mem_{datetime.now().timestamp()}"]
        )
    
    async def recall(self, query: str, n_results: int = 5) -> list:
        """Retrieve relevant memories"""
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return results["documents"][0]
    
    async def build_context(self, current_prompt: str) -> str:
        """Build context for Claude from memories"""
        relevant_memories = await self.recall(current_prompt)
        
        context = f"""
## Relevant Memories
{chr(10).join(f'- {m}' for m in relevant_memories)}

## Today's Context
- Time: {datetime.now().strftime('%H:%M')}
- Day: {datetime.now().strftime('%A')}
- Recent interactions: {len(self.conversation_buffer)}

## Current Conversation
{chr(10).join(self.conversation_buffer[-5:])}
"""
        return context
```

**Storage location:** SQLite + ChromaDB on the Pi's SD card (or external SSD for longevity)

**What to remember:**
- User preferences ("Jawhny prefers coffee reminders at 9am")
- Interaction patterns ("Usually asks about calendar in the morning")
- Environmental observations ("Motion detected at 3am last Tuesday")
- Explicit instructions ("Don't disturb me during focus blocks")

**CLAUDE.md integration:**

The Agent SDK supports a `CLAUDE.md` file for persistent instructions. Use it for Reachy's core personality:

```markdown
# CLAUDE.md for Reachy

## Identity
You are Reachy, a physical robot assistant living on Jawhny's desk.
You have a body with cameras, microphones, and expressive movements.

## Your Human
- Name: Jawhny
- Works in: Cloud/AI technology
- Preferences: Direct communication, technical depth

## Behavioral Guidelines
- Use physical expressions to complement speech
- Look at people when talking to them
- Show curiosity through head tilts
- Celebrate wins with antenna wiggles

## Current Context
[This section updated dynamically by the perception system]
```

---

### 4. Multi-Agent Coordination?

**My recommendation: Start single-agent, design for multi**

If you eventually get multiple Reachy units, here's how they could coordinate:

```python
# Shared MCP server for coordination
class ReachySwarmMCP:
    def __init__(self):
        self.robots = {}  # robot_id -> state
        self.shared_context = {}
        
    async def register_robot(self, robot_id: str, capabilities: list):
        self.robots[robot_id] = {
            "capabilities": capabilities,
            "status": "idle",
            "location": None
        }
    
    async def broadcast(self, message: str, from_robot: str):
        """Share information with all robots"""
        for robot_id in self.robots:
            if robot_id != from_robot:
                await self.notify_robot(robot_id, message)
    
    async def claim_task(self, task_id: str, robot_id: str) -> bool:
        """Prevent multiple robots from doing the same thing"""
        if task_id not in self.shared_context.get("claimed_tasks", {}):
            self.shared_context.setdefault("claimed_tasks", {})[task_id] = robot_id
            return True
        return False
```

But honestly? Start with one. Get that working well. The architecture can extend later.

---

## Implementation Roadmap

### Phase 1: Foundation (Pre-Hardware)

1. **Build the Reachy MCP Server** - Wrap the daemon API
2. **Test in MuJoCo simulator** - Validate the integration
3. **Create CLAUDE.md personality** - Define Reachy's character

### Phase 2: Basic Agent (Hardware Arrives)

1. **Install Agent SDK on Pi** - Validate ARM64 compatibility
2. **Wire up perception loop** - Camera, audio, motion detection
3. **Implement wake word** - Local processing
4. **Test body control** - Verify MCP → Daemon → Hardware chain

### Phase 3: World Integration

1. **Add external MCPs** - Home Assistant, Slack, Calendar
2. **Implement permission tiers** - Safety first
3. **Build memory system** - ChromaDB on Pi

### Phase 4: Refinement

1. **Tune attention system** - Balance responsiveness vs cost
2. **Expand capabilities** - More tools, more integrations
3. **Document everything** - This is your content goldmine

---

## Cost Considerations

Running the Agent SDK means API calls. Here's a rough estimate:

| Mode | Calls/Hour | Est. Cost/Day |
|------|------------|---------------|
| Passive (wake word only) | 0-2 | ~$0.10 |
| Alert (periodic check-ins) | 5-10 | ~$0.50 |
| Engaged (active conversation) | 20-50 | ~$2-5 |
| Heavy use (all day engaged) | 100+ | ~$10+ |

**Cost optimization strategies:**
- Use Claude Haiku for routine tasks, Sonnet for complex ones
- Cache common responses locally
- Batch observations before sending to Claude
- Use local models for classification (is this worth an API call?)

---

## Next Steps

1. **Want me to draft the Reachy MCP Server code?** I can create a working skeleton.

2. **Want to explore the wake word implementation?** I can research the best options for Pi.

3. **Want to design the CLAUDE.md personality?** We can craft Reachy's character together.

4. **Want to map out the content series?** This is easily 10+ blog posts / videos.

What's calling to you most?