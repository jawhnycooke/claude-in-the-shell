# Configuration Reference

Complete reference for all configuration options in `config/default.yaml`.

## Configuration File Location

The agent looks for configuration in the following order:

1. `~/.reachy/config.yaml` (user override)
2. `config/default.yaml` (project defaults)

## Agent Settings

Core agent configuration:

```yaml
agent:
  name: Jarvis              # Agent's name for personality
  wake_word: hey jarvis     # Wake word phrase
  model: claude-haiku-4-5-20251001  # Claude model to use
  max_tokens: 512           # Max tokens per response
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `name` | string | `"Jarvis"` | Agent's display name |
| `wake_word` | string | `"hey jarvis"` | Wake word phrase |
| `model` | string | `"claude-haiku-4-5-20251001"` | Claude model ID |
| `max_tokens` | int | `512` | Maximum response tokens |

## Perception Settings

Sensor and detection configuration:

```yaml
perception:
  wake_word_engine: openwakeword
  wake_word_sensitivity: 0.5
  spatial_audio_enabled: true
  vision_enabled: true
  face_detection_enabled: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `wake_word_engine` | string | `"openwakeword"` | Wake word engine (`openwakeword`, `porcupine`) |
| `wake_word_sensitivity` | float | `0.5` | Detection sensitivity (0.0-1.0) |
| `spatial_audio_enabled` | bool | `true` | Enable spatial audio processing |
| `vision_enabled` | bool | `true` | Enable camera for vision |
| `face_detection_enabled` | bool | `true` | Enable face detection |

## Memory Settings

Semantic memory and profile storage:

```yaml
memory:
  chroma_path: ~/.reachy/memory/chroma
  sqlite_path: ~/.reachy/memory/reachy.db
  embedding_model: all-MiniLM-L6-v2
  max_memories: 10000
  retention_days: 90
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `chroma_path` | path | `~/.reachy/memory/chroma` | ChromaDB storage directory |
| `sqlite_path` | path | `~/.reachy/memory/reachy.db` | SQLite database path |
| `embedding_model` | string | `"all-MiniLM-L6-v2"` | Sentence transformer model |
| `max_memories` | int | `10000` | Maximum stored memories |
| `retention_days` | int | `90` | Memory retention period |

## Attention State Settings

Attention state transitions:

```yaml
attention:
  passive_to_alert_motion_threshold: 0.3
  alert_to_passive_timeout_minutes: 5
  engaged_to_alert_silence_seconds: 30
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `passive_to_alert_motion_threshold` | float | `0.3` | Motion detection threshold |
| `alert_to_passive_timeout_minutes` | int | `5` | Minutes before returning to passive |
| `engaged_to_alert_silence_seconds` | int | `30` | Silence before disengaging |

## Resilience Settings

Error handling and thermal management:

```yaml
resilience:
  thermal_threshold_celsius: 80.0
  api_timeout_seconds: 30.0
  max_retries: 3
  offline_llm_model: llama3.2:3b
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `thermal_threshold_celsius` | float | `80.0` | CPU thermal throttle threshold |
| `api_timeout_seconds` | float | `30.0` | API request timeout |
| `max_retries` | int | `3` | Maximum retry attempts |
| `offline_llm_model` | string | `"llama3.2:3b"` | Offline LLM fallback |

## Privacy Settings

Audit logging and data storage:

```yaml
privacy:
  audit_logging_enabled: true
  audit_retention_days: 7
  store_audio: false
  store_images: false
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `audit_logging_enabled` | bool | `true` | Enable audit logging |
| `audit_retention_days` | int | `7` | Audit log retention |
| `store_audio` | bool | `false` | Store audio recordings |
| `store_images` | bool | `false` | Store captured images |

## Motion Blend Settings

Motion orchestration configuration:

