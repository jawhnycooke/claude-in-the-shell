# Raspberry Pi Installation Guide

This guide covers installing Claude in the Shell on a Reachy Mini's Raspberry Pi 4.

## Prerequisites

- Reachy Mini with Raspberry Pi 4 (4GB+ RAM recommended)
- Reachy Mini SDK installed and daemon running
- WiFi connectivity
- Anthropic API key

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Raspberry Pi 4                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Claude in the Shell                                      │  │
│  │  ├── Agent Loop (Claude SDK)                              │  │
│  │  ├── Reachy MCP Server (23 tools)                         │  │
│  │  ├── Memory MCP Server (4 tools)                          │  │
│  │  └── Permission System (4-tier)                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │ HTTP :8000                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Reachy Daemon (Pollen Robotics)                          │  │
│  │  ├── FastAPI REST endpoints                               │  │
│  │  ├── Zenoh pub/sub (for real-time apps)                   │  │
│  │  └── Hardware drivers                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                        │                                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Robot Hardware                                           │  │
│  │  ├── Head (6 DOF) + Body (360°)                           │  │
│  │  ├── 2 Animated Antennas                                  │  │
│  │  ├── Wide-angle Camera                                    │  │
│  │  └── 4-mic Array + Speaker                                │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Compatibility with Reachy Ecosystem

Claude in the Shell is designed to **coexist** with other Reachy apps:

| Protocol | Used By | Purpose |
|----------|---------|---------|
| **HTTP REST** (`:8000`) | Claude in the Shell | Tool-based commands |
| **Zenoh** (pub/sub) | Conversation App, Dashboard | Real-time 100Hz control |

Both protocols access the same daemon - you can run Claude in the Shell alongside the dashboard.

## Installation

### Step 1: Verify Reachy SDK

First, ensure the Reachy Mini SDK is installed and the daemon is running:

```bash
# Check daemon status
curl http://localhost:8000/api/daemon/status

# Expected output includes:
# {"simulation_enabled": false, "robot_name": "reachy_mini", ...}
```

If the daemon isn't running, start it according to Pollen's documentation.

### Step 2: Install uv (Fast Package Manager)

```bash
# Install uv for 10-100x faster package installation
curl -LsSf https://astral.sh/uv/install.sh | sh

# Reload shell
source ~/.bashrc  # or ~/.zshrc
```

### Step 3: Clone and Install Claude in the Shell

```bash
# Clone the repository
git clone https://github.com/jawhnycooke/claude-in-the-shell.git
cd claude-in-the-shell

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### Step 4: Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your API key
nano .env
```

Required environment variables:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...

# Optional: GitHub integration
GITHUB_PERSONAL_ACCESS_TOKEN=ghp_...

# Optional: Custom daemon URL (default: http://localhost:8000)
REACHY_DAEMON_URL=http://localhost:8000
```

### Step 5: Install GitHub MCP Binary (Optional)

For GitHub integration without Docker:

```bash
# Create bin directory
mkdir -p ~/.reachy/bin

# Download ARM64 binary
curl -sL https://github.com/github/github-mcp-server/releases/latest/download/github-mcp-server_Linux_arm64.tar.gz | tar xzf - -C ~/.reachy/bin

# Verify installation
~/.reachy/bin/github-mcp-server --version
```

### Step 6: Verify Installation

```bash
# Run health check
python -m reachy_agent check

# Expected output:
# ✓ Daemon connection: OK
# ✓ MCP servers: OK
# ✓ Permissions: OK
```

## Running the Agent

### Interactive REPL Mode

```bash
# Rich terminal interface
python -m reachy_agent repl
```

### Web Dashboard Mode

```bash
# Start web interface at http://localhost:8080
python -m reachy_agent web
```

### Background Agent Mode

```bash
# Run agent in background
python -m reachy_agent run --daemon
```

## Systemd Service (Auto-Start)

Create a systemd service for automatic startup:

```bash
sudo nano /etc/systemd/system/claude-in-the-shell.service
```

```ini
[Unit]
Description=Claude in the Shell - Reachy AI Agent
After=network.target reachy-daemon.service
Wants=reachy-daemon.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/claude-in-the-shell
Environment="PATH=/home/pi/claude-in-the-shell/.venv/bin:/usr/local/bin:/usr/bin"
Environment="ANTHROPIC_API_KEY=sk-ant-..."
ExecStart=/home/pi/claude-in-the-shell/.venv/bin/python -m reachy_agent run
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable claude-in-the-shell
sudo systemctl start claude-in-the-shell

# Check status
sudo systemctl status claude-in-the-shell
```

## Memory Requirements

| Component | RAM Usage |
|-----------|-----------|
| Claude in the Shell | ~200MB |
| ChromaDB (memory) | ~100MB |
| MCP servers | ~50MB |
| **Total** | ~350MB |

Raspberry Pi 4 with 4GB RAM has plenty of headroom.

## Performance Tips

### 1. Reduce Claude API Latency

Use a fast model for routine tasks:

```python
# In config/default.yaml
agent:
  model: claude-sonnet-4-20250514  # Fast model
  # model: claude-opus-4-5-20250514  # For complex reasoning
```

### 2. Monitor Temperature

```bash
# Check CPU temperature
vcgencmd measure_temp

# If throttling, add cooling
```

### 3. Use Swap for Large Memory Operations

```bash
# Increase swap if needed
sudo dphys-swapfile swapoff
sudo nano /etc/dphys-swapfile
# Set CONF_SWAPSIZE=2048
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

## Troubleshooting

### Daemon Connection Failed

```bash
# Check if daemon is running
systemctl status reachy-mini-daemon

# Check port availability
netstat -tlnp | grep 8000

# Restart daemon
sudo systemctl restart reachy-mini-daemon
```

### Permission Denied Errors

```bash
# Add user to required groups
sudo usermod -aG video,audio,gpio pi

# Reload groups
newgrp video
```

### API Rate Limits

Claude API has rate limits. If you see 429 errors:

```python
# In config/default.yaml
agent:
  rate_limit_delay: 1.0  # seconds between requests
```

### Memory Issues

```bash
# Check memory usage
free -h

# Clear Python cache
find . -type d -name __pycache__ -exec rm -rf {} +

# Restart with lower memory profile
python -m reachy_agent run --memory-mode minimal
```

## Updating

```bash
cd ~/claude-in-the-shell
git pull origin main
source .venv/bin/activate
uv pip install -r requirements.txt

# Restart service
sudo systemctl restart claude-in-the-shell
```

## Logs

```bash
# View service logs
journalctl -u claude-in-the-shell -f

# View agent logs
tail -f ~/.reachy/logs/agent.log
```

## Coexistence with Other Apps

Claude in the Shell can run alongside:

- **Reachy Dashboard**: Both use the daemon simultaneously
- **Conversation App**: May conflict if both try to control the robot

To avoid conflicts:
1. Stop Conversation App before running Claude in the Shell
2. Or use the web dashboard to switch between apps

## Security Considerations

1. **API Keys**: Never commit `.env` to version control
2. **Network**: The web dashboard is bound to localhost by default
3. **Permissions**: The 4-tier system prevents destructive actions

## Next Steps

- [Getting Started Tutorial](../tutorials/getting-started.md) - Learn the basics
- [Architecture Overview](../architecture/overview.md) - Understand the system
- [MCP Tools Reference](../../ai_docs/mcp-tools-quick-ref.md) - Available robot commands
