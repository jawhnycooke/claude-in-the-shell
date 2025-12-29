# Troubleshooting Guide

Common issues and solutions for the Reachy Agent.

## Quick Diagnostics

Run the health check first:

```bash
python -m reachy_agent check
```

This validates:
- Configuration loading
- Anthropic API key
- Daemon connectivity

## Connection Issues

### "Connection refused on port 8000"

**Cause**: No daemon running on the production port.

**Solutions**:

1. Start mock daemon for testing:
   ```bash
   python -m reachy_agent run --mock
   ```

2. Or start MuJoCo simulation (adjust port):
   ```bash
   /opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main \
     --sim --scene minimal --fastapi-port 8000
   ```

3. On Raspberry Pi, check daemon service:
   ```bash
   sudo systemctl status reachy-daemon
   sudo systemctl restart reachy-daemon
   ```

### "Connection refused on port 8765"

**Cause**: MuJoCo simulation not running.

**Solution**: Start the simulation:

```bash
# macOS with GUI
/opt/homebrew/bin/mjpython -m reachy_mini.daemon.app.main \
  --sim --scene minimal --fastapi-port 8765

# Headless (CI/SSH)
python -m reachy_mini.daemon.app.main \
  --sim --scene minimal --headless --fastapi-port 8765
```

### "Timeout connecting to daemon"

**Cause**: Daemon is slow or network issues.

**Solutions**:

1. Increase timeout in `config/default.yaml`:
   ```yaml
   daemon:
     timeout_seconds: 60
   ```

2. Check network connectivity:
   ```bash
   curl -v http://localhost:8765/health
   ```

## Permission Issues

### "Permission denied for tool X"

**Cause**: Tool is Tier 4 (Forbidden) or needs confirmation.

**Solutions**:

1. Check permission tier in `config/permissions.yaml`

2. For Tier 3 tools, user confirmation is required via CLI or web UI

3. Adjust permission rules if appropriate:
   ```yaml
   rules:
     - pattern: "mcp__reachy__<tool>"
       tier: 1  # Change to autonomous
   ```

### "Confirmation timeout"

**Cause**: User didn't respond within 60 seconds.

**Solutions**:

1. Use the web dashboard for easier confirmation dialogs

2. Increase timeout in permission config:
   ```yaml
   confirmation_timeout_seconds: 120
   ```

3. Check if CLI confirmation handler is properly configured

## API Issues

### "ANTHROPIC_API_KEY not set"

**Cause**: Missing or invalid API key.

**Solutions**:

1. Set environment variable:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   ```

2. Or add to `.env` file:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

3. Verify key is valid:
   ```bash
   python -c "import anthropic; print(anthropic.Anthropic().models.list())"
   ```

### "Rate limit exceeded"

**Cause**: Too many API requests.

**Solutions**:

1. Wait and retry (automatic backoff)

2. Check your API tier limits at console.anthropic.com

3. Reduce request frequency in conversations

### "Model not found"

**Cause**: Invalid model name in config.

**Solution**: Use a valid model in `config/default.yaml`:
```yaml
agent:
  model: claude-sonnet-4-20250514  # or claude-3-haiku-20240307
