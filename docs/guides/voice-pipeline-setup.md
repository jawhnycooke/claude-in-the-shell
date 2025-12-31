# How to Set Up the Voice Pipeline on Reachy Mini

> **Goal**: Enable real-time voice interaction with Reachy Mini using OpenAI's Realtime API
> **Use case**: When you want Reachy to respond to voice commands with wake word detection
> **Time required**: 30-45 minutes (including testing)

## Prerequisites

Before starting, you should:
- Have basic familiarity with Linux command line and YAML configuration
- Have Reachy Mini hardware with USB audio device connected
- Have access to the Raspberry Pi 4 via SSH
- Possess an OpenAI API key with access to the Realtime API
- Understand basic audio concepts (sample rates, device indices)

Required software:
- Reachy Agent installed: `uv pip install -e ".[voice]"`
- ALSA utilities: `sudo apt-get install alsa-utils`
- PyAudio dependencies: `sudo apt-get install portaudio19-dev python3-pyaudio`

Required hardware:
- Reachy Mini with USB Audio device (4-mic array + speaker)
- Microphone for audio input
- Speaker for audio output

## Problem Context

The Reachy Mini voice pipeline enables natural conversation with the robot through:
1. Wake word detection (e.g., "Hey Motoko", "Hey Batou")
2. Real-time speech-to-text using OpenAI's Realtime API
3. Claude-powered responses with persona-based personalities
4. Text-to-speech playback through the robot's speaker
5. Audio-reactive head wobble animations during speech

This setup is essential for autonomous voice interaction without requiring manual input.

## Solution Overview

We'll configure the voice pipeline by:
1. Identifying audio hardware device indices
2. Configuring ALSA for shared device access
3. Setting up wake word models
4. Configuring voice pipeline settings in `config/default.yaml`
5. Testing the complete pipeline

**Why this approach**: Reachy's daemon and the voice pipeline need simultaneous access to the same audio hardware. ALSA's dsnoop/dmix plugins enable this shared access, preventing "Device or resource busy" errors.

## Step 1: Identify Audio Devices

Find your audio device indices using ALSA utilities.

```bash
# List all audio capture devices (microphones)
arecord -l

# Expected output on Reachy Mini:
# card 2: Device [USB Audio Device], device 0: USB Audio [USB Audio]
#   Subdevices: 1/1
#   Subdevice #0: subdevice #0

# List all playback devices (speakers)
aplay -l

# Expected output on Reachy Mini:
# card 2: Device [USB Audio Device], device 0: USB Audio [USB Audio]
#   Subdevices: 1/1
#   Subdevice #0: subdevice #0
```

**Note the card and device numbers** - you'll need these for ALSA configuration.

For Reachy Mini with USB Audio:
- Typical card number: `2`
- Typical device number: `0`

**Expected result**: You have identified the card and device numbers for both microphone and speaker.

## Step 2: Configure ALSA for Shared Access

Create or edit `/home/reachy/.asoundrc` to enable device sharing between the daemon and voice pipeline.

```bash
# Create ALSA configuration
nano ~/.asoundrc
```

Add this configuration (adjust `card 2` to match your hardware):

```
# Shared microphone input (dsnoop)
pcm.dsnoop_mic {
    type dsnoop
    ipc_key 5678
    slave {
        pcm "hw:2,0"
        channels 1
        rate 16000
        format S16_LE
    }
}

# Shared speaker output (dmix)
pcm.dmix_speaker {
    type dmix
    ipc_key 5679
    slave {
        pcm "hw:2,0"
        channels 1
        rate 24000
        format S16_LE
    }
}

# Make shared devices the defaults
pcm.!default {
    type asym
    playback.pcm "dmix_speaker"
    capture.pcm "dsnoop_mic"
}

ctl.!default {
    type hw
    card 2
}
```

