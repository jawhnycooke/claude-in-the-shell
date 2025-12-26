# MCP Tools Quick Reference

Compact reference for all **27 MCP tools** (23 Reachy + 4 Memory) with parameters and permission tiers.

> **Note:** Tools are discovered dynamically via MCP `ListTools` protocol.
> Sources:
> - Reachy: `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py`
> - Memory: `src/reachy_agent/mcp_servers/memory/memory_mcp.py`

## Tool Summary

| Tool | Category | Tier | Key Parameters |
|------|----------|------|----------------|
| `move_head` | Movement | 1 | direction, speed |
| `look_at` | Movement | 1 | roll, pitch, yaw, z |
| `look_at_world` | Movement | 1 | x, y, z, duration |
| `look_at_pixel` | Movement | 1 | u, v, duration |
| `rotate` | Movement | 1 | direction, degrees |
| `play_emotion` | Expression | 1 | emotion, intensity |
| `play_recorded_move` | Expression | 1 | dataset, move_name |
| `set_antenna_state` | Expression | 1 | left_angle, right_angle, wiggle |
| `nod` | Expression | 1 | times, speed |
| `shake` | Expression | 1 | times, speed |
| `rest` | Lifecycle | 1 | (none) |
| `speak` | Audio | 1 | text, voice, speed |
| `listen` | Perception | 1 | duration_seconds |
| `capture_image` | Perception | 1 | analyze, save |
| `get_sensor_data` | Perception | 1 | sensors |
| `look_at_sound` | Perception | 1 | timeout_ms |
| `dance` | Actions | 1 | routine, duration_seconds |
| `wake_up` | Lifecycle | 1 | (none) |
| `sleep` | Lifecycle | 1 | (none) |
| `set_motor_mode` | Control | 1 | mode |
| `get_status` | Status | 1 | (none) |
| `get_pose` | Status | 1 | (none) |
| `cancel_action` | Control | 1 | action_id |

## Movement Tools

### move_head
Move head in cardinal direction.
```python
await client.move_head(direction="left", speed="normal", degrees=30)
```
| Param | Values | Default |
|-------|--------|---------|
| direction | left, right, up, down, front | required |
| speed | slow, normal, fast | normal |
| degrees | 0-90 | 30 |

### look_at
Precise head positioning with Euler angles.
```python
await client.look_at(roll=0, pitch=-15, yaw=30, z=0, duration=1.0)
```
| Param | Range | Default |
|-------|-------|---------|
| roll | -45 to 45 | 0 |
| pitch | -45 to 45 | 0 |
| yaw | -45 to 45 | 0 |
| z | -50 to 50 mm | 0 |
| duration | 0.1 to 5.0 sec | 1.0 |

### look_at_world
Look at a 3D point in world coordinates using inverse kinematics.
```python
await client.look_at_world(x=-0.5, y=1.0, z=0.3, duration=1.0)
```
| Param | Range | Default |
|-------|-------|---------|
| x | meters (right=+) | required |
| y | meters (forward=+) | required |
| z | meters (up=+) | required |
| duration | 0.1 to 5.0 sec | 1.0 |

### look_at_pixel
Look at a pixel coordinate in the camera image.
```python
await client.look_at_pixel(u=320, v=240, duration=0.5)
```
| Param | Range | Default |
|-------|-------|---------|
| u | 0+ (left=0) | required |
| v | 0+ (top=0) | required |
| duration | 0.1 to 5.0 sec | 1.0 |

### rotate
Rotate body on 360° base.
```python
await client.rotate(direction="left", degrees=90, speed="normal")
```
| Param | Values | Default |
|-------|--------|---------|
| direction | left, right | required |
| degrees | 0-360 | 90 |
| speed | slow, normal, fast | normal |

## Expression Tools

### play_emotion
Trigger predefined emotion sequence. **Uses native SDK emotions when available** from the HuggingFace emotions library (`pollen-robotics/reachy-mini-emotions-library`), with fallback to custom compositions for emotions not in the SDK.
```python
await client.play_emotion(emotion="happy", intensity=0.7)
```

**Native SDK Emotions** (preferred, with synchronized audio):
| Emotion | SDK Move | Description |
|---------|----------|-------------|
| curious | curious1 | Head tilt, inquisitive |
| confused | confused1 | Uncertain behavior |
| happy/joy | cheerful1 | Happy expression |
| excited | enthusiastic1 | Excited energy |
| sad | downcast1 | Dejected |
| surprised | amazed1 | Discovery/awe |
| tired/sleepy | exhausted1 | Tired |
| listening | attentive1 | Alert/focused |
| focused | attentive2 | Deep focus |
| bored | boredom1 | Disengaged |
| scared/fear | fear1 | Frightened |
| anxious | anxiety1 | Nervous |
| angry | contempt1 | Disdainful |

