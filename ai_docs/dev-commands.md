# Development Commands Cheat Sheet

Quick reference for common development tasks in the Reachy Agent project.

## Environment Setup

```bash
# Create and activate virtual environment (recommended)
uv venv && source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt      # Production
uv pip install -r requirements-dev.txt  # Development tools
```

## Starting the Simulation

### macOS (with GUI)
```bash
# Terminal 1: Start MuJoCo simulation
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main --sim --scene minimal --fastapi-port 8765

# Terminal 2: Run your code
source .venv/bin/activate
python scripts/live_demo.py
```

### Headless Mode (CI/SSH)
```bash
python -m reachy_mini.daemon.app.main --sim --scene minimal --headless --fastapi-port 8765
```

## Code Quality

```bash
# Format code
uvx black . && uvx isort .

# Lint
uvx ruff check .         # Check for issues
uvx ruff check . --fix   # Auto-fix safe issues

# Type check
uvx mypy .               # Full check
uvx mypy src/            # Source only

# Security scan
uvx bandit -r src/

# All quality checks
uvx black . && uvx isort . && uvx ruff check . && uvx mypy .
```

## Running Tests

```bash
# All tests
pytest -v

# Specific test categories
pytest tests/unit -v           # Unit tests only
pytest tests/integration -v    # Integration tests
pytest tests/simulation -v     # Simulation tests

# With markers
pytest -m "not slow" -v        # Skip slow tests
pytest -m "simulation" -v      # Only simulation tests

# With coverage
pytest --cov=src --cov-report=html   # HTML report in htmlcov/
pytest --cov=src --cov-report=term   # Terminal output
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

# Precise positioning (degrees)
await client.look_at(roll=10, pitch=-15, yaw=30)
```

### Antennas
```python
# Angles: 0=down, 45=neutral, 90=up
await client.set_antenna_state(left_angle=45, right_angle=45)  # Neutral
await client.set_antenna_state(left_angle=90, right_angle=90)  # Alert
```

### Gestures
```python
await client.nod(times=2, speed="normal")   # Affirmative
await client.shake(times=2, speed="normal") # Negative
```

### Body Rotation
```python
await client.rotate("left", degrees=45, speed="normal")
```

## Direct API Calls

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
| `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py` | MCP tool definitions (23 tools) |
| `src/reachy_agent/mcp_servers/reachy/daemon_client.py` | Daemon HTTP client |
| `src/reachy_agent/mcp_servers/reachy/daemon_mock.py` | Mock daemon for testing |
| `src/reachy_agent/permissions/hooks.py` | Permission enforcement |
| `src/reachy_agent/agent/agent.py` | Main agent loop |
| `scripts/validate_mcp_e2e.py` | MCP validation |
| `scripts/validate_agent_e2e.py` | Full stack validation |
| `config/default.yaml` | Default configuration |
| `config/permissions.yaml` | Permission rules |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | For Claude | API key for Claude |
| `REACHY_DEBUG` | No | Enable debug logging |
| `REACHY_DAEMON_URL` | No | Override daemon URL |

## Troubleshooting

```bash
# Kill all daemon processes
pkill -f "reachy_mini"

# Check if port is in use
lsof -i :8765

# Reset virtual environment
rm -rf .venv && uv venv && source .venv/bin/activate && uv pip install -r requirements.txt

# Check Python path
python -c "import reachy_agent; print(reachy_agent.__file__)"
```

## MCP Testing

### Start Mock Daemon
```bash
# Terminal 1: Start the mock daemon
source .venv/bin/activate
python -m reachy_agent.mcp_servers.reachy.daemon_mock
```

### MCP Inspector (Interactive Testing)
```bash
# Terminal 2: Run MCP Inspector
npx @modelcontextprotocol/inspector \
  /Users/jawhny/Documents/projects/reachy_project/.venv/bin/python \
  -m reachy_agent.mcp_servers.reachy

# Opens browser UI at http://localhost:5173
```

### Programmatic Tool Validation
```bash
# Test all 23 MCP tools via daemon client
python scripts/validate_mcp_e2e.py

# Test full agent stack with Claude API
python scripts/validate_agent_e2e.py
```

### Quick Tool Test
```python
import asyncio
from reachy_agent.mcp_servers.reachy.daemon_client import ReachyDaemonClient

async def test():
    client = ReachyDaemonClient("http://localhost:8000")
    print(await client.move_head("left"))
    print(await client.play_emotion("happy"))
    await client.close()

asyncio.run(test())
```

## Git Workflow

```bash
# Check status
git status

# Format before commit
uvx black . && uvx isort . && uvx ruff check . --fix

# Run tests before commit
pytest -v

# Commit
git add .
git commit -m "feat: description of change"
```

## Useful Imports

```python
# Logging
from reachy_agent.utils.logging import get_logger, bind_context, clear_context
log = get_logger(__name__)

# Configuration
from reachy_agent.utils.config import ReachyConfig

# Client
from reachy_agent.simulation.reachy_client import ReachyMiniClient

# Agent loop
from reachy_agent.agent.agent import ReachyAgentLoop, create_agent_loop

# Permissions
from reachy_agent.permissions.hooks import PermissionHooks, create_permission_hooks
from reachy_agent.permissions.tiers import PermissionTier, PermissionEvaluator
```

## Expression Presets

Quick copy-paste for common expressions:

```python
# Curious
await client.look_at(roll=10, yaw=20)
await client.set_antenna_state(left_angle=30, right_angle=70)

# Happy
await client.look_at(pitch=-10)
await client.set_antenna_state(left_angle=90, right_angle=90)
await client.nod(times=1)

# Thinking
await client.look_at(yaw=15)
await client.set_antenna_state(left_angle=60, right_angle=60)

# Agreement
await client.nod(times=3)
await client.set_antenna_state(left_angle=70, right_angle=70)
```