**Key parameters explained**:
- `ipc_key`: Unique identifier for shared memory (must be unique per device)
- `hw:2,0`: Hardware device (card 2, device 0)
- `rate`: Sample rate must match voice pipeline config
- `channels`: 1 for mono, 2 for stereo

**Verify it worked**:

```bash
# Test microphone capture (Ctrl+C to stop)
arecord -D dsnoop_mic -f S16_LE -r 16000 -c 1 test.wav

# Test speaker playback
aplay -D dmix_speaker test.wav
```

If you hear clean audio playback, the ALSA configuration is working.

## Step 3: Find PyAudio Device Indices

The voice pipeline uses PyAudio, which has different device indices than ALSA. Find the correct indices:

```bash
# List PyAudio devices
python3 -c "
import pyaudio
p = pyaudio.PyAudio()
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f'{i}: {info[\"name\"]} (in:{info[\"maxInputChannels\"]}, out:{info[\"maxOutputChannels\"]})')
p.terminate()
"
```

**Expected output**:
```
0: bcm2835 Headphones (in:0, out:8)
1: bcm2835 Headphones (in:0, out:8)
2: sysdefault (in:128, out:128)
3: dmix_speaker (in:0, out:2)
4: dsnoop_mic (in:2, out:0)
5: default (in:32, out:32)
```

**For Reachy Mini USB Audio**:
- Input device index: `4` (dsnoop_mic)
- Output device index: `3` (dmix_speaker)

**Expected result**: You have the PyAudio device indices for both input and output.

## Step 4: Set Up Wake Word Models

The voice pipeline supports custom wake word models for persona-based interaction.

```bash
# Navigate to wake word models directory
cd /home/reachy/reachy_project/data/wake_words/

# Check bundled models
ls -lh

# Expected files:
# hey_motoko.onnx    - "Hey Motoko" wake word
# hey_batou.onnx     - "Hey Batou" wake word
# README.md          - Documentation
```

**Bundled models** (Ghost in the Shell theme):
- `hey_motoko.onnx` - Female persona (analytical, philosophical)
- `hey_batou.onnx` - Male persona (casual, action-oriented)

If you need to add custom wake word models:

```bash
# Download or copy your custom .onnx model
cp /path/to/custom_wake_word.onnx data/wake_words/

# Model filename must match the wake word key in config
# Example: "hey_jarvis" requires hey_jarvis.onnx
```

**Training custom wake words** (advanced):

```bash
# Clone OpenWakeWord repository
git clone https://github.com/dscripka/openWakeWord.git
cd openWakeWord

# Follow training instructions in the repository
# to create custom .onnx models
```

**Fallback behavior**: If custom models are not found, the system falls back to bundled OpenWakeWord models (e.g., "hey jarvis", "alexa").

**Expected result**: Wake word models are in place and ready for loading.

## Step 5: Configure Voice Pipeline Settings

Edit `config/default.yaml` to configure the voice pipeline for your hardware.

```bash
# Edit configuration
nano config/default.yaml
```

**Essential configuration sections**:

### Audio Hardware Settings

```yaml
voice:
  audio:
    sample_rate: 16000              # Microphone sample rate
    channels: 1                     # Mono audio
    chunk_size: 512                 # Samples per chunk (Silero VAD requirement)
    format_bits: 16                 # int16 PCM
    input_device_index: 4           # PyAudio index for dsnoop_mic
    output_device_index: 3          # PyAudio index for dmix_speaker
```

### Wake Word Detection Settings

```yaml
voice:
  wake_word:
    enabled: true
    model: hey_jarvis               # Fallback model if persona models missing
    sensitivity: 0.5                # 0.0 (strict) to 1.0 (lenient)
    cooldown_seconds: 2.0           # Ignore detections for this period
    custom_models_dir: data/wake_words
```

**Sensitivity tuning**:
- `0.3-0.4`: Very strict (fewer false positives, may miss some detections)
- `0.5`: Balanced (recommended starting point)
- `0.6-0.7`: Lenient (more detections, possible false positives)