**Custom Emotions** (composed from head + antenna movements):
| Emotion | Description |
|---------|-------------|
| thinking | Slow side-to-side |
| neutral | Default pose |
| agreeing | Slight nod with raised antennas |
| disagreeing | Head shake with lowered antennas |
| alert | Antennas up, head forward |

| Param | Range | Default |
|-------|-------|---------|
| emotion | see above | required |
| intensity | 0.1 to 1.0 | 0.7 |

### play_recorded_move
Play a pre-recorded move from a HuggingFace dataset. Access to the full emotions library.
```python
await client.play_recorded_move(
    dataset="pollen-robotics/reachy-mini-emotions-library",
    move_name="dance1"
)
```
| Param | Type | Default |
|-------|------|---------|
| dataset | string | required |
| move_name | string | required |

**Available moves in emotions library:**
- Emotions: curious1, confused1, cheerful1, downcast1, amazed1, exhausted1, attentive1, attentive2, contempt1, boredom1, fear1, anxiety1, disgusted1, displeased1, calming1, dying1, electric1, enthusiastic1/2, come1
- Dances: dance1, dance2, dance3

### set_antenna_state
Fine-grained antenna control.
```python
await client.set_antenna_state(left_angle=45, right_angle=45, wiggle=False, duration_ms=500)
```
| Angle | Meaning |
|-------|---------|
| 0° | Passive/sleeping |
| 45° | Alert/neutral |
| 90° | Engaged/listening |
| Asymmetric | Curious/confused |

### nod
Affirmative gesture.
```python
await client.nod(times=2, speed="normal")
```
| Param | Range | Default |
|-------|-------|---------|
| times | 1-5 | 2 |
| speed | slow, normal, fast | normal |

### shake
Negative gesture.
```python
await client.shake(times=2, speed="normal")
```
| Param | Range | Default |
|-------|-------|---------|
| times | 1-5 | 2 |
| speed | slow, normal, fast | normal |

## Audio Tools

### speak
Text-to-speech output.
```python
await client.speak(text="Hello!", voice="default", speed=1.0)
```
| Param | Range | Default |
|-------|-------|---------|
| text | max 500 chars | required |
| voice | string | default |
| speed | 0.5 to 2.0 | 1.0 |

### listen
Capture audio from microphones.
```python
await client.listen(duration_seconds=3.0)
```
| Param | Range | Default |
|-------|-------|---------|
| duration_seconds | 0.5 to 10.0 | 3.0 |

## Perception Tools

### capture_image
Capture camera frame.
```python
await client.capture_image(analyze=False, save=False)
```
| Param | Type | Default |
|-------|------|---------|
| analyze | bool | False |
| save | bool | False |

### get_sensor_data
Read sensor values.
```python
await client.get_sensor_data(sensors=["all"])
```
| Sensor | Data |
|--------|------|
| imu | accelerometer, gyroscope |
| audio_level | ambient dB |
| temperature | internal temp |
| all | everything |

### look_at_sound
Turn toward detected sound source.
```python
await client.look_at_sound(timeout_ms=2000)
```
| Param | Range | Default |
|-------|-------|---------|
| timeout_ms | 500+ | 2000 |

## Lifecycle Tools

### wake_up
Initialize motors, ready position.
```python
await client.wake_up()
```

### sleep
Power down motors safely.
```python
await client.sleep()
```

### rest
Return to neutral pose (motors stay active).
```python
await client.rest()
```

## Action Tools

### dance
Execute choreographed routine. **Uses native SDK dances when available** from the HuggingFace emotions library.
```python
await client.dance(routine="celebrate", duration_seconds=5.0)
```
| Routine | Native SDK | Description |
|---------|------------|-------------|
| celebrate | dance1 | Excited movement |
| party | dance2 | Energetic dance |
| groove | dance3 | Rhythmic motion |
| greeting | (custom) | Welcome gesture |
| thinking | (custom) | Contemplative motion |

## Status Tools

### get_status
Get comprehensive robot status.
```python
await client.get_status()
```
Returns: `{status, connected, control_mode, ...}`

### get_pose
Get current physical pose (proprioceptive feedback).
```python
await client.get_pose()
```
Returns:
| Field | Description |
|-------|-------------|
| head.roll | Side tilt (-45 to 45°) |
| head.pitch | Up/down (-45 to 45°) |
| head.yaw | Left/right (-45 to 45°) |
| body_yaw | Body rotation (degrees) |
| antennas.left | Left antenna (0-90°) |
| antennas.right | Right antenna (0-90°) |

