# Reachy Mini Community Movement Datasets

This document catalogs community-contributed movement datasets on Hugging Face that are compatible with Reachy Mini.

## Available Datasets

| Dataset | Moves | Duration | Description |
|---------|-------|----------|-------------|
| [RemiFabre/mymoves](https://huggingface.co/datasets/RemiFabre/mymoves) | 2 | 10s | General movements (counting gestures) |
| [RemiFabre/dances](https://huggingface.co/datasets/RemiFabre/dances) | 1 | 16s | Dance routines (wakawaka) |
| [RemiFabre/marionette-dataset2](https://huggingface.co/datasets/RemiFabre/marionette-dataset2) | 1 | 5s | Marionette recordings |

**Creator:** Remi Fabre (Pollen Robotics)
**License:** Apache 2.0
**Last Updated:** December 2025

## Marionette Recording Format

Movements are recorded using the **Marionette Reachy Mini app** and stored as JSON trajectory files following the Reachy Mini emotions schema.

### Data Structure

```json
{
  "move_id": "counting",
  "description": "Counting gesture with head and antennas",
  "duration_seconds": 5.0,
  "has_audio": true,
  "set_target_data": {
    "antennas": [45.0, 45.0],
    "body_yaw": 0.0,
    "check_collision": true,
    "head": [[...4x4 transformation matrix...]]
  }
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `head` | `list[list[float]]` | 4x4 transformation matrix for head pose |
| `body_yaw` | `float` | Base rotation in degrees |
| `antennas` | `list[float]` | Left/right antenna positions (0-90°) |
| `check_collision` | `bool` | Safety collision checking flag |
| `duration_seconds` | `float` | Total motion duration |
| `has_audio` | `bool` | Whether WAV audio is included |

### File Organization

```
data/
├── counting/
│   ├── trajectory.json    # Motion keyframes
│   └── audio.wav          # Optional audio recording
├── wakawaka/
│   ├── trajectory.json
│   └── audio.wav
└── ...
```

## Comparison with Our Dance Format

Our current `daemon_client.py` uses a simpler keyframe format:

```python
# Our format (simpler, roll/pitch/yaw degrees)
DANCE_ROUTINES = {
    "celebrate": [
        {"pitch": 15, "yaw": -20, "roll": 10, "duration": 0.4},
        ...
    ]
}
```

**Marionette format advantages:**
- Full 4x4 transformation matrices (more precise)
- Time-indexed keyframes (smoother interpolation)
- Audio synchronization support
- Community contribution via Marionette app

**Our format advantages:**
- Human-readable and editable
- Simpler to create programmatically
- No external dependencies

## Future Integration

> **TODO:** Consider building a motion loader module to:
> 1. Download datasets from Hugging Face
> 2. Cache motions to `~/.reachy/motions/`
> 3. Convert Marionette format to daemon API calls
> 4. Expose a `play_recording` MCP tool
>
> This would allow the agent to access community-contributed movements.

## Discovery

Search Hugging Face for more datasets:
- Tag: `reachy_mini_community_moves`
- Organization: `RemiFabre` (Pollen Robotics developer)

## Related Resources

- [Marionette App](https://github.com/pollen-robotics/reachy_mini) - Record movements
- [Reachy Mini SDK](https://github.com/pollen-robotics/reachy_mini) - Robot control
- [Hugging Face Datasets](https://huggingface.co/docs/datasets/) - Dataset loading
