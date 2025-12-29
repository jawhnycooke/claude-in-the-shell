"""Autonomous voice testing harness for Reachy Agent.

This module provides a "synthetic human" that generates TTS audio to simulate
human speech input, enabling automated end-to-end testing of the voice pipeline
without requiring manual voice input.

Architecture:
1. SyntheticHuman generates PCM audio via OpenAI Realtime TTS
2. Audio is resampled from 24kHz (OpenAI) to 16kHz (pipeline input)
3. Audio is injected directly into VoicePipeline's audio queue
4. Pipeline processes: STT → Claude Agent → TTS Response
5. TestHarness captures and validates results
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
import structlog

from reachy_agent.voice.openai_realtime import OpenAIRealtimeClient, RealtimeConfig

if TYPE_CHECKING:
    from reachy_agent.agent.agent import ReachyAgentLoop
    from reachy_agent.voice.pipeline import VoicePipeline

logger = structlog.get_logger(__name__)


def resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample PCM16 audio from one sample rate to another.

    Uses linear interpolation for fast, reasonable quality resampling.

    Args:
        audio_data: Input audio bytes (PCM16, mono)
        from_rate: Source sample rate (e.g., 24000)
        to_rate: Target sample rate (e.g., 16000)

    Returns:
        Resampled audio bytes
    """
    if from_rate == to_rate:
        return audio_data

    samples = np.frombuffer(audio_data, dtype=np.int16)
    if len(samples) == 0:
        return audio_data

    # Linear interpolation resampling
    ratio = to_rate / from_rate
    new_length = int(len(samples) * ratio)

    indices = np.linspace(0, len(samples) - 1, new_length)
    resampled = np.interp(indices, np.arange(len(samples)), samples)

    return resampled.astype(np.int16).tobytes()


class TestResultStatus(Enum):
    """Status of a test scenario result."""

    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class TestResult:
    """Result of a single test scenario execution."""

    input_text: str
    status: TestResultStatus
    transcription: str = ""
    agent_response: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    error_message: str = ""
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        """Check if test passed."""
        return self.status == TestResultStatus.PASSED


@dataclass
class TestScenario:
    """Definition of a test scenario."""

    name: str
    input_text: str
    expect_response: bool = True
    expect_tool: str | None = None
    expect_tools: list[str] | None = None
    expect_transcription_contains: str | None = None
    timeout_seconds: float = 30.0


@dataclass
class SyntheticHuman:
    """Generates synthetic speech audio to simulate human input.

    Uses OpenAI's Realtime API TTS to generate PCM audio that can be
    injected into the voice pipeline, simulating a human speaking.
    """

    config: RealtimeConfig = field(default_factory=RealtimeConfig)
    _client: OpenAIRealtimeClient | None = field(default=None, repr=False)
    _is_connected: bool = field(default=False, repr=False)

    async def initialize(self) -> bool:
        """Initialize the OpenAI Realtime client.

        Returns:
            True if initialization successful
        """
        self._client = OpenAIRealtimeClient(config=self.config)

        if not self._client.is_available:
            logger.error("synthetic_human_openai_not_available")
            return False

        logger.info(
            "synthetic_human_initialized",
            model=self.config.model,
            voice=self.config.voice,
        )
        return True

    async def connect(self) -> bool:
        """Connect to OpenAI Realtime API.

        Returns:
            True if connection successful
        """
        if not self._client:
            logger.error("synthetic_human_not_initialized")
            return False

        connected = await self._client.connect()
        self._is_connected = connected
        return connected

    async def disconnect(self) -> None:
        """Disconnect from OpenAI Realtime API."""
        if self._client:
            await self._client.disconnect()
        self._is_connected = False

    async def speak(self, text: str) -> bytes:
        """Generate PCM audio of the synthetic human speaking.

        Args:
            text: Text for the synthetic human to speak

        Returns:
            PCM16 audio bytes at 24kHz (OpenAI's output format)
        """
        if (not self._client or not self._is_connected) and not await self.connect():
            logger.error("synthetic_human_speak_connect_failed")
            return b""

        logger.info("synthetic_human_speaking", text=text)

        chunks: list[bytes] = []
        try:
            async for chunk in self._client.speak(text):
                if chunk:
                    chunks.append(chunk)
        except Exception as e:
            logger.error("synthetic_human_speak_error", error=str(e))
            return b""

        audio = b"".join(chunks)
        logger.debug(
            "synthetic_human_audio_generated",
            text_length=len(text),
            audio_bytes=len(audio),
            chunks=len(chunks),
        )
        return audio

    async def speak_resampled(
        self,
        text: str,
        target_rate: int = 16000,
    ) -> bytes:
        """Generate PCM audio resampled to target rate.

        Args:
            text: Text for the synthetic human to speak
            target_rate: Target sample rate (default 16kHz for pipeline)

        Returns:
            PCM16 audio bytes at target sample rate
        """
        audio_24k = await self.speak(text)
        if not audio_24k:
            return b""

        # Resample from 24kHz (OpenAI output) to target rate
        audio_resampled = resample_audio(audio_24k, 24000, target_rate)
        logger.debug(
            "synthetic_human_audio_resampled",
            from_rate=24000,
            to_rate=target_rate,
            original_bytes=len(audio_24k),
            resampled_bytes=len(audio_resampled),
        )
        return audio_resampled

    async def __aenter__(self) -> SyntheticHuman:
        """Async context manager entry."""
        await self.initialize()
        await self.connect()
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.disconnect()


