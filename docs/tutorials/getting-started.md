# Tutorial: Getting Started with Reachy Agent Development

Welcome to embodied AI development with the Reachy Mini robot and Claude Agent SDK! This tutorial will guide you through setting up a complete development environment where you can control a simulated robot using AI.

## What You'll Learn

By the end of this tutorial, you will:
- Have a working MuJoCo simulation of the Reachy Mini robot
- Control the robot programmatically with Python
- See the robot respond to your commands in real-time
- Understand how to integrate the Claude Agent SDK for AI-powered control

## Prerequisites

### Required Knowledge
- Basic Python programming (functions, async/await)
- Familiarity with terminal/command line

### Required Setup
- macOS (Apple Silicon or Intel) or Linux
- Python 3.10 or higher
- Homebrew (macOS only)
- About 2GB free disk space

### Time Required
- Approximately 30 minutes

---

## Part 1: Environment Setup (10 min)

Let's set up your development environment step by step.

### Step 1.1: Verify Python Version

First, let's make sure you have Python 3.10 or higher installed.

```bash
python3 --version
```

You should see:
```
Python 3.10.x  # or higher
```

If you don't have Python 3.10+, install it via Homebrew (macOS) or your system package manager.

### Step 1.2: Install uv Package Manager

We'll use `uv` for fast Python package management:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, restart your terminal or run:
```bash
source ~/.bashrc  # or ~/.zshrc on macOS
```

Verify it's installed:
```bash
uv --version
```

You should see:
```
uv 0.x.x
```

### Step 1.3: Clone the Repository

```bash
git clone https://github.com/jawhnycooke/reachy-agent.git
cd reachy-agent
```

### Step 1.4: Create Virtual Environment

```bash
uv venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)`:
```
(.venv) user@machine:~/reachy-agent$
```

### Step 1.5: Install Core Dependencies

```bash
uv pip install -r requirements.txt
```

You should see packages being installed:
```
Resolved 25 packages in 1.2s
Downloaded 25 packages in 3.4s
Installed 25 packages in 0.8s
```

### Checkpoint: Verify Environment

Let's make sure everything is working so far:

```bash
python -c "import httpx; import pydantic; print('Core dependencies OK!')"
```

You should see:
```
Core dependencies OK!
```

---

## Part 2: MuJoCo Simulation Setup (10 min)

Now we'll set up the physics simulation that lets you control a virtual Reachy robot.

### Step 2.1: Install MuJoCo (macOS)

On macOS, MuJoCo needs to be installed via Homebrew for proper GUI support:

```bash
brew install mujoco
```

Verify the installation:
```bash
which mjpython
```

You should see:
```
/opt/homebrew/bin/mjpython
```

> **Note**: `mjpython` is a special Python launcher that enables MuJoCo's GUI on macOS.

### Step 2.2: Install Reachy Mini SDK

The Reachy Mini SDK needs to be installed in the system Python that `mjpython` uses:

```bash
/opt/homebrew/bin/pip3 install reachy-mini
```

You should see:
```
Successfully installed reachy-mini-x.x.x
```

### Step 2.3: Start the Simulation

Now for the exciting part - let's launch the robot simulation!

Open a **new terminal window** (keep it running) and execute:

```bash
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main --sim --scene minimal --fastapi-port 8765
```

You should see:
1. A window appear showing the Reachy Mini robot
2. Console output like:
```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8765
```

**Keep this window open!** The simulation needs to run while you control the robot.

### Step 2.4: Verify the Daemon is Running

In your **original terminal** (with the virtual environment active), test the connection:

```bash
curl -s http://localhost:8765/api/daemon/status | python3 -m json.tool
```

You should see:
```json
{
    "state": "running",
    "simulation_enabled": true,
    "scene": "minimal"
}
```

### Checkpoint: Simulation Ready

Before continuing, verify:
- [ ] MuJoCo window is visible with the robot
- [ ] Daemon status returns "running"
- [ ] You can see the robot's head and antennas

---

## Part 3: Your First Robot Commands (10 min)

Let's make the robot move! We'll use Python to send commands to the simulation.

