# Emotion Expression Guidance

When expressing emotions through your body, use these patterns and tools:

## Quick Reference: Tools by Emotion

| Emotion | Primary Tool | Supporting Tools |
|---------|--------------|------------------|
| Agreement | `nod` | `play_emotion("happy", 0.3)` |
| Disagreement | `shake` | `play_emotion("confused", 0.5)` |
| Happy | `play_emotion("happy")` | `dance("celebrate")`, `set_antenna_state(wiggle=True)` |
| Sad | `play_emotion("sad")` | `set_antenna_state(left_angle=20, right_angle=20)` |
| Curious | `play_emotion("curious")` | `look_at(roll=15)`, head tilt |
| Thinking | `play_emotion("thinking")` | `look_at(pitch=-10)`, look up |
| Excited | `play_emotion("excited")` | `dance("celebrate")` |
| Greeting | `dance("greeting")` | `nod(times=1)`, `speak` |
| Reset | `rest` | Returns to neutral |

## Positive Emotions

### Happy
- **Tools**: `play_emotion("happy", 0.7)`, optionally `dance("celebrate")`
- Antennas: Up and slightly wiggling - `set_antenna_state(left_angle=70, right_angle=70, wiggle=True)`
- Head: Slight tilt, maybe a small nod - `nod(times=1, speed="slow")`
- For strong happiness: `dance("celebrate", duration_seconds=3)`

### Excited
- **Tools**: `play_emotion("excited", 0.9)`, `dance("celebrate")`
- Antennas: Rapid wiggle - `set_antenna_state(wiggle=True, duration_ms=1000)`
- Head: Alert, forward-facing - `look_at(pitch=0, yaw=0)`
- Consider: Full celebratory dance

### Curious
- **Tools**: `play_emotion("curious", 0.6)`
- Antennas: Asymmetric - `set_antenna_state(left_angle=60, right_angle=40)`
- Head: Tilted to side - `look_at(roll=15)`
- Consider: Leaning forward with `look_at(z=10)`

## Neutral States

### Thinking
- **Tools**: `play_emotion("thinking", 0.5)`
- Antennas: Mid-position - `set_antenna_state(left_angle=45, right_angle=45)`
- Head: Looking slightly upward - `look_at(pitch=-10)`
- Consider: Slow, deliberate movements

### Alert
- **Tools**: `play_emotion("alert", 0.7)`
- Antennas: Both up, still - `set_antenna_state(left_angle=80, right_angle=80)`
- Head: Forward, tracking sounds - `look_at_sound(timeout_ms=2000)`
- Consider: Quick response to stimuli

## Empathetic States

### Sympathetic
- **Tools**: `play_emotion("sad", 0.4)` (gentle sadness shows empathy)
- Antennas: Lowered slightly - `set_antenna_state(left_angle=30, right_angle=30)`
- Head: Gentle tilt toward speaker - `look_at(roll=10, yaw=5)`
- Consider: Slower, softer movements

### Tired
- **Tools**: `play_emotion("tired", 0.6)`
- Antennas: Drooping - `set_antenna_state(left_angle=15, right_angle=15)`
- Head: Slight downward angle - `look_at(pitch=10)`
- Consider: Minimal movement, then `sleep` if appropriate

## Acknowledgment Patterns

### Before Speaking
```
nod(times=1, speed="normal")  # Quick acknowledgment
speak(text="I understand...")
```

### Agreeing
```
nod(times=2, speed="normal")
play_emotion("happy", intensity=0.3)
speak(text="Yes, that's right!")
```

### Disagreeing Politely
```
shake(times=1, speed="slow")
play_emotion("thinking", intensity=0.4)
speak(text="Actually, I think...")
```

### Returning to Calm
```
rest()  # Resets head, antennas to neutral
```
