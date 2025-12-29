"""Voice pipeline for Reachy Agent.

This module provides voice I/O capabilities using OpenAI's Realtime API
with gpt-realtime-mini model for low-latency speech-to-text and text-to-speech.

Components:
    - AudioManager: Hardware audio I/O (microphone + speaker)
    - WakeWordDetector: "Hey Reachy" wake word detection (OpenWakeWord)
    - VAD: Voice activity detection for end-of-speech (Silero VAD)
    - OpenAIRealtimeClient: STT/TTS via gpt-realtime-mini
    - VoicePipeline: State machine orchestrating the full voice interaction

Usage:
    from reachy_agent.voice import VoicePipeline

    pipeline = VoicePipeline(agent=reachy_agent)
    await pipeline.start()  # Begins listening for "Hey Reachy"
"""

from reachy_agent.voice.audio import AudioConfig, AudioManager
from reachy_agent.voice.openai_realtime import OpenAIRealtimeClient, RealtimeConfig
from reachy_agent.voice.pipeline import VoicePipeline, VoicePipelineConfig, VoicePipelineState
from reachy_agent.voice.vad import VADConfig, VoiceActivityDetector
from reachy_agent.voice.wake_word import WakeWordConfig, WakeWordDetector

__all__ = [
    "AudioConfig",
    "AudioManager",
    "WakeWordConfig",
    "WakeWordDetector",
    "VADConfig",
    "VoiceActivityDetector",
    "RealtimeConfig",
    "OpenAIRealtimeClient",
    "VoicePipelineConfig",
    "VoicePipeline",
    "VoicePipelineState",
]