## Control Tools

### set_motor_mode
Set the motor control mode. Essential for safety and teaching mode.
```python
await client.set_motor_mode(mode="gravity_compensation")
```
| Mode | Description |
|------|-------------|
| enabled | Normal operation, motors active |
| disabled | Motors off, robot goes limp |
| gravity_compensation | Motors resist gravity, can be posed by hand |

> **Note:** Only available on real daemon (not in simulation mock).

### cancel_action
Cancel a running action by its UUID.
```python
await client.cancel_action(action_id="abc123-def456")
```
| Param | Type | Default |
|-------|------|---------|
| action_id | string (UUID) | required |

## Permission Tiers Reference

From `config/permissions.yaml`:

| Tier | Name | Behavior |
|------|------|----------|
| 1 | autonomous | Execute immediately |
| 2 | notify | Execute + notify user |
| 3 | confirm | Ask before executing (60s timeout) |
| 4 | forbidden | Never execute |

### Default Rules

```yaml
# Tier 1: Autonomous
- pattern: "mcp__reachy__*"      # All body control
- pattern: "mcp__calendar__get_*" # Read calendar
- pattern: "mcp__weather__*"      # Weather info
- pattern: "mcp__github__get_*"   # Read GitHub

# Tier 2: Notify
- pattern: "mcp__homeassistant__turn_on_*"
- pattern: "mcp__homeassistant__turn_off_*"
- pattern: "mcp__slack__send_message"

# Tier 3: Confirm
- pattern: "mcp__calendar__create_*"
- pattern: "mcp__github__create_*"
- pattern: "mcp__homeassistant__unlock_*"

# Tier 4: Forbidden
- pattern: "mcp__homeassistant__disarm_*"
- pattern: "mcp__email__send"
- pattern: "mcp__banking__*"
```

## Memory MCP Server (4 tools)

The Memory MCP server provides semantic memory and user profile management.

> **Source:** `src/reachy_agent/mcp_servers/memory/memory_mcp.py`

### search_memories
Semantic search over stored memories using ChromaDB vector similarity.
```python
await client.search_memories(query="What did we discuss yesterday?", limit=5)
```
| Param | Type | Default |
|-------|------|---------|
| query | string | required |
| limit | 1-20 | 5 |
| memory_type | string (optional) | None (all types) |

**Memory Types:** `conversation`, `fact`, `preference`, `event`

**Returns:** List of memories with similarity scores

### store_memory
Save a new memory with automatic type classification and embedding.
```python
await client.store_memory(
    content="User prefers morning meetings",
    memory_type="preference",
    metadata={"source": "conversation"}
)
```
| Param | Type | Default |
|-------|------|---------|
| content | string | required |
| memory_type | string | "conversation" |
| metadata | dict (optional) | {} |

### get_user_profile
Retrieve user profile with preferences and connected services.
```python
await client.get_user_profile(user_id="default")
```
| Param | Type | Default |
|-------|------|---------|
| user_id | string | "default" |

**Returns:**
| Field | Description |
|-------|-------------|
| name | User's display name |
| preferences | Key-value preferences |
| schedule_patterns | Recurring schedule info |
| connected_services | Linked external services |

### update_user_profile
Update user profile preferences.
```python
await client.update_user_profile(
    user_id="default",
    name="Alice",
    preferences={"wake_time": "7:00 AM", "voice": "friendly"}
)
```
| Param | Type | Default |
|-------|------|---------|
| user_id | string | "default" |
| name | string (optional) | unchanged |
| preferences | dict (optional) | merged with existing |

### Memory System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Memory MCP Server                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  search_memories │ store_memory │ get_profile │ update_profile││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    ▼                   ▼
        ┌─────────────────┐   ┌─────────────────┐
        │    ChromaDB     │   │     SQLite      │
        │ (Vector Store)  │   │ (User Profiles) │
        │                 │   │                 │
        │ • Semantic      │   │ • Preferences   │
        │   embeddings    │   │ • Sessions      │
        │ • Similarity    │   │ • Schedule      │
        │   search        │   │   patterns      │
        └─────────────────┘   └─────────────────┘
```

### Memory Tool Permission Tier

All memory tools are **Tier 1 (Autonomous)** - they read/write to local storage only.

## Error Codes

| Code | Description |
|------|-------------|
| `INVALID_PARAMETER` | Bad parameter value |
| `HARDWARE_ERROR` | Hardware communication failed |
| `TIMEOUT` | Operation timed out |
| `NOT_READY` | Robot not initialized |
| `PERMISSION_DENIED` | Action blocked by tier |
| `MEMORY_ERROR` | Memory system failure (ChromaDB/SQLite) |