```yaml
motion_blend:
  enabled: true
  tick_rate_hz: 100.0
  command_rate_hz: 20.0
  smoothing_factor: 0.3
  pose_limits:
    pitch_range: [-45, 45]
    yaw_range: [-45, 45]
    roll_range: [-30, 30]
    z_range: [-50, 50]
    antenna_range: [0, 90]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable motion blending |
| `tick_rate_hz` | float | `100.0` | Internal loop rate |
| `command_rate_hz` | float | `20.0` | Daemon command rate |
| `smoothing_factor` | float | `0.3` | Pose interpolation factor |
| `pose_limits.pitch_range` | [float, float] | `[-45, 45]` | Pitch safety limits (degrees) |
| `pose_limits.yaw_range` | [float, float] | `[-45, 45]` | Yaw safety limits (degrees) |
| `pose_limits.roll_range` | [float, float] | `[-30, 30]` | Roll safety limits (degrees) |
| `pose_limits.z_range` | [float, float] | `[-50, 50]` | Z offset limits (mm) |
| `pose_limits.antenna_range` | [float, float] | `[0, 90]` | Antenna limits (degrees) |

## Idle Behavior Settings

Autonomous look-around behavior:

```yaml
idle_behavior:
  enabled: true
  min_look_interval: 3.0
  max_look_interval: 8.0
  movement_duration: 1.5
  yaw_range: [-35, 35]
  pitch_range: [-15, 20]
  roll_range: [-8, 8]
  curiosity_chance: 0.15
  double_look_chance: 0.10
  return_to_neutral_chance: 0.25
  curiosity_intensity: 0.6
  curiosity_emotions:
    - curious
    - thinking
    - recognition
  pause_on_interaction: true
  interaction_cooldown: 2.0
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable idle behavior |
| `min_look_interval` | float | `3.0` | Minimum seconds between looks |
| `max_look_interval` | float | `8.0` | Maximum seconds between looks |
| `movement_duration` | float | `1.5` | Look movement duration |
| `yaw_range` | [float, float] | `[-35, 35]` | Left/right range (degrees) |
| `pitch_range` | [float, float] | `[-15, 20]` | Down/up range (degrees) |
| `roll_range` | [float, float] | `[-8, 8]` | Tilt range (degrees) |
| `curiosity_chance` | float | `0.15` | Probability of curiosity emotion |
| `pause_on_interaction` | bool | `true` | Pause during user interaction |

## Breathing Motion Settings

Subtle idle animation:

```yaml
breathing:
  enabled: false
  z_amplitude_mm: 5.0
  z_frequency_hz: 0.1
  antenna_amplitude_deg: 15.0
  antenna_frequency_hz: 0.5
  antenna_base_angle: 45.0
  pitch_amplitude_deg: 1.5
  pitch_frequency_hz: 0.12
  yaw_amplitude_deg: 0.8
  yaw_frequency_hz: 0.07
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `false` | Enable breathing animation |
| `z_amplitude_mm` | float | `5.0` | Vertical oscillation amplitude |
| `z_frequency_hz` | float | `0.1` | Breathing cycle frequency |
| `antenna_amplitude_deg` | float | `15.0` | Antenna sway amplitude |
| `antenna_frequency_hz` | float | `0.5` | Antenna cycle frequency |
| `antenna_base_angle` | float | `45.0` | Neutral antenna position |

## Head Wobble Settings

Speech-reactive animation:

```yaml
wobble:
  enabled: true
  max_pitch_deg: 8.0
  max_yaw_deg: 6.0
  max_roll_deg: 4.0
  latency_compensation_ms: 80.0
  smoothing_factor: 0.3
  noise_scale: 0.2
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable head wobble |
| `max_pitch_deg` | float | `8.0` | Maximum pitch displacement |
| `max_yaw_deg` | float | `6.0` | Maximum yaw displacement |
| `max_roll_deg` | float | `4.0` | Maximum roll displacement |
| `latency_compensation_ms` | float | `80.0` | Audio latency compensation |
| `smoothing_factor` | float | `0.3` | Motion smoothing factor |

## Voice Pipeline Settings

Real-time voice interaction:

```yaml
voice:
  enabled: false
  confirmation_beep: true
  auto_restart: true
```

### Persona Configuration

Multi-persona wake word system:

```yaml
voice:
  personas:
    hey_motoko:
      name: motoko
      display_name: Major Kusanagi
      voice: nova
      prompt_path: prompts/personas/motoko.md
    hey_batou:
      name: batou
      display_name: Batou
      voice: onyx
      prompt_path: prompts/personas/batou.md

  default_persona: hey_motoko
```

| Option | Type | Description |
|--------|------|-------------|
| `personas.<key>.name` | string | Internal persona identifier |
| `personas.<key>.display_name` | string | Human-readable name |
| `personas.<key>.voice` | string | OpenAI TTS voice (`alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`) |
| `personas.<key>.prompt_path` | path | Path to persona system prompt |
| `default_persona` | string | Key of default persona |

### Wake Word Configuration

