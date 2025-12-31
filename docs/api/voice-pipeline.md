# Voice Pipeline API Reference

## Overview

The Voice Pipeline module provides a complete voice interaction system for the Reachy robot, orchestrating wake word detection, speech recognition, agent processing, and text-to-speech playback. It implements a state machine that coordinates audio capture, voice activity detection, OpenAI Realtime API integration, and error recovery.

**Module**: `reachy_agent.voice.pipeline`

**Key Features**:
- State machine-based pipeline coordination
- Multi-persona support with wake word switching
- Automatic error recovery and degraded mode operation
- Real-time audio streaming with OpenAI Realtime API
- Voice activity detection (VAD) for speech segmentation
- Integration with Reachy motion behaviors

---

## VoicePipeline

Main orchestrator class that coordinates all voice interaction components.

### Constructor

```python
VoicePipeline(
    agent: ReachyAgentLoop | None = None,
    config: VoicePipelineConfig = VoicePipelineConfig(),
    on_state_change: Callable[[VoicePipelineState, VoicePipelineState], None] | None = None,
    on_transcription: Callable[[str], None] | None = None,
    on_response: Callable[[str], None] | None = None,
    on_degraded_mode: Callable[[str, bool], None] | None = None,
)
```

**Parameters**:

- `agent` (ReachyAgentLoop | None): The agent instance for processing user input. Optional for testing.
- `config` (VoicePipelineConfig): Configuration for pipeline components. Default: `VoicePipelineConfig()`
- `on_state_change` (Callable | None): Callback invoked on state transitions with signature `(from_state, to_state)`. Default: None
- `on_transcription` (Callable | None): Callback invoked when user speech is transcribed with signature `(text)`. Default: None
- `on_response` (Callable | None): Callback invoked when agent response text is available with signature `(text)`. Default: None
- `on_degraded_mode` (Callable | None): Callback invoked when a component enters/exits degraded mode with signature `(component, is_degraded)`. Default: None

**Returns**: VoicePipeline instance

**Example**:
```python
from reachy_agent.agent import ReachyAgentLoop
from reachy_agent.voice import VoicePipeline, VoicePipelineConfig

agent = ReachyAgentLoop()
config = VoicePipelineConfig()

pipeline = VoicePipeline(
    agent=agent,
    config=config,
    on_transcription=lambda text: print(f"User said: {text}"),
    on_response=lambda text: print(f"Agent replied: {text}"),
)

await pipeline.initialize()
await pipeline.start()
```

### Properties

#### state

- **Type**: `VoicePipelineState`
- **Access**: Read-only
- **Description**: Current state of the voice pipeline

**Example**:
```python
>>> pipeline.state
<VoicePipelineState.LISTENING_WAKE: 'listening_wake'>
```

#### is_running

- **Type**: `bool`
- **Access**: Read-only
- **Description**: Whether the pipeline main loop is active

**Example**:
```python
>>> pipeline.is_running
True
```

#### is_degraded

- **Type**: `bool`
- **Access**: Read-only
- **Description**: Whether any component is operating in degraded mode

**Example**:
```python
>>> pipeline.is_degraded
False
```

#### degraded_modes

- **Type**: `set[str]`
- **Access**: Read-only
- **Description**: Set of component names currently in degraded mode (e.g., `{"audio", "wake_word"}`)

**Example**:
```python
>>> pipeline.degraded_modes
{"audio"}
```

#### current_persona

- **Type**: `PersonaConfig | None`
- **Access**: Read-only
- **Description**: The currently active persona configuration, or None if no persona is active

**Example**:
```python
>>> pipeline.current_persona.display_name
'Major Kusanagi'
>>> pipeline.current_persona.voice
'nova'
```

### Methods

#### initialize()

```python
async def initialize() -> bool
```

Initialize all pipeline components (audio, wake word, VAD, OpenAI client).

**Returns**: `bool` - True if initialization succeeded (possibly in degraded mode), False if initialization completely failed

**Raises**:
- `AudioDeviceError`: If audio devices cannot be initialized
- `WakeWordError`: If wake word models cannot be loaded
- `VADError`: If VAD model cannot be loaded

**Example**:
```python
>>> success = await pipeline.initialize()
>>> if success:
...     print(f"Initialized, degraded: {pipeline.is_degraded}")
Initialized, degraded: False
```

