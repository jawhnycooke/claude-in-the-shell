# Daemon Compatibility & Coexistence

This document explains how Claude in the Shell interacts with the Reachy Mini daemon and coexists with other Reachy applications.

## Daemon Architecture

The Reachy Mini daemon (provided by Pollen Robotics) exposes **two communication protocols**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Reachy Mini Daemon                            │
│                                                                  │
│  ┌────────────────────┐     ┌────────────────────────────────┐  │
│  │   FastAPI REST     │     │      Zenoh Pub/Sub             │  │
│  │   (HTTP :8000)     │     │   (Real-time messaging)        │  │
│  │                    │     │                                │  │
│  │  • Request/Response│     │  • 100Hz control loop          │  │
│  │  • Tool commands   │     │  • Streaming sensor data       │  │
│  │  • Status queries  │     │  • Low-latency motion          │  │
│  └────────────────────┘     └────────────────────────────────┘  │
│            │                           │                         │
│            └───────────────┬───────────┘                         │
│                           │                                      │
│                  ┌────────────────┐                              │
│                  │  Hardware HAL  │                              │
│                  │  (Motors, IMU, │                              │
│                  │   Camera, Mic) │                              │
│                  └────────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

## Protocol Comparison

| Aspect | HTTP REST | Zenoh |
|--------|-----------|-------|
| **Port** | `:8000` | Default Zenoh ports |
| **Latency** | ~10-50ms | ~1-5ms |
| **Pattern** | Request/Response | Publish/Subscribe |
| **Use Case** | Command-driven control | Real-time streaming |
| **Connection** | Per-request | Persistent session |

## How Each App Uses the Daemon

### Claude in the Shell (HTTP REST)

```python
# Our ReachyDaemonClient uses HTTP
class ReachyDaemonClient:
    def __init__(self, base_url="http://localhost:8000"):
        self._client = httpx.AsyncClient(base_url=base_url)

    async def move_head(self, direction: str):
        return await self._request("POST", "/api/move/goto", ...)
```

**Why HTTP works well for us:**
- MCP tools are naturally request/response
- Claude thinks, then acts (not continuous control)
- Simpler async integration with Claude SDK
- No dependency on Zenoh library

### Conversation App (Zenoh)

```python
# Conversation App uses ReachyMini class with Zenoh
from reachy_mini import ReachyMini

robot = ReachyMini()  # Connects via Zenoh
robot.set_target(head=head_pose)  # 100Hz updates
```

**Why Zenoh works well for them:**
- Real-time audio streaming requires low latency
- Continuous head tracking during conversation
- Primary/secondary motion blending at 100Hz

### Dashboard (Zenoh)

The Pollen dashboard also uses Zenoh for:
- Real-time status monitoring
- App lifecycle management
- Live camera preview

## Coexistence Scenarios

### Scenario 1: Claude in the Shell + Dashboard ✅

Both can run simultaneously:

```
Dashboard (Zenoh) ─────┐
                       ├──► Daemon ──► Robot
Claude (HTTP REST) ────┘
```

The daemon handles concurrent access gracefully. Motion commands from either source are queued.

### Scenario 2: Claude in the Shell + Conversation App ⚠️

May conflict if both try to control the robot:

```
Conversation App (Zenoh) ───┐
                            ├──► Daemon ──► Robot (conflicts!)
Claude (HTTP REST) ─────────┘
```

**Recommendation:** Run one at a time, or designate one as "primary controller".

### Scenario 3: Multiple Claude Instances ❌

Not recommended - permission states may conflict:

```
Claude Instance 1 ───┐
                     ├──► Daemon (race conditions)
Claude Instance 2 ───┘
```

## Daemon API Endpoints We Use

### Movement
- `POST /api/move/goto` - Smooth interpolated movement
- `POST /api/move/play/wake_up` - Wake up sequence
- `POST /api/move/play/goto_sleep` - Sleep sequence
- `POST /api/move/play/recorded-move-dataset/{dataset}/{move}` - HuggingFace emotions