@dataclass
class VoiceTestHarness:
    """Orchestrates autonomous voice pipeline testing.

    Coordinates synthetic human speech generation with voice pipeline
    processing, capturing and validating results.
    """

    agent: ReachyAgentLoop | None = None
    pipeline: VoicePipeline | None = None
    synthetic_human: SyntheticHuman = field(default_factory=SyntheticHuman)

    # Captured results from pipeline callbacks
    _transcriptions: list[str] = field(default_factory=list, repr=False)
    _agent_responses: list[str] = field(default_factory=list, repr=False)
    _tool_calls: list[dict] = field(default_factory=list, repr=False)
    _response_event: asyncio.Event = field(
        default_factory=asyncio.Event, repr=False
    )

    async def initialize(self) -> bool:
        """Initialize the test harness components.

        Returns:
            True if initialization successful
        """
        # Initialize synthetic human
        if not await self.synthetic_human.initialize():
            logger.error("test_harness_synthetic_human_init_failed")
            return False

        logger.info("test_harness_initialized")
        return True

    def _on_transcription(self, text: str) -> None:
        """Callback when transcription is received."""
        logger.debug("test_harness_transcription", text=text)
        self._transcriptions.append(text)

    def _on_response(self, text: str) -> None:
        """Callback when agent response is received."""
        logger.debug("test_harness_response", text=text[:100] if text else "")
        self._agent_responses.append(text)
        self._response_event.set()

    async def inject_audio(self, audio_data: bytes) -> None:
        """Inject audio directly into the pipeline's audio queue.

        This bypasses the hardware microphone, allowing synthetic audio
        to be processed by the voice pipeline.

        Args:
            audio_data: PCM16 audio at 16kHz (pipeline's expected format)
        """
        if not self.pipeline or not self.pipeline._audio:
            logger.error("test_harness_no_pipeline")
            return

        # Split audio into chunks matching pipeline's chunk size
        chunk_size = self.pipeline.config.audio.chunk_size * 2  # 2 bytes per int16 sample
        chunks = [
            audio_data[i : i + chunk_size]
            for i in range(0, len(audio_data), chunk_size)
        ]

        logger.debug(
            "test_harness_injecting_audio",
            total_bytes=len(audio_data),
            chunks=len(chunks),
        )

        # Inject chunks into the audio queue
        for chunk in chunks:
            try:
                self.pipeline._audio._audio_queue.put_nowait(chunk)
            except Exception as e:
                logger.warning("test_harness_inject_queue_full", error=str(e))
                break

    async def run_scenario(
        self,
        scenario: TestScenario,
    ) -> TestResult:
        """Run a single test scenario.

        Args:
            scenario: Test scenario to execute

        Returns:
            Test result with captured data
        """
        import time

        start_time = time.monotonic()

        # Reset captured data
        self._transcriptions.clear()
        self._agent_responses.clear()
        self._tool_calls.clear()
        self._response_event.clear()

        logger.info(
            "test_scenario_starting",
            name=scenario.name,
            input_text=scenario.input_text,
        )

        try:
            # Generate synthetic speech
            audio = await self.synthetic_human.speak_resampled(
                scenario.input_text,
                target_rate=16000,
            )

            if not audio:
                return TestResult(
                    input_text=scenario.input_text,
                    status=TestResultStatus.ERROR,
                    error_message="Failed to generate synthetic speech",
                    duration_seconds=time.monotonic() - start_time,
                )

            # Inject audio into pipeline
            await self.inject_audio(audio)

            # Wait for response with timeout
            try:
                await asyncio.wait_for(
                    self._response_event.wait(),
                    timeout=scenario.timeout_seconds,
                )
            except asyncio.TimeoutError:
                return TestResult(
                    input_text=scenario.input_text,
                    status=TestResultStatus.TIMEOUT,
                    transcription=self._transcriptions[-1] if self._transcriptions else "",
                    error_message=f"Timeout after {scenario.timeout_seconds}s",
                    duration_seconds=time.monotonic() - start_time,
                )

            # Build result
            transcription = self._transcriptions[-1] if self._transcriptions else ""
            agent_response = self._agent_responses[-1] if self._agent_responses else ""

            # Validate expectations
            status = TestResultStatus.PASSED

            if scenario.expect_response and not agent_response:
                status = TestResultStatus.FAILED

            if (
                scenario.expect_transcription_contains
                and scenario.expect_transcription_contains.lower() not in transcription.lower()
            ):
                status = TestResultStatus.FAILED

            # TODO: Add tool call validation when we capture tool calls

            result = TestResult(
                input_text=scenario.input_text,
                status=status,
                transcription=transcription,
                agent_response=agent_response,
                tool_calls=list(self._tool_calls),
                duration_seconds=time.monotonic() - start_time,
            )

            logger.info(
                "test_scenario_completed",
                name=scenario.name,
                status=result.status.value,
                duration=round(result.duration_seconds, 2),
            )

            return result

        except Exception as e:
            logger.error("test_scenario_error", name=scenario.name, error=str(e))
            return TestResult(
                input_text=scenario.input_text,
                status=TestResultStatus.ERROR,
                error_message=str(e),
                duration_seconds=time.monotonic() - start_time,
            )

    async def run_all_scenarios(
        self,
        scenarios: list[TestScenario],
    ) -> list[TestResult]:
        """Run all test scenarios sequentially.

        Args:
            scenarios: List of test scenarios to execute

        Returns:
            List of test results
        """
        results: list[TestResult] = []

        logger.info("test_harness_starting", scenario_count=len(scenarios))

        for scenario in scenarios:
            result = await self.run_scenario(scenario)
            results.append(result)

            # Brief pause between scenarios
            await asyncio.sleep(1.0)

        # Summary
        passed = sum(1 for r in results if r.success)
        logger.info(
            "test_harness_completed",
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
        )

        return results

    async def cleanup(self) -> None:
        """Clean up test harness resources."""
        await self.synthetic_human.disconnect()
        logger.info("test_harness_cleanup")