#### start()

```python
async def start() -> None
```

Start the voice pipeline main loop. Must call `initialize()` first.

**Raises**:
- `RuntimeError`: If pipeline is already running or not initialized
- `StateTransitionError`: If pipeline is in an invalid state for starting

**Example**:
```python
>>> await pipeline.start()
# Pipeline is now listening for wake word
```

#### stop()

```python
async def stop() -> None
```

Stop the voice pipeline main loop and clean up resources.

**Example**:
```python
>>> await pipeline.stop()
# Pipeline has stopped, resources cleaned up
```

#### get_recovery_status()

```python
def get_recovery_status() -> dict
```

Get detailed status of recovery manager and degraded modes.

**Returns**: `dict` - Status report with keys:
- `degraded_modes`: List of component names in degraded mode
- `strategies`: Dict mapping component names to recovery strategy details
- `active_recoveries`: Number of active recovery attempts

**Example**:
```python
>>> status = pipeline.get_recovery_status()
>>> status["degraded_modes"]
['audio']
>>> status["strategies"]["audio"]["attempt"]
2
```

### Context Manager Support

VoicePipeline supports async context manager protocol for automatic resource cleanup:

```python
async with VoicePipeline(agent=agent, config=config) as pipeline:
    await pipeline.start()
    # Pipeline runs...
# Automatically stopped and cleaned up
```

---

## VoicePipelineConfig

Configuration dataclass for all pipeline components.

```python
@dataclass
class VoicePipelineConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)

    # Timeout settings
    listening_timeout: float = 30.0
    processing_timeout: float = 45.0
    playback_timeout: float = 60.0

    # Persona settings
    personas: dict[str, Any] = field(default_factory=dict)
    default_persona: str = ""
```

**Fields**:

- `audio` (AudioConfig): Audio device and recording configuration. See [audio.py](voice-audio.md)
- `wake_word` (WakeWordConfig): Wake word detection configuration. See [wake_word.py](voice-wake-word.md)
- `vad` (VADConfig): Voice activity detection configuration. See [vad.py](voice-vad.md)
- `realtime` (RealtimeConfig): OpenAI Realtime API configuration. See [openai_realtime.py](voice-openai-realtime.md)
- `listening_timeout` (float): Maximum seconds to wait for speech after wake word. Default: 30.0
- `processing_timeout` (float): Maximum seconds to wait for agent response. Default: 45.0
- `playback_timeout` (float): Maximum seconds to wait for TTS playback. Default: 60.0
- `personas` (dict): Persona configurations keyed by wake word model name
- `default_persona` (str): Wake word model name for the default persona

**Example**:
```python
from reachy_agent.voice import (
    VoicePipelineConfig,
    AudioConfig,
    WakeWordConfig,
    VADConfig,
    RealtimeConfig,
)

config = VoicePipelineConfig(
    audio=AudioConfig(
        input_device_index=None,  # Auto-detect
        sample_rate=16000,
    ),
    wake_word=WakeWordConfig(
        models=["hey_motoko"],
        sensitivity=0.5,
    ),
    listening_timeout=20.0,
    personas={
        "hey_motoko": {
            "name": "motoko",
            "voice": "nova",
            "display_name": "Major Kusanagi",
            "prompt_path": "config/prompts/motoko.txt",
        }
    },
    default_persona="hey_motoko",
)
```

---

## VoicePipelineState

Enumeration of pipeline state machine states.

```python
class VoicePipelineState(Enum):
    IDLE = "idle"
    LISTENING_WAKE = "listening_wake"
    WAKE_DETECTED = "wake_detected"
    LISTENING_SPEECH = "listening_speech"
    PROCESSING_SPEECH = "processing_speech"
    PLAYING_RESPONSE = "playing_response"
    ERROR = "error"
```

**Values**:

- `IDLE`: Pipeline not active, minimal resource usage
- `LISTENING_WAKE`: Listening for wake word detection
- `WAKE_DETECTED`: Wake word heard, preparing to listen for speech
- `LISTENING_SPEECH`: Recording user speech with VAD
- `PROCESSING_SPEECH`: Sending transcription to agent for processing
- `PLAYING_RESPONSE`: Playing TTS audio response from agent
- `ERROR`: Error occurred, attempting recovery