### Voice Activity Detection (VAD)

```yaml
voice:
  vad:
    silence_threshold_ms: 800       # Silence duration to trigger end-of-speech
    min_speech_duration_ms: 250     # Minimum speech to be valid
    max_speech_duration_s: 30.0     # Maximum before timeout
    speech_threshold: 0.5           # VAD sensitivity (0.0-1.0)
```

**VAD tuning tips**:
- Increase `silence_threshold_ms` if responses cut off too quickly
- Decrease `speech_threshold` if VAD doesn't detect quiet speech
- Increase `speech_threshold` if background noise triggers false detections

### OpenAI Realtime API Settings

```yaml
voice:
  openai:
    model: gpt-4o-realtime-preview-2024-12-17
    voice: nova                     # Options: alloy, echo, fable, onyx, nova, shimmer
    sample_rate: 24000              # OpenAI uses 24kHz
    temperature: 0.8                # Response creativity
    max_response_tokens: 4096       # Max response length
    turn_detection_threshold: 0.5
    turn_detection_silence_ms: 500
```

### Persona Configuration (Multi-Wake Word)

```yaml
voice:
  personas:
    hey_motoko:
      name: motoko
      display_name: Major Kusanagi
      voice: nova                   # Female voice
      prompt_path: prompts/personas/motoko.md
    hey_batou:
      name: batou
      display_name: Batou
      voice: onyx                   # Male voice
      prompt_path: prompts/personas/batou.md

  default_persona: hey_motoko       # Used before any wake word detected
```

### Degraded Mode (Fallback Behavior)

```yaml
voice:
  degraded_mode:
    skip_wake_word_on_failure: true       # Switch to always-listening if wake word fails
    use_energy_vad_fallback: true         # Use energy-based VAD if Silero unavailable
    log_response_on_tts_failure: true     # Log response text if TTS fails
```

**Expected result**: Voice pipeline is fully configured for your hardware and preferences.

## Step 6: Set OpenAI API Key

The voice pipeline requires an OpenAI API key with Realtime API access.

```bash
# Set API key in environment
export OPENAI_API_KEY="sk-proj-your-api-key-here"

# Or add to .bashrc for persistence
echo 'export OPENAI_API_KEY="sk-proj-your-api-key-here"' >> ~/.bashrc
source ~/.bashrc

# Verify it's set
echo $OPENAI_API_KEY
```

**Security note**: Never commit API keys to version control. Use environment variables or `.env` files (excluded from git).

**Expected result**: OpenAI API key is configured and accessible.

## Step 7: Test the Voice Pipeline

Run the voice pipeline with debug logging to verify everything works.

```bash
# Run with voice mode enabled and debug output
REACHY_DEBUG=1 python -m reachy_agent run --voice
```

**Expected console output**:

```
[INFO] audio_manager_initialized device_count=6
[INFO] wake_word_detector_initialized model=hey_motoko sensitivity=0.5
[INFO] voice_pipeline_started default_persona=hey_motoko
[INFO] listening_for_wake_word state=passive
```

**Test sequence**:

1. **Wake word detection**: Say "Hey Motoko" clearly into the microphone
   - Expected: `[INFO] wake_word_detected model=hey_motoko confidence=0.87`
   - Expected: Confirmation beep sound

2. **Speech input**: Speak a question (e.g., "What time is it?")
   - Expected: `[INFO] speech_detected duration_ms=2150`
   - Expected: `[INFO] processing_speech transcription="What time is it?"`

3. **Response generation**: Wait for Claude to generate a response
   - Expected: `[INFO] response_received tokens=45`

4. **TTS playback**: Listen for voice response through speaker
   - Expected: `[INFO] tts_playback_started voice=nova`
   - Expected: Head wobble animation during speech
   - Expected: `[INFO] tts_playback_completed duration_s=3.2`