# Pre-defined test scenarios
DEFAULT_TEST_SCENARIOS = [
    TestScenario(
        name="basic_greeting",
        input_text="Hello Reachy, how are you?",
        expect_response=True,
    ),
    TestScenario(
        name="look_left",
        input_text="Look to the left please",
        expect_response=True,
        expect_tool="look_at",
    ),
    TestScenario(
        name="wave_hello",
        input_text="Wave hello to me",
        expect_response=True,
        expect_tool="play_emotion",
    ),
    TestScenario(
        name="nod_head",
        input_text="Nod your head",
        expect_response=True,
        expect_tool="nod",
    ),
    TestScenario(
        name="current_pose",
        input_text="What position is your head in right now?",
        expect_response=True,
        expect_tool="get_pose",
    ),
    TestScenario(
        name="show_excitement",
        input_text="Show me that you are excited!",
        expect_response=True,
        expect_tool="play_emotion",
    ),
]


async def run_voice_tests(
    agent: ReachyAgentLoop | None = None,
    pipeline: VoicePipeline | None = None,
    scenarios: list[TestScenario] | None = None,
) -> list[TestResult]:
    """Convenience function to run voice pipeline tests.

    Args:
        agent: Optional ReachyAgentLoop instance
        pipeline: Optional VoicePipeline instance
        scenarios: Optional list of test scenarios (uses defaults if None)

    Returns:
        List of test results
    """
    harness = VoiceTestHarness(
        agent=agent,
        pipeline=pipeline,
    )

    if not await harness.initialize():
        logger.error("voice_tests_init_failed")
        return []

    try:
        test_scenarios = scenarios or DEFAULT_TEST_SCENARIOS
        return await harness.run_all_scenarios(test_scenarios)
    finally:
        await harness.cleanup()
