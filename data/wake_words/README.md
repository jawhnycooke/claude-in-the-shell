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

If custom models are not found, the system will:
1. Log a warning about missing model files
2. Fall back to the default `hey_jarvis` wake word (if available)
3. Use the default persona specified in config