```

## Memory Issues

### "ChromaDB initialization failed"

**Cause**: Disk space, permissions, or corrupted data.

**Solutions**:

1. Check disk space:
   ```bash
   df -h ~/.reachy
   ```

2. Reset ChromaDB (loses memories):
   ```bash
   rm -rf ~/.reachy/memory/chroma
   python -m reachy_agent run
   ```

3. Check directory permissions:
   ```bash
   chmod 755 ~/.reachy/memory
   ```

### "Embedding model not found"

**Cause**: sentence-transformers not installed or model not downloaded.

**Solutions**:

1. Install dependencies:
   ```bash
   uv pip install sentence-transformers
   ```

2. Pre-download model:
   ```bash
   python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
   ```

### "SQLite database locked"

**Cause**: Multiple processes accessing the database.

**Solutions**:

1. Find processes:
   ```bash
   lsof ~/.reachy/memory/reachy.db
   ```

2. Kill conflicting processes:
   ```bash
   kill <PID>
   ```

3. Or wait for other processes to finish

## MCP Server Issues

### "MCP server failed to start"

**Cause**: Import errors or missing dependencies.

**Solutions**:

1. Test MCP server directly:
   ```bash
   python -m reachy_agent.mcp_servers.reachy
   ```

2. Check for import errors:
   ```bash
   python -c "from reachy_agent.mcp_servers.reachy import reachy_mcp"
   ```

3. Reinstall dependencies:
   ```bash
   uv pip install -r requirements.txt
   ```

### "Tool not found: mcp__reachy__X"

**Cause**: MCP server not registered or tool renamed.

**Solutions**:

1. Check available tools:
   ```bash
   # Run MCP Inspector
   npx @modelcontextprotocol/inspector \
     .venv/bin/python -m reachy_agent.mcp_servers.reachy
   ```

2. Verify tool name in `reachy_mcp.py`

## Hardware Issues

### Robot Becomes Unresponsive ("channel closed")

**Cause**: Communication channel between daemon and motors lost. Motors go limp and commands fail.

**Solutions** (in order of preference):

1. **Web UI Recovery** (Fastest):
   ```
   Open browser: http://reachy-mini.local:8000/settings
   Toggle the On/Off switch: Off, then On
   ```

2. **SSH Recovery**:
   ```bash
   ssh pollen@reachy-mini.local
   # Password: root
   sudo systemctl restart reachy-mini-daemon
   ```

3. **Physical Reset** (Last resort):
   - Power cycle the robot using the hardware power switch
   - Wait 10 seconds before powering back on

After recovery, run `wake_up` to re-enable motor control.

### "Motor not responding"

**Cause**: Hardware disconnection or power issue.

**Solutions**:

1. Check daemon status:
   ```bash
   curl http://localhost:8000/api/daemon/status
   ```

2. Restart the daemon:
   ```bash
   sudo systemctl restart reachy-mini-daemon
   ```

3. Check power and connections on the robot

### "Camera frame capture failed"

**Cause**: Camera not connected or driver issue.

**Solutions**:

1. Test camera access:
   ```bash
   curl http://localhost:8000/api/camera/capture
   ```

2. On Raspberry Pi, check camera status:
   ```bash
   vcgencmd get_camera
   ```

## Environment Issues

### "ModuleNotFoundError: reachy_agent"

**Cause**: Package not installed or wrong environment.

**Solutions**:

1. Ensure virtual environment is active:
   ```bash
   source .venv/bin/activate
   ```

2. Reinstall package:
   ```bash
   uv pip install -e .
   ```

3. Check Python path:
   ```bash
   python -c "import reachy_agent; print(reachy_agent.__file__)"
   ```

### "mjpython not found"

**Cause**: MuJoCo not installed on macOS.

**Solution**: Install MuJoCo:

```bash
brew install mujoco
# mjpython should be at /opt/homebrew/bin/mjpython
```

## Performance Issues

### "Agent response is slow"

**Cause**: Network latency, model size, or tool execution time.

**Solutions**:

1. Use a faster model:
   ```yaml
   agent:
     model: claude-3-haiku-20240307
   ```

2. Check network latency:
   ```bash
   ping api.anthropic.com
   ```

3. Enable debug logging to identify bottleneck:
   ```bash
   REACHY_DEBUG=1 python -m reachy_agent run
   ```

### "High memory usage"

**Cause**: Large conversation history or memory accumulation.

**Solutions**:

1. Clear conversation history (restart session)

2. Run memory cleanup:
   ```python
   from reachy_agent.memory.manager import MemoryManager
   manager = MemoryManager(...)
   await manager.cleanup()
   ```

## Getting Help

If you're still stuck:

1. Check debug logs:
   ```bash
   REACHY_DEBUG=1 python -m reachy_agent run 2>&1 | tee debug.log
   ```

2. Search existing issues: https://github.com/jawhnycooke/claude-in-the-shell/issues

3. Open a new issue with:
   - Python version: `python --version`
   - Package versions: `uv pip freeze`
   - Full error traceback
   - Steps to reproduce