5. **Return to listening**: Pipeline returns to wake word detection
   - Expected: `[INFO] listening_for_wake_word state=passive`

**Success criteria**: Complete wake-to-response-to-listen cycle works without errors.

## Verification

Confirm your voice pipeline is fully operational:

```bash
# Check audio levels during recording
REACHY_DEBUG=1 python -m reachy_agent run --voice 2>&1 | grep audio_level

# Expected output (when speaking):
# [DEBUG] audio_level level=0.42 state=speech
# [DEBUG] audio_level level=0.38 state=speech

# Test wake word sensitivity
python3 -c "
from reachy_agent.voice.wake_word import WakeWordDetector
from reachy_agent.config import load_config

config = load_config()
detector = WakeWordDetector(config.voice.wake_word)
print(f'Models loaded: {list(detector._models.keys())}')
"
# Expected output: Models loaded: ['hey_motoko', 'hey_batou']
```

## Troubleshooting

### Problem: "Device or resource busy" on audio device

**Symptoms**: PyAudio fails to open stream with error "Device or resource busy"

**Cause**: Multiple processes trying to access the same audio device without ALSA sharing

**Solution**: Ensure dsnoop/dmix configuration is correct

```bash
# Check if daemon is using the device
sudo lsof /dev/snd/*

# Kill any conflicting processes
sudo pkill -f reachy_daemon

# Verify ALSA configuration
cat ~/.asoundrc

# Test shared access
arecord -D dsnoop_mic -f S16_LE -r 16000 -c 1 -d 3 test.wav &
arecord -D dsnoop_mic -f S16_LE -r 16000 -c 1 -d 3 test2.wav &
# Both should succeed
```

### Problem: Audio cuts off at the beginning of TTS playback

**Symptoms**: First syllable or word is missing from TTS output

**Cause**: Speaker takes time to initialize; audio buffer starts playing before speaker is ready

**Solution**: The pipeline includes a built-in lead-in buffer, but you can adjust:

```yaml
voice:
  audio:
    playback_lead_in_ms: 200  # Increase if audio still cuts off
```

### Problem: Wake word detection has too many false positives

**Symptoms**: Wake word triggers on background noise or similar-sounding words

**Cause**: Sensitivity is too high, cooldown is too short

**Solution**: Adjust sensitivity and cooldown

```yaml
voice:
  wake_word:
    sensitivity: 0.4            # Lower = more strict (was 0.5)
    cooldown_seconds: 3.0       # Longer cooldown (was 2.0)
```

**Test different sensitivity values**:

```bash
# Quick sensitivity test
python3 -c "
from reachy_agent.voice.wake_word import WakeWordDetector, WakeWordConfig

# Test with strict sensitivity
config = WakeWordConfig(sensitivity=0.3)
detector = WakeWordDetector(config)
print('Testing strict mode (0.3)...')
# Speak wake word and observe detection rate
"
```

### Problem: Wake word detection misses valid detections

**Symptoms**: You say the wake word clearly but it doesn't trigger

**Cause**: Sensitivity is too low, model doesn't match your voice/accent

**Solution**: Increase sensitivity or retrain wake word model

```yaml
voice:
  wake_word:
    sensitivity: 0.6            # Higher = more lenient (was 0.5)
```

**Verify microphone input**:

```bash
# Record test audio to check microphone quality
arecord -D dsnoop_mic -f S16_LE -r 16000 -c 1 -d 5 wake_word_test.wav

# Play back to verify clarity
aplay wake_word_test.wav
```

### Problem: Echo or feedback during conversation

**Symptoms**: Robot's voice is picked up by microphone, triggering false detections

**Cause**: Speaker output is too loud or microphone is too sensitive

**Solution**: Reduce speaker volume or enable acoustic echo suppression

```bash
# Reduce ALSA speaker volume
amixer -D hw:2 set Speaker 80%

# Or in config (if implemented):
voice:
  audio:
    output_volume: 0.8          # 80% volume
```