### Step 3.1: Open Python Interactive Shell

In your terminal with the virtual environment active:

```bash
cd ~/reachy-agent  # or wherever you cloned the repo
source .venv/bin/activate
python
```

### Step 3.2: Connect to the Robot

In the Python shell:

```python
import asyncio
import sys
sys.path.insert(0, "src")  # Add source to path

from reachy_agent.simulation.reachy_client import ReachyMiniClient

# Create client
client = ReachyMiniClient(base_url="http://localhost:8765")

# Wake up the robot
async def wake():
    result = await client.wake_up()
    print(f"Robot awake: {result}")

asyncio.run(wake())
```

You should see:
```
Robot awake: {'uuid': 'abc123...'}
```

**Look at the MuJoCo window!** The robot should now be in an alert position with antennas up.

### Step 3.3: Move the Head

Let's make the robot look around:

```python
async def look_around():
    # Look left
    print("Looking left...")
    await client.move_head("left", speed="normal")
    await asyncio.sleep(1)

    # Look right
    print("Looking right...")
    await client.move_head("right", speed="normal")
    await asyncio.sleep(1)

    # Look up
    print("Looking up...")
    await client.move_head("up", speed="normal")
    await asyncio.sleep(1)

    # Return to center
    print("Centering...")
    await client.move_head("front", speed="normal")

asyncio.run(look_around())
```

**Watch the simulation window!** You should see the robot's head moving in each direction.

### Step 3.4: Control the Antennas

The antennas are expressive - let's make them move:

```python
async def antenna_expressions():
    # Antennas up (excited!)
    print("Excited pose...")
    await client.set_antenna_state(left_angle=90, right_angle=90)
    await asyncio.sleep(1)

    # Curious tilt
    print("Curious pose...")
    await client.set_antenna_state(left_angle=30, right_angle=70)
    await asyncio.sleep(1)

    # Neutral
    print("Neutral pose...")
    await client.set_antenna_state(left_angle=45, right_angle=45)

asyncio.run(antenna_expressions())
```

### Step 3.5: Make the Robot Nod

Let's have the robot agree with you:

```python
async def nod_yes():
    print("Nodding...")
    result = await client.nod(times=3, speed="normal")
    print(f"Nod complete: {result}")

asyncio.run(nod_yes())
```

**Watch for it!** The robot will nod its head up and down three times.

### Step 3.6: Clean Up

When you're done experimenting:

```python
async def cleanup():
    await client.rest()  # Return to neutral position
    await client.close()
    print("Done!")

asyncio.run(cleanup())
exit()
```

### Checkpoint: Robot Control Works!

You've successfully:
- [ ] Woken up the robot
- [ ] Moved its head in different directions
- [ ] Controlled antenna positions
- [ ] Made it perform gestures (nodding)

---

## Part 4: Running the Demo Script (5 min)

Now let's run a complete demonstration that shows all the robot's capabilities.

### Step 4.1: Run the Live Demo

```bash
python scripts/live_demo.py
```

You should see:
```
============================================================
🤖 Reachy Mini Live Demo
============================================================

1️⃣  Waking up robot...
   ✓ {'uuid': '...'}

2️⃣  Head movements:
   → Looking left... ✓
   → Looking right... ✓
   → Looking up... ✓
   → Looking down... ✓
   → Looking front... ✓

3️⃣  Antenna expressions:
   → Antennas down (sleeping)... ✓
   → Antennas mid (alert)... ✓
   → Antennas up (engaged)... ✓
   ...

✅ Demo complete!
============================================================
```

**Watch the simulation window** as each movement happens in real-time!

---

## Part 5: MCP Validation (Optional) (5 min)

This validates that all the MCP (Model Context Protocol) tools work correctly.

```bash
python scripts/validate_mcp_e2e.py
```

