# Port Configuration Guide

This guide clarifies the port configuration for different deployment modes in the Reachy Agent project.

## Port Reference

| Service | Port | Description |
|---------|------|-------------|
| **Reachy Daemon (Production)** | `8000` | Real Reachy hardware on Raspberry Pi |
| **MuJoCo Daemon (Simulation)** | `8765` | Physics simulation via `mjpython` |
| **Mock Daemon** | `8000` | Testing without hardware or MuJoCo |
| **Web Dashboard** | `8080` | Browser-based agent interface |
| **MCP Inspector** | `5173` | MCP tool testing UI |

## Daemon Ports Explained

### Production Daemon (:8000)

The Reachy daemon runs on port `8000` by default when using real hardware:

```bash
# On Raspberry Pi - daemon auto-starts on boot
# Agent connects to production port
python -m reachy_agent run  # defaults to http://localhost:8000
```

### MuJoCo Simulation (:8765)

The MuJoCo simulation daemon runs on port `8765` to avoid conflicts with production:

```bash
# Terminal 1: Start simulation
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main \
  --sim --scene minimal --fastapi-port 8765

# Terminal 2: Connect agent
python -m reachy_agent run --daemon-url http://localhost:8765
```

**Why 8765?** The simulation uses a different port to:
1. Avoid conflicts with local development daemons
2. Allow both real and simulated daemons to run simultaneously
3. Make it clear which daemon you're targeting

### Mock Daemon (:8000)

The mock daemon uses the same port as production (`8000`) for seamless testing:

```bash
# Option 1: Start mock manually
python -m reachy_agent.mcp_servers.reachy.daemon_mock

# Option 2: Use --mock flag (auto-starts on 8000)
python -m reachy_agent run --mock
```

## CLI Command Defaults

| Command | Default Daemon Port | Notes |
|---------|---------------------|-------|
| `run` | `8000` | Production-first |
| `repl` | `8765` | Simulation-first |
| `web` | `8765` | Simulation-first |
| `check` | `8000` | Checks production |

**Rationale**: `run` targets production by default since it's used on the robot. `repl` and `web` target simulation since they're primarily used during development.

## Override Examples

```bash
# Run with simulation
python -m reachy_agent run --daemon-url http://localhost:8765

# REPL with production
python -m reachy_agent repl --daemon-url http://localhost:8000

# Web dashboard with production
python -m reachy_agent web --daemon-url http://localhost:8000

# Environment variable override (all commands)
export REACHY_DAEMON_URL=http://192.168.1.100:8000
python -m reachy_agent run
```

## Network Setup

### Local Development

```
┌─────────────────────────────────────────────┐
│  Development Machine                         │
│  ┌─────────────┐   ┌─────────────────────┐  │
│  │ Agent       │──▶│ MuJoCo Daemon :8765 │  │
│  │ (repl/web)  │   └─────────────────────┘  │
│  └─────────────┘   ┌─────────────────────┐  │
│        or    ────▶ │ Mock Daemon :8000   │  │
│                    └─────────────────────┘  │
└─────────────────────────────────────────────┘
```

### Production (Raspberry Pi)

```
┌─────────────────────────────────────────────┐
│  Raspberry Pi                                │
│  ┌─────────────┐   ┌─────────────────────┐  │
│  │ Agent       │──▶│ Reachy Daemon :8000 │  │
│  │ (run)       │   └──────────┬──────────┘  │
│  └─────────────┘              │             │
└───────────────────────────────┼─────────────┘
                        ┌───────▼───────┐
                        │ Reachy Mini   │
                        │ Hardware      │
                        └───────────────┘
```

### Remote Development

```bash
# SSH tunnel from dev machine to Pi
ssh -L 8000:localhost:8000 pi@reachy-pi.local

# Now run agent locally, connecting to remote daemon
python -m reachy_agent run  # Uses tunneled :8000
```

## Troubleshooting

### "Connection refused on port 8000"

1. Check if any daemon is running: `lsof -i :8000`
2. Start mock daemon: `python -m reachy_agent run --mock`
3. Or start MuJoCo: `/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main --sim --fastapi-port 8000`

### "Connection refused on port 8765"

1. Start MuJoCo simulation:
   ```bash
   /opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main \
     --sim --scene minimal --fastapi-port 8765
   ```
2. Or use mock daemon with port override:
   ```bash
   # Not recommended - mock doesn't need MuJoCo port
   ```

### Port Already in Use

```bash
# Find what's using the port
lsof -i :8765

# Kill the process
kill -9 <PID>

# Or kill all daemon processes
pkill -f "reachy_mini"
```

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REACHY_DAEMON_URL` | Override daemon URL for all commands | None |
| `REACHY_DEBUG` | Enable debug logging | `false` |

### Config File (`config/default.yaml`)

```yaml
daemon:
  url: "http://localhost:8000"  # Default daemon URL
  timeout_seconds: 30           # Request timeout
  retry_attempts: 3             # Connection retries
```

## Quick Reference

```bash
# Simulation workflow (most common in development)
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main --sim --fastapi-port 8765
python -m reachy_agent repl  # defaults to :8765

# Production workflow (on Raspberry Pi)
python -m reachy_agent run  # defaults to :8000

# Testing workflow (no external dependencies)
python -m reachy_agent run --mock  # starts mock on :8000
```