**Advanced solution**: Implement acoustic echo cancellation (AEC) using software like PulseAudio or custom filters.

### Problem: High latency between speech and response

**Symptoms**: 5+ second delay between finishing speech and hearing response

**Cause**: Network latency to OpenAI API, model processing time, or CPU throttling

**Solution**: Optimize configuration and check system resources

```yaml
voice:
  openai:
    model: gpt-4o-mini-realtime  # Faster model (if available)
    max_response_tokens: 512     # Shorter responses (was 4096)
```

**Check Raspberry Pi thermal throttling**:

```bash
# Monitor temperature during operation
vcgencmd measure_temp

# Check for throttling
vcgencmd get_throttled
# 0x0 = no throttling (good)
# Non-zero = throttling active
```

**Improve thermal performance**:
- Add heatsink to Raspberry Pi
- Ensure adequate ventilation
- Reduce CPU load by disabling unnecessary services

### Problem: "ImportError: No module named 'pyaudio'"

**Symptoms**: Voice pipeline fails to start with PyAudio import error

**Cause**: PyAudio not installed or missing system dependencies

**Solution**: Install PyAudio and dependencies

```bash
# Install system dependencies
sudo apt-get update
sudo apt-get install portaudio19-dev python3-pyaudio

# Install Python package
uv pip install pyaudio

# Or reinstall voice extras
uv pip install -e ".[voice]"
```

### Problem: OpenAI API key not found

**Symptoms**: Error message "openai_api_key_missing" in logs

**Cause**: OPENAI_API_KEY environment variable not set

**Solution**: Set the environment variable

```bash
# Temporary (current session only)
export OPENAI_API_KEY="sk-proj-your-key-here"

# Permanent (add to .bashrc)
echo 'export OPENAI_API_KEY="sk-proj-your-key-here"' >> ~/.bashrc
source ~/.bashrc

# Verify
env | grep OPENAI
```

## Raspberry Pi Specific Setup

### USB Audio Device Indices

On Raspberry Pi 4 with Reachy Mini USB Audio:

```bash
# Typical device configuration:
# Card 0: bcm2835 (onboard)
# Card 1: bcm2835 (onboard HDMI)
# Card 2: USB Audio Device (Reachy's 4-mic array + speaker)

# PyAudio indices (after dsnoop/dmix setup):
# Index 3: dmix_speaker (output)
# Index 4: dsnoop_mic (input)
```

**Verify your specific indices**:

```bash
python3 -c "
import pyaudio
p = pyaudio.PyAudio()
print('Input devices:')
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxInputChannels'] > 0:
        print(f'  {i}: {info[\"name\"]}')
print('Output devices:')
for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    if info['maxOutputChannels'] > 0:
        print(f'  {i}: {info[\"name\"]}')
p.terminate()
"
```

### Thermal Management

Voice processing is CPU-intensive. Monitor and manage thermals:

```bash
# Install monitoring tools
sudo apt-get install libraspberrypi-bin

# Check current temperature
vcgencmd measure_temp

# Monitor continuously (Ctrl+C to stop)
watch -n 1 vcgencmd measure_temp

# Check throttling status
vcgencmd get_throttled
```

**Temperature guidelines**:
- < 60°C: Normal operation
- 60-70°C: Warm but acceptable
- 70-80°C: Consider cooling improvements
- > 80°C: CPU will throttle (performance degradation)

**Cooling improvements**:
- Install heatsink on Raspberry Pi SoC
- Add active cooling fan
- Improve case ventilation
- Reduce room temperature

### Systemd Service Configuration

Run the voice pipeline as a system service for automatic startup:

```bash
# Create service file
sudo nano /etc/systemd/system/reachy-voice.service
```

Add this configuration:

```ini
[Unit]
Description=Reachy Voice Pipeline
After=network.target reachy-daemon.service
Wants=reachy-daemon.service

[Service]
Type=simple
User=reachy
Group=reachy
WorkingDirectory=/home/reachy/reachy_project
Environment="OPENAI_API_KEY=sk-proj-your-key-here"
Environment="REACHY_DEBUG=0"
ExecStart=/home/reachy/reachy_project/.venv/bin/python -m reachy_agent run --voice
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start the service**:

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable reachy-voice

# Start service now
sudo systemctl start reachy-voice

# Check status
sudo systemctl status reachy-voice

# View logs
sudo journalctl -u reachy-voice -f
```

**Service management commands**:

```bash
# Stop service
sudo systemctl stop reachy-voice

# Restart service
sudo systemctl restart reachy-voice

# Disable autostart
sudo systemctl disable reachy-voice

# View recent logs
sudo journalctl -u reachy-voice -n 100
```

## Alternative Approaches

### For Limited Internet Connectivity

If you have unreliable internet or want to reduce API costs, consider local alternatives:

**Approach**: Use local Whisper STT + Piper TTS instead of OpenAI Realtime API

**Pros**:
- No internet required after model download
- No API costs
- Better privacy (data stays on device)

**Cons**:
- Higher latency (separate STT/LLM/TTS calls)
- Requires more storage and RAM
- Potentially lower quality

**When to use**: Offline demos, privacy-critical applications, or high-volume usage

**Configuration**:

```yaml
voice:
  stt_backend: whisper_local  # Instead of openai_realtime
  tts_backend: piper          # Local TTS
```

### For High-Volume Usage

For applications requiring many hours of conversation per day:

**Approach**: Use cheaper STT/TTS services (Azure, Google Cloud)

**Trade-offs**:
- Lower cost per hour
- May require additional API setup
- Different voice quality characteristics

**When to use**: Production deployments, extended conversations, cost-sensitive applications

### For Custom Wake Words

If bundled wake words don't fit your use case:

**Approach**: Train custom wake word models with OpenWakeWord

**Pros**:
- Exact phrase matching your needs
- Brand-specific wake words
- Better accuracy for unusual names/phrases

**Cons**:
- Requires training data collection
- Time investment for model training
- May need multiple training iterations

**When to use**: Commercial products, non-English languages, brand-specific wake words

## Best Practices

- **Audio Quality**: Use a quality USB audio device with noise cancellation for best results
- **Wake Word Choice**: Choose wake words with 3+ syllables and distinct phonemes (avoid common words)
- **Testing**: Always test with different speakers, accents, and background noise levels
- **Monitoring**: Enable debug logging during initial setup, then disable for production
- **Security**: Never commit API keys to version control; use environment variables or secrets management
- **Performance**: Monitor CPU and memory usage; adjust config for available resources
- **Fallbacks**: Enable degraded mode settings for graceful handling of component failures
- **Updates**: Keep wake word models updated; retrain if detection accuracy degrades

**Important**: The voice pipeline shares audio hardware with the Reachy daemon. Always use dsnoop/dmix ALSA configuration to prevent resource conflicts.

## Related Tasks

- [Raspberry Pi Installation](raspberry-pi-installation.md) - Initial Reachy setup
- [Troubleshooting Guide](troubleshooting.md) - General debugging procedures

## Further Reading

- **New to Reachy Agent?** Start with [Getting Started Tutorial](/Users/jawhny/Documents/projects/reachy_project/docs/tutorials/getting-started.md)
- **Need technical details?** Check the [MCP Tools Reference](/Users/jawhny/Documents/projects/reachy_project/docs/api/mcp-tools.md)
- **Want to understand agent behavior?** Read [Agent Behavior Guide](/Users/jawhny/Documents/projects/reachy_project/ai_docs/agent-behavior.md)
- **OpenAI Realtime API**: [Official Documentation](https://platform.openai.com/docs/guides/realtime)
- **OpenWakeWord**: [GitHub Repository](https://github.com/dscripka/openWakeWord)