Expected output:
```
============================================================
🔧 MCP End-to-End Validation
============================================================

[1/8] Testing get_status (health check)... ✅ PASSED
[2/8] Testing wake_up tool... ✅ PASSED
[3/8] Testing move_head tool... ✅ PASSED
[4/8] Testing look_at tool... ✅ PASSED
[5/8] Testing set_antenna_state tool... ✅ PASSED
[6/8] Testing nod gesture... ✅ PASSED
[7/8] Testing shake gesture... ✅ PASSED
[8/8] Testing combined expression sequence... ✅ PASSED

============================================================
📊 Results Summary
============================================================
   Passed: 8/8

🎉 ALL MCP TOOLS VALIDATED SUCCESSFULLY!
============================================================
```

---

## Part 6: Claude Agent SDK Integration (10 min)

This is where it gets exciting - we'll have Claude control the robot!

### Step 6.1: Get an Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Sign in or create an account
3. Navigate to API Keys
4. Create a new API key
5. Copy the key (starts with `sk-ant-`)

### Step 6.2: Set the API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### Step 6.3: Run the Agent Validation

```bash
python scripts/validate_agent_e2e.py
```

You should see:
```
======================================================================
🤖 Claude Agent SDK End-to-End Validation
======================================================================

✅ API Key configured: sk-ant-api03-YCodm...
✅ Simulation daemon running at http://localhost:8765

----------------------------------------------------------------------
📝 Test Scenario: Ask Claude to make Reachy express curiosity
----------------------------------------------------------------------

🔄 Sending request to Claude API...

📨 Response received (stop_reason: tool_use)

🔧 Claude called: move_head({'direction': 'left', 'speed': 'normal'})
   ✅ Executed successfully
🔧 Claude called: set_antenna_state({'left_angle': 75, 'right_angle': 80})
   ✅ Executed successfully

----------------------------------------------------------------------
💬 Claude's response:
----------------------------------------------------------------------
I've made Reachy express curiosity by turning its head to the left
and raising its antennas asymmetrically...

======================================================================
📊 Validation Summary
======================================================================
   API calls to Claude: 1+
   Tool calls executed: 2
   Tools used: move_head, set_antenna_state

🎉 FULL AGENT STACK VALIDATED!

   User Request
        ↓
   Claude API (reasoning)
        ↓
   Tool Calls (MCP interface)
        ↓
   ReachyMiniClient (HTTP)
        ↓
   Reachy Daemon (FastAPI)
        ↓
   MuJoCo Physics Engine
        ↓
   🤖 Robot Movement!
======================================================================
```

**Watch the simulation!** You'll see Claude decide how to make the robot look curious and execute the movements.

---

## What You've Accomplished

Congratulations! You've successfully:

- ✅ Set up a Python development environment with uv
- ✅ Installed and configured MuJoCo simulation
- ✅ Launched the Reachy Mini simulation daemon
- ✅ Controlled the robot programmatically
- ✅ Run the complete validation suite
- ✅ Connected Claude AI to control the robot

## Understanding the Architecture

Here's what you built:

```
┌─────────────────────────────────────────────┐
│              Your Code / Claude              │
│     (Python scripts, Agent SDK, MCP)         │
└────────────────────┬────────────────────────┘
                     │ HTTP API
                     ▼
┌─────────────────────────────────────────────┐
│          Reachy Daemon (FastAPI)             │
│     Running on localhost:8765                │
└────────────────────┬────────────────────────┘
                     │ Physics Commands
                     ▼
┌─────────────────────────────────────────────┐
│           MuJoCo Physics Engine              │
│     Simulates robot physics                  │
└─────────────────────────────────────────────┘
```

## Next Steps

Now that you have a working development environment:

### Try These Variations
- Modify `scripts/live_demo.py` to create your own movement sequences
- Edit the prompt in `scripts/validate_agent_e2e.py` to try different emotions
- Create expressions like "confused", "happy", or "sleepy"

### Explore the Codebase
- `src/reachy_agent/simulation/reachy_client.py` - The robot control API
- `src/reachy_agent/mcp_servers/reachy/reachy_mcp.py` - MCP tool definitions (23 tools)
- `src/reachy_agent/mcp_servers/reachy/__main__.py` - Standalone MCP server entry point
- `src/reachy_agent/agent/agent.py` - Agent loop with MCP client integration
- `src/reachy_agent/permissions/tiers.py` - Permission system

