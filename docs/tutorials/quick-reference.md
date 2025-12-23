# Quick Reference Card

A cheat sheet for common Reachy Agent development tasks.

## Starting the Simulation

### macOS (with GUI)
```bash
# Terminal 1: Start simulation
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main --sim --scene minimal --fastapi-port 8765

# Terminal 2: Run your code
source .venv/bin/activate
python scripts/live_demo.py
```

### Headless Mode (CI/SSH)
```bash
python -m reachy_mini.daemon.app.main --sim --scene minimal --headless --fastapi-port 8765
```

## Common Commands

### Environment Setup
```bash
uv venv && source .venv/bin/activate  # Create/activate venv
uv pip install -r requirements.txt     # Install dependencies
uv pip install -r requirements-dev.txt # Install dev tools
```

### Running Tests
```bash
pytest -v                              # All tests
pytest tests/simulation/ -v            # Simulation tests only
pytest -m "not slow" -v                # Skip slow tests
```

### Code Quality
```bash
black . && isort .                     # Format code
mypy src/                              # Type check
ruff check .                           # Lint
```

## ReachyMiniClient API

### Connection
```python
from reachy_agent.simulation.reachy_client import ReachyMiniClient

client = ReachyMiniClient(base_url="http://localhost:8765")
```

### Lifecycle
```python
await client.wake_up()   # Activate motors
await client.rest()      # Neutral position
await client.sleep()     # Deactivate motors
await client.close()     # Close connection
```

### Head Movement
```python
# Cardinal directions
await client.move_head("left", speed="normal")   # left, right, up, down, front
await client.move_head("right", speed="fast")    # slow, normal, fast

# Precise positioning (degrees)
await client.look_at(roll=10, pitch=-15, yaw=30)
```

### Antennas
```python
# Angles: 0=down, 45=neutral, 90=up
await client.set_antenna_state(left_angle=45, right_angle=45)  # Neutral
await client.set_antenna_state(left_angle=90, right_angle=90)  # Alert
await client.set_antenna_state(left_angle=30, right_angle=70)  # Curious
```

### Gestures
```python
await client.nod(times=2, speed="normal")   # Affirmative
await client.shake(times=2, speed="normal") # Negative
```

### Body Rotation
```python
await client.rotate("left", degrees=45, speed="normal")
await client.rotate("right", degrees=90, speed="fast")
```

## Expression Presets

| Expression | Head | Antennas | Gesture |
|------------|------|----------|---------|
| **Curious** | roll=10, yaw=20 | L=30, R=70 | - |
| **Happy** | pitch=-10 | L=90, R=90 | nod |
| **Sad** | pitch=20, roll=-5 | L=20, R=20 | - |
| **Confused** | roll=15 | L=60, R=30 | - |
| **Thinking** | yaw=15 | L=60, R=60 | - |
| **Agreeing** | - | L=70, R=70 | nod x3 |
| **Disagreeing** | - | L=30, R=30 | shake x2 |

## Claude Agent SDK Integration

### Basic Tool Call Pattern
```python
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

tools = [
    {
        "name": "move_head",
        "description": "Move the robot's head",
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["left", "right", "up", "down", "front"]},
                "speed": {"type": "string", "enum": ["slow", "normal", "fast"]}
            },
            "required": ["direction"]
        }
    }
]

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "Make the robot look curious"}]
)
```

## API Endpoints (Direct HTTP)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/daemon/status` | GET | Health check |
| `/api/state/full` | GET | Full robot state |
| `/api/move/goto` | POST | Move to position |
| `/api/move/play/wake_up` | POST | Wake up robot |
| `/api/move/play/goto_sleep` | POST | Sleep robot |

### Example: Direct API Call
```bash
# Status check
curl -s http://localhost:8765/api/daemon/status | python3 -m json.tool

# Move head
curl -X POST http://localhost:8765/api/move/goto \
  -H "Content-Type: application/json" \
  -d '{"head_pose": {"x": 0, "y": 0, "z": 0, "roll": 0, "pitch": 0, "yaw": 0.5}, "duration": 1.0}'
```

## File Locations

| Path | Purpose |
|------|---------|
| `src/reachy_agent/simulation/reachy_client.py` | Robot client API |
| `src/reachy_agent/mcp_servers/reachy/server.py` | MCP tool definitions |
| `scripts/live_demo.py` | Interactive demo |
| `scripts/validate_mcp_e2e.py` | MCP validation |
| `scripts/validate_agent_e2e.py` | Full stack validation |
| `config/default.yaml` | Default configuration |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For Claude | API key for Claude |
| `REACHY_DEBUG` | No | Enable debug logging |
| `REACHY_DAEMON_URL` | No | Override daemon URL |

## Troubleshooting Quick Fixes

```bash
# Kill all daemon processes
pkill -f "reachy_mini"

# Check if port is in use
lsof -i :8765

# Reset virtual environment
rm -rf .venv && uv venv && source .venv/bin/activate && uv pip install -r requirements.txt
```
