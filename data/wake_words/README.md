# Custom Wake Word Models

This directory contains custom OpenWakeWord models for persona-based wake word detection.

## Expected Files

Place your trained OpenWakeWord `.onnx` model files here:

- `hey_motoko.onnx` - Wake word model for "Hey Motoko" (Major Kusanagi persona)
- `hey_batou.onnx` - Wake word model for "Hey Batou" (Batou persona)

## Training Custom Wake Words

OpenWakeWord models can be trained using the [OpenWakeWord training scripts](https://github.com/dscripka/openWakeWord):

```bash
# Clone the repository
git clone https://github.com/dscripka/openWakeWord.git
cd openWakeWord

# Follow the training instructions in the repository
# to create custom wake word models
```

## Model Format

- Models must be in ONNX format (`.onnx`)
- File names must match the persona wake word keys in `config/default.yaml`
- Models are loaded automatically when the voice pipeline starts

## Ghost in the Shell Theme

This setup supports the Ghost in the Shell theme with two personas:

| Wake Word | Persona | Voice | Character |
|-----------|---------|-------|-----------|
| "Hey Motoko" | Major Kusanagi | nova (female) | Analytical, philosophical, direct |
| "Hey Batou" | Batou | onyx (male) | Casual, humorous, action-oriented |

## Fallback Behavior

If custom persona wake word models are not found, the system handles fallback separately for each subsystem:

**Wake Word Detection:**
1. Logs a warning about missing custom model files
2. Falls back to bundled OpenWakeWord models (e.g., `hey_jarvis`, `alexa`)
3. Uses the `model_name` from config or first available bundled model

**Persona Selection:**
1. Uses the `default_persona` specified in `config/default.yaml` on startup
2. Persona only changes when a registered wake word is detected
3. If a bundled wake word (like `hey_jarvis`) is detected but has no registered persona, the current persona remains unchanged

See `config/default.yaml` under `voice.personas` for persona configuration and `voice.default_persona` for the default.