### Continue Learning
- [Architecture Overview](../architecture/overview.md) - Understand the full system
- [MCP Tools Reference](../../ai_docs/mcp-tools-quick-ref.md) - All 23 available tools
- [Phase 2 Preparation](../guides/phase2-preparation.md) - Hardware integration

---

## Troubleshooting

### Issue: `mjpython: command not found`

**Solution**: Install MuJoCo via Homebrew:
```bash
brew install mujoco
```

Then verify:
```bash
which mjpython
```

### Issue: `ModuleNotFoundError: No module named 'reachy_mini'`

**Solution**: Install reachy-mini in the system Python:
```bash
/opt/homebrew/bin/pip3 install reachy-mini
```

### Issue: `Connection refused` when testing daemon

**Solution**: Make sure the simulation is running in another terminal:
```bash
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main --sim --scene minimal --fastapi-port 8765
```

### Issue: `ANTHROPIC_API_KEY not set`

**Solution**: Set the environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
```

### Issue: Robot movements are too fast to see

**Solution**: In your scripts, add `await asyncio.sleep(2.0)` between movements:
```python
await client.move_head("left")
await asyncio.sleep(2.0)  # Wait 2 seconds
await client.move_head("right")
```

### Issue: MuJoCo window doesn't appear (Linux)

**Solution**: Make sure you have a display server running. Try:
```bash
export DISPLAY=:0
python -m reachy_mini.daemon.app.main --sim --scene minimal --fastapi-port 8765
```

---

## Connecting to Real Hardware

Once you've tested with simulation, you can connect to real Reachy Mini hardware.

### From Your Development Machine

The robot's daemon is accessible over the network:

```bash
# Test daemon connectivity (replace with your robot's hostname)
curl http://reachy-mini.local:8000/api/daemon/status

# Run agent pointing to real hardware
REACHY_DAEMON_URL=http://reachy-mini.local:8000 python -m reachy_agent run
```

### From the Robot's Raspberry Pi (SSH)

For headless operation, SSH into the robot:

```bash
ssh pollen@reachy-mini.local
# Password: root

cd ~/reachy_agent
source .venv/bin/activate
python -m reachy_agent run
```

### Key Differences: Simulation vs Real Hardware

| Aspect | Simulation | Real Hardware |
|--------|------------|---------------|
| Port | 8765 | 8000 |
| Movement API | `/api/move/goto` | `/api/move/set_target` |
| Backend | Mock daemon | Pollen daemon |

The agent auto-detects which backend is running and uses the appropriate API for smooth movements.

### Troubleshooting Real Hardware

If the robot becomes unresponsive:

1. Open `http://reachy-mini.local:8000/settings` in your browser
2. Toggle the On/Off switch off, then on
3. Run `wake_up` command to re-enable motor control

See the [Troubleshooting Guide](../guides/troubleshooting.md) for more solutions.

---

## Complete Reference Script

Here's a complete script you can use as a starting point:

```python
#!/usr/bin/env python3
"""My first Reachy robot script."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reachy_agent.simulation.reachy_client import ReachyMiniClient


async def main():
    """Control the Reachy robot."""
    # Connect to simulation
    client = ReachyMiniClient(base_url="http://localhost:8765")

    try:
        # Wake up
        print("Waking up...")
        await client.wake_up()
        await asyncio.sleep(1)

        # Your movements here
        print("Looking around...")
        await client.move_head("left", speed="normal")
        await asyncio.sleep(1)

        await client.move_head("right", speed="normal")
        await asyncio.sleep(1)

        # Express something
        print("Expressing curiosity...")
        await client.set_antenna_state(left_angle=30, right_angle=80)
        await client.look_at(roll=10, pitch=-5, yaw=20)
        await asyncio.sleep(2)

        # Return to rest
        print("Resting...")
        await client.rest()

    finally:
        await client.close()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
```

Save this as `my_first_script.py` in the project's `scripts/` folder and run:
```bash
python scripts/my_first_script.py
```

Happy robot programming! 🤖