**Valid State Transitions**:

| From State | To States |
|------------|-----------|
| `IDLE` | `LISTENING_WAKE` |
| `LISTENING_WAKE` | `WAKE_DETECTED`, `ERROR`, `IDLE` |
| `WAKE_DETECTED` | `LISTENING_SPEECH`, `ERROR`, `LISTENING_WAKE` |
| `LISTENING_SPEECH` | `PROCESSING_SPEECH`, `ERROR`, `LISTENING_WAKE` |
| `PROCESSING_SPEECH` | `PLAYING_RESPONSE`, `ERROR`, `LISTENING_WAKE` |
| `PLAYING_RESPONSE` | `LISTENING_WAKE`, `ERROR` |
| `ERROR` | `LISTENING_WAKE`, `IDLE` |

**Example**:
```python
def on_state_change(from_state: VoicePipelineState, to_state: VoicePipelineState):
    if to_state == VoicePipelineState.WAKE_DETECTED:
        print("Wake word detected!")
    elif to_state == VoicePipelineState.PROCESSING_SPEECH:
        print("Processing user request...")
```

---

## PersonaConfig

Configuration for a persona tied to a wake word.

```python
@dataclass
class PersonaConfig:
    name: str
    wake_word_model: str
    voice: str
    display_name: str
    prompt_path: str
    traits: dict[str, Any] = field(default_factory=dict)
```

**Fields**:

- `name` (str): Internal identifier (e.g., "motoko", "batou")
- `wake_word_model` (str): OpenWakeWord model name (e.g., "hey_motoko")
- `voice` (str): OpenAI TTS voice name. Valid: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`
- `display_name` (str): Human-readable name (e.g., "Major Kusanagi")
- `prompt_path` (str): Path to the persona's system prompt file
- `traits` (dict): Optional personality traits for runtime reference

**Validation Rules**:

- `voice` must be one of: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`
- `prompt_path` file must exist

**Raises**:
- `ValueError`: If voice is invalid or prompt_path doesn't exist

**Factory Method**:

```python
@classmethod
def from_dict(cls, wake_word_model: str, data: dict[str, Any]) -> PersonaConfig
```

Create a PersonaConfig from a dictionary.

**Parameters**:
- `wake_word_model` (str): Wake word model name to use
- `data` (dict): Dictionary with keys: `name`, `voice`, `display_name`, `prompt_path`, `traits` (optional)

**Returns**: `PersonaConfig` instance

**Example**:
```python
from reachy_agent.voice import PersonaConfig

# Direct construction
persona = PersonaConfig(
    name="motoko",
    wake_word_model="hey_motoko",
    voice="nova",
    display_name="Major Kusanagi",
    prompt_path="config/prompts/motoko.txt",
    traits={"mood": "focused", "expertise": "security"},
)

# From dictionary
data = {
    "name": "batou",
    "voice": "onyx",
    "display_name": "Batou",
    "prompt_path": "config/prompts/batou.txt",
}
persona = PersonaConfig.from_dict("hey_batou", data)
```

---

## PersonaManager

Manages persona registration and lookup.

```python
@dataclass
class PersonaManager:
    personas: dict[str, PersonaConfig] = field(default_factory=dict)
    current_persona: PersonaConfig | None = None
    default_persona_key: str = ""
```

**Fields**:

- `personas` (dict): Mapping of wake word model names to PersonaConfig
- `current_persona` (PersonaConfig | None): Currently active persona
- `default_persona_key` (str): Wake word model name of the default persona

### Methods

#### register_persona()

```python
def register_persona(config: PersonaConfig) -> None
```

Register a persona for a wake word model.

**Parameters**:
- `config` (PersonaConfig): Persona configuration to register

**Example**:
```python
manager = PersonaManager()
manager.register_persona(persona)
```

#### get_persona()

```python
def get_persona(wake_word_model: str) -> PersonaConfig | None
```

Look up a persona by wake word model name.

**Parameters**:
- `wake_word_model` (str): Wake word model name

**Returns**: `PersonaConfig | None` - The persona if found, None otherwise

**Example**:
```python
>>> persona = manager.get_persona("hey_motoko")
>>> persona.display_name
'Major Kusanagi'
```

#### set_default()

```python
def set_default(wake_word_model: str) -> bool
```

