"""Context builder for memory injection.

Builds context strings for injection into Claude's system prompt,
providing personalized context without explicit tool calls.
"""

from __future__ import annotations

import logging
from datetime import datetime

from reachy_agent.memory.types import SessionSummary, UserProfile

logger = logging.getLogger(__name__)


class MemoryContextBuilder:
    """Builds memory context for system prompt injection.

    Formats user profile and session information into markdown
    that can be injected into Claude's system prompt.

    Example:
        >>> builder = MemoryContextBuilder()
        >>> context = builder.build(profile, last_session)
        >>> system_prompt = f"{base_prompt}\\n\\n{context}"
    """

    def __init__(self) -> None:
        self._custom_sections: list[str] = []

    def build(
        self,
        profile: UserProfile | None = None,
        last_session: SessionSummary | None = None,
        include_timestamp: bool = True,
    ) -> str:
        """Build the complete memory context string.

        Args:
            profile: User profile to include.
            last_session: Last session summary to include.
            include_timestamp: Whether to include current timestamp.

        Returns:
            Formatted markdown context string.
        """
        sections = []

        # Header
        sections.append("# Memory Context")
        sections.append("")

        # Timestamp
        if include_timestamp:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            sections.append(f"*Current time: {now}*")
            sections.append("")

        # User Profile Section
        if profile and self._has_profile_content(profile):
            sections.append("## User Profile")
            sections.append(profile.to_context_string())
            sections.append("")

        # Last Session Section
        if last_session:
            sections.append("## Last Session")
            sections.append(last_session.to_context_string())
            sections.append("")

        # Custom sections
        for section in self._custom_sections:
            sections.append(section)
            sections.append("")

        # If we only have the header and timestamp, return empty
        if len(sections) <= 3:
            return ""

        return "\n".join(sections).rstrip()

    def _has_profile_content(self, profile: UserProfile) -> bool:
        """Check if profile has meaningful content to display."""
        return bool(
            profile.name != "User"
            or profile.preferences
            or profile.schedule_patterns
            or profile.connected_services
        )

    def add_section(self, title: str, content: str) -> None:
        """Add a custom section to the context.

        Args:
            title: Section title (will be formatted as ## heading).
            content: Section content (markdown).
        """
        self._custom_sections.append(f"## {title}")
        self._custom_sections.append(content)

    def clear_custom_sections(self) -> None:
        """Clear all custom sections."""
        self._custom_sections.clear()

    def build_minimal(
        self,
        profile: UserProfile | None = None,
    ) -> str:
        """Build a minimal context with just user name.

        Useful for reducing token usage while maintaining personalization.

        Args:
            profile: User profile to extract name from.

        Returns:
            Minimal context string.
        """
        if not profile or profile.name == "User":
            return ""

        return f"*Talking with {profile.name}*"


def build_memory_context(
    profile: UserProfile | None = None,
    last_session: SessionSummary | None = None,
) -> str:
    """Convenience function to build memory context.

    Args:
        profile: User profile to include.
        last_session: Last session summary to include.

    Returns:
        Formatted markdown context string.
    """
    builder = MemoryContextBuilder()
    return builder.build(profile, last_session)