### Status
- `GET /api/daemon/status` - Daemon health and config
- `GET /api/state/full` - Robot pose and sensor state

### Kinematics
- `POST /api/kinematics/look_at_world` - Look at 3D point
- `POST /api/kinematics/look_at_pixel` - Look at camera pixel

### Motors
- `POST /api/motors/set_mode/{mode}` - Enable/disable/gravity compensation

## MovementManager Pattern (From Conversation App)

The Conversation App uses a sophisticated `MovementManager` that we could adopt for smoother motion:

```python
class MovementManager:
    """Orchestrates 100Hz motion with primary/secondary blending."""

    def __init__(self):
        self.primary_queue = []      # Sequential moves (emotions, dances)
        self.secondary_offset = {}   # Additive moves (speech sway, tracking)
        self.breathing = BreathingMove()  # Idle behavior

    def working_loop(self):
        """100Hz control loop."""
        while not self.stop_event.is_set():
            primary = self._get_current_primary()
            secondary = self._get_secondary_offsets()
            final_pose = self._compose_poses(primary, secondary)
            self.robot.set_target(head=final_pose)
            time.sleep(0.01)  # 100Hz
```

**Key concepts:**
- **Primary moves**: Mutually exclusive (emotions, dances)
- **Secondary moves**: Additive overlays (speech sway, head tracking)
- **Breathing**: Subtle idle animation when no other moves active

### Potential Enhancement for Claude in the Shell

We could add a similar pattern:

```python
# Future: Add to idle behavior controller
class IdleMotionBlender:
    """Blend MCP tool commands with continuous idle behavior."""

    async def execute_with_blend(self, tool_command):
        """Execute tool while maintaining secondary idle motion."""
        self.pause_idle()
        result = await self.daemon_client.execute(tool_command)
        self.resume_idle()
        return result
```

## Native SDK Emotions

Both apps can use the official emotion library from HuggingFace:

```python
# Dataset: pollen-robotics/reachy-mini-emotions-library
# Available moves: curious1, cheerful1, amazed1, exhausted1, etc.

# Via HTTP (our approach)
await client.play_recorded_move(
    "pollen-robotics/reachy-mini-emotions-library",
    "curious1"
)

# Via Zenoh (Conversation App approach)
robot.play_recorded_move(
    "pollen-robotics/reachy-mini-emotions-library",
    "curious1"
)
```

Both methods trigger the same pre-recorded motion capture animations.

## Future Considerations

### 1. Hybrid Approach

We could add Zenoh for specific features:

```python
# Hypothetical: Use Zenoh for real-time head tracking
# while keeping HTTP for tool commands
class HybridController:
    def __init__(self):
        self.http_client = ReachyDaemonClient()  # Tools
        self.zenoh_client = ZenohClient()        # Real-time
```

### 2. Dashboard Integration

We could register as a ReachyMiniApp for dashboard visibility:

```python
from reachy_mini import ReachyMiniApp

class ClaudeInTheShellApp(ReachyMiniApp):
    custom_app_url = "http://localhost:8080"

    def run(self, reachy_mini, stop_event):
        # Launch our agent in a thread
        self.agent = ReachyAgentLoop()
        asyncio.run(self.agent.run())
```

### 3. App Store Distribution

To publish to the Reachy App Store:

1. Restructure as a `ReachyMiniApp` subclass
2. Publish to HuggingFace Spaces
3. Submit for official listing

See [Reachy Mini App Development Guide](https://huggingface.co/blog/pollen-robotics/make-and-publish-your-reachy-mini-apps).

## Summary

| Aspect | Current Approach | Alternative |
|--------|------------------|-------------|
| **Protocol** | HTTP REST | Could add Zenoh |
| **Daemon port** | `:8000` | Same |
| **Coexistence** | ✅ With Dashboard | ⚠️ With Conversation App |
| **Motion quality** | Good (tool-based) | Better with blending |
| **Distribution** | Standalone install | Could add App Store |

The HTTP approach is well-suited for Claude's tool-based interaction model. Adding Zenoh support is an option for Phase 2 if we need real-time features like head tracking during speech.