```yaml
voice:
  wake_word:
    enabled: true
    model: hey_jarvis
    sensitivity: 0.5
    cooldown_seconds: 2.0
    custom_models_dir: data/wake_words
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable wake word detection |
| `model` | string | `"hey_jarvis"` | Fallback wake word model |
| `sensitivity` | float | `0.5` | Detection sensitivity (0.0-1.0) |
| `cooldown_seconds` | float | `2.0` | Ignore detections cooldown |
| `custom_models_dir` | path | `"data/wake_words"` | Custom .onnx models directory |

### Voice Activity Detection (VAD)

```yaml
voice:
  vad:
    silence_threshold_ms: 800
    min_speech_duration_ms: 250
    max_speech_duration_s: 30.0
    speech_threshold: 0.5
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `silence_threshold_ms` | int | `800` | Silence to trigger end-of-speech |
| `min_speech_duration_ms` | int | `250` | Minimum valid speech duration |
| `max_speech_duration_s` | float | `30.0` | Maximum before timeout |
| `speech_threshold` | float | `0.5` | VAD sensitivity |

### OpenAI Realtime Configuration

```yaml
voice:
  openai:
    model: gpt-realtime-mini
    voice: alloy
    sample_rate: 24000
    temperature: 0.8
    max_response_tokens: 4096
    turn_detection_threshold: 0.5
    turn_detection_silence_ms: 500
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `model` | string | `"gpt-realtime-mini"` | OpenAI Realtime model |
| `voice` | string | `"alloy"` | TTS voice |
| `sample_rate` | int | `24000` | Audio sample rate |
| `temperature` | float | `0.8` | Response temperature |
| `max_response_tokens` | int | `4096` | Max response length |

### Audio Hardware Configuration

```yaml
voice:
  audio:
    sample_rate: 16000
    channels: 1
    chunk_size: 512
    format_bits: 16
    input_device_index: 4
    output_device_index: 3
    max_init_retries: 3
    retry_delay_seconds: 1.0
    retry_backoff_factor: 2.0
    output_lead_in_ms: 200
    input_warmup_chunks: 5
    health_check_interval_seconds: 5.0
    max_consecutive_errors: 3
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `sample_rate` | int | `16000` | Microphone sample rate |
| `channels` | int | `1` | Audio channels (mono) |
| `chunk_size` | int | `512` | Samples per chunk |
| `input_device_index` | int | `4` | Input device (dsnoop) |
| `output_device_index` | int | `3` | Output device (dmix) |

### Degraded Mode Configuration

```yaml
voice:
  degraded_mode:
    skip_wake_word_on_failure: true
    use_energy_vad_fallback: true
    log_response_on_tts_failure: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `skip_wake_word_on_failure` | bool | `true` | Always-listening if wake word fails |
| `use_energy_vad_fallback` | bool | `true` | Energy-based VAD fallback |
| `log_response_on_tts_failure` | bool | `true` | Log response if TTS fails |

## SDK Motion Control Settings

Direct Python SDK for low-latency motion:

```yaml
sdk:
  enabled: true
  robot_name: reachy_mini
  connect_timeout_seconds: 10.0
  fallback_to_http: true
  max_workers: 1
  localhost_only: true
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `enabled` | bool | `true` | Enable SDK motion control |
| `robot_name` | string | `"reachy_mini"` | Robot name for Zenoh |
| `connect_timeout_seconds` | float | `10.0` | SDK connection timeout |
| `fallback_to_http` | bool | `true` | Fall back to HTTP on failure |
| `max_workers` | int | `1` | Thread pool size |
| `localhost_only` | bool | `true` | Only connect to localhost |

## Integration Settings

External service integrations:

```yaml
integrations:
  home_assistant:
    enabled: false
    url: null
    token_env_var: HA_TOKEN

  google_calendar:
    enabled: false
    credentials_path: null

  github:
    enabled: false
    token_env_var: GITHUB_TOKEN
    repos: []
```

| Integration | Options |
|-------------|---------|
| `home_assistant` | `enabled`, `url`, `token_env_var` |
| `google_calendar` | `enabled`, `credentials_path` |
| `github` | `enabled`, `token_env_var`, `repos` |

## Environment Variables

Key environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key (required) |
| `OPENAI_API_KEY` | OpenAI API key (for voice pipeline) |
| `GITHUB_TOKEN` | GitHub personal access token |
| `HA_TOKEN` | Home Assistant long-lived access token |
| `REACHY_DEBUG` | Enable debug logging |
| `REACHY_CONFIG_PATH` | Override config file path |
