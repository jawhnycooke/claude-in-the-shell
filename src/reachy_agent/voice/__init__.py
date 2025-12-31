"""Voice pipeline for Reachy Agent.

This module provides voice I/O capabilities using OpenAI's Realtime API
with gpt-realtime-mini model for low-latency speech-to-text and text-to-speech.

Components:
    - AudioManager: Hardware audio I/O (microphone + speaker)
    - WakeWordDetector: "Hey Reachy" wake word detection (OpenWakeWord)
    - VAD: Voice activity detection for end-of-speech (Silero VAD)
    - OpenAIRealtimeClient: STT/TTS via gpt-realtime-mini
    - VoicePipeline: State machine orchestrating the full voice interaction
    - SyntheticHuman: Generates TTS audio to simulate human speech (testing)
    - VoiceTestHarness: Orchestrates autonomous voice pipeline testing

Usage:
    from reachy_agent.voice import VoicePipeline

    pipeline = VoicePipeline(agent=reachy_agent)
    await pipeline.start()  # Begins listening for "Hey Reachy"

Testing:
    from reachy_agent.voice import SyntheticHuman, run_voice_tests

    # Run automated voice tests without manual speech
    results = await run_voice_tests(agent=agent, pipeline=pipeline)
"""

from reachy_agent.voice.audio import AudioConfig, AudioManager
from reachy_agent.voice.openai_realtime import OpenAIRealtimeClient, RealtimeConfig
from reachy_agent.voice.pipeline import VoicePipeline, VoicePipelineConfig, VoicePipelineState
from reachy_agent.voice.test_harness import (
    DEFAULT_TEST_SCENARIOS,
    SyntheticHuman,
    TestResult,
    TestResultStatus,
    TestScenario,
    VoiceTestHarness,
    resample_audio,
    run_voice_tests,
)
from reachy_agent.voice.vad import VADConfig, VoiceActivityDetector
from reachy_agent.voice.wake_word import WakeWordConfig, WakeWordDetector

__all__ = [
    # Audio
    "AudioConfig",
    "AudioManager",
    # Wake word
    "WakeWordConfig",
    "WakeWordDetector",
    # VAD
    "VADConfig",
    "VoiceActivityDetector",
    # OpenAI Realtime
    "RealtimeConfig",
    "OpenAIRealtimeClient",
    # Pipeline
    "VoicePipelineConfig",
    "VoicePipeline",
    "VoicePipelineState",
    # Test harness
    "SyntheticHuman",
    "VoiceTestHarness",
    "TestScenario",
    "TestResult",
    "TestResultStatus",
    "DEFAULT_TEST_SCENARIOS",
    "run_voice_tests",
    "resample_audio",
]