Set the default persona by wake word model name.

**Parameters**:
- `wake_word_model` (str): Wake word model name to set as default

**Returns**: `bool` - True if persona exists and was set, False otherwise

**Example**:
```python
>>> manager.set_default("hey_motoko")
True
```

#### get_default()

```python
def get_default() -> PersonaConfig | None
```

Get the default persona.

**Returns**: `PersonaConfig | None` - The default persona if set, None otherwise

**Example**:
```python
>>> default = manager.get_default()
>>> default.name
'motoko'
```

### Factory Method

```python
@classmethod
def from_config(cls, config: dict[str, Any]) -> PersonaManager
```

Create a PersonaManager from a configuration dictionary.

**Parameters**:
- `config` (dict): Configuration with keys:
  - `personas` (dict): Mapping of wake word models to persona data
  - `default_persona` (str, optional): Default wake word model

**Returns**: `PersonaManager` - Configured persona manager

**Example**:
```python
config = {
    "personas": {
        "hey_motoko": {
            "name": "motoko",
            "voice": "nova",
            "display_name": "Major Kusanagi",
            "prompt_path": "config/prompts/motoko.txt",
        },
        "hey_batou": {
            "name": "batou",
            "voice": "onyx",
            "display_name": "Batou",
            "prompt_path": "config/prompts/batou.txt",
        },
    },
    "default_persona": "hey_motoko",
}

manager = PersonaManager.from_config(config)
```

---

## Usage Examples

### Basic Voice Pipeline

```python
from reachy_agent.agent import ReachyAgentLoop
from reachy_agent.voice import VoicePipeline, VoicePipelineConfig

# Create agent and pipeline
agent = ReachyAgentLoop()
pipeline = VoicePipeline(agent=agent)

# Initialize and start
await pipeline.initialize()
await pipeline.start()

# Pipeline now listens for wake word, processes speech, plays responses
# Stop when done
await pipeline.stop()
```

### With Callbacks

```python
def on_state_change(from_state, to_state):
    print(f"State: {from_state.value} -> {to_state.value}")

def on_transcription(text):
    print(f"User said: {text}")

def on_response(text):
    print(f"Agent replied: {text}")

pipeline = VoicePipeline(
    agent=agent,
    on_state_change=on_state_change,
    on_transcription=on_transcription,
    on_response=on_response,
)

await pipeline.initialize()
await pipeline.start()
```

### With Custom Configuration

```python
from reachy_agent.voice import AudioConfig, WakeWordConfig

config = VoicePipelineConfig(
    audio=AudioConfig(
        sample_rate=16000,
        chunk_duration_ms=50,
    ),
    wake_word=WakeWordConfig(
        models=["hey_motoko"],
        sensitivity=0.6,
    ),
    listening_timeout=25.0,
)

pipeline = VoicePipeline(agent=agent, config=config)
```

### Using Context Manager

```python
async with VoicePipeline(agent=agent, config=config) as pipeline:
    await pipeline.start()

    # Wait for keyboard interrupt or other signal
    await asyncio.Event().wait()

# Pipeline automatically stopped and cleaned up
```

### Multi-Persona Setup

```python
config = VoicePipelineConfig(
    personas={
        "hey_motoko": {
            "name": "motoko",
            "voice": "nova",
            "display_name": "Major Kusanagi",
            "prompt_path": "config/prompts/motoko.txt",
        },
        "hey_batou": {
            "name": "batou",
            "voice": "onyx",
            "display_name": "Batou",
            "prompt_path": "config/prompts/batou.txt",
        },
    },
    default_persona="hey_motoko",
    wake_word=WakeWordConfig(
        models=["hey_motoko", "hey_batou"],  # Both wake words active
    ),
)

pipeline = VoicePipeline(agent=agent, config=config)
# Pipeline will switch personas when different wake words are detected
```

---

## Related Modules

- [AudioManager](voice-audio.md) - Audio device management and streaming
- [WakeWordDetector](voice-wake-word.md) - Wake word detection with OpenWakeWord
- [VoiceActivityDetector](voice-vad.md) - Speech segmentation with Silero VAD
- [OpenAIRealtimeClient](voice-openai-realtime.md) - OpenAI Realtime API integration
- [PipelineRecoveryManager](voice-recovery.md) - Error recovery and degraded mode handling
