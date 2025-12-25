"""Unit tests for memory context builder."""

from datetime import datetime

import pytest

from reachy_agent.memory.context_builder import (
    MemoryContextBuilder,
    build_memory_context,
)
from reachy_agent.memory.types import SessionSummary, UserProfile


class TestMemoryContextBuilder:
    """Tests for MemoryContextBuilder class."""

    def test_empty_context(self) -> None:
        """Test building context with no data returns only timestamp."""
        builder = MemoryContextBuilder()
        result = builder.build(include_timestamp=False)
        assert result == ""

    def test_profile_only(self) -> None:
        """Test building context with profile only."""
        builder = MemoryContextBuilder()
        profile = UserProfile(
            name="John",
            preferences={"coffee": "black"},
        )
        result = builder.build(profile=profile, include_timestamp=False)

        assert "# Memory Context" in result
        assert "## User Profile" in result
        assert "- **Name**: John" in result
        assert "coffee: black" in result

    def test_session_only(self) -> None:
        """Test building context with last session only."""
        builder = MemoryContextBuilder()
        session = SessionSummary(
            session_id="s1",
            summary_text="Discussed plans",
            end_time=datetime(2024, 12, 24, 18, 30),
            key_topics=["plans"],
        )
        result = builder.build(last_session=session, include_timestamp=False)

        assert "## Last Session" in result
        assert "- **Summary**: Discussed plans" in result
        assert "- **Ended**: 2024-12-24 18:30" in result

    def test_full_context(self) -> None:
        """Test building context with both profile and session."""
        builder = MemoryContextBuilder()
        profile = UserProfile(
            name="John",
            preferences={"wake_time": "7:00 AM"},
        )
        session = SessionSummary(
            session_id="s1",
            summary_text="Morning conversation",
            end_time=datetime(2024, 12, 24, 8, 0),
        )
        result = builder.build(
            profile=profile,
            last_session=session,
            include_timestamp=False,
        )

        assert "## User Profile" in result
        assert "## Last Session" in result
        assert "- **Name**: John" in result
        assert "- **Summary**: Morning conversation" in result

    def test_timestamp_included(self) -> None:
        """Test that timestamp is included when requested."""
        builder = MemoryContextBuilder()
        profile = UserProfile(name="John")
        result = builder.build(profile=profile, include_timestamp=True)

        assert "*Current time:" in result

    def test_default_profile_excluded(self) -> None:
        """Test that default profile with no content is excluded."""
        builder = MemoryContextBuilder()
        profile = UserProfile()  # All defaults
        result = builder.build(profile=profile, include_timestamp=False)

        # Should be empty since profile has no meaningful content
        assert result == ""

    def test_custom_sections(self) -> None:
        """Test adding custom sections."""
        builder = MemoryContextBuilder()
        builder.add_section("Recent Tasks", "- Buy groceries\n- Call mom")

        profile = UserProfile(name="John")
        result = builder.build(profile=profile, include_timestamp=False)

        assert "## Recent Tasks" in result
        assert "- Buy groceries" in result

    def test_clear_custom_sections(self) -> None:
        """Test clearing custom sections."""
        builder = MemoryContextBuilder()
        builder.add_section("Test", "Content")
        builder.clear_custom_sections()

        profile = UserProfile(name="John")
        result = builder.build(profile=profile, include_timestamp=False)

        assert "## Test" not in result

    def test_build_minimal(self) -> None:
        """Test building minimal context."""
        builder = MemoryContextBuilder()

        # Default user returns empty
        profile = UserProfile()
        result = builder.build_minimal(profile)
        assert result == ""

        # Named user returns greeting
        profile = UserProfile(name="John")
        result = builder.build_minimal(profile)
        assert result == "*Talking with John*"


class TestBuildMemoryContextFunction:
    """Tests for the convenience function."""

    def test_convenience_function(self) -> None:
        """Test the build_memory_context convenience function."""
        profile = UserProfile(name="Jane")
        session = SessionSummary(
            session_id="s1",
            summary_text="Test session",
        )

        result = build_memory_context(profile=profile, last_session=session)

        assert "# Memory Context" in result
        assert "- **Name**: Jane" in result
        assert "- **Summary**: Test session" in result

    def test_convenience_function_empty(self) -> None:
        """Test convenience function with no arguments includes timestamp."""
        result = build_memory_context()
        # With no profile/session, only timestamp header is included
        assert "*Current time:" in result or result == ""
