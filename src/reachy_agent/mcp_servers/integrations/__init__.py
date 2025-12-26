"""External MCP integrations - Home Assistant, Calendar, GitHub, etc.

This module provides configuration builders for external MCP servers
that can be integrated with the Reachy agent.

Available Integrations:
    - GitHub MCP: Repository, issue, and PR management via official GitHub MCP server
    - Home Assistant MCP: Smart home control (planned)
    - Google Calendar MCP: Calendar access (planned)
"""

from reachy_agent.mcp_servers.integrations.github_mcp import (
    DEFAULT_TOOLSETS as GITHUB_DEFAULT_TOOLSETS,
)
from reachy_agent.mcp_servers.integrations.github_mcp import (
    GITHUB_MCP_BINARY,
    GITHUB_MCP_BINARY_PATHS,
    GITHUB_MCP_IMAGE,
    GITHUB_MCP_RELEASES_URL,
    GITHUB_PERMISSION_TIERS,
    GITHUB_TOOLSETS,
    build_github_mcp_config,
    find_github_mcp_binary,
    get_all_github_tools,
    get_github_token,
    get_github_tools_for_toolset,
    get_platform_asset_name,
    is_binary_available,
    is_docker_available,
)

__all__ = [
    # GitHub MCP
    "build_github_mcp_config",
    "get_github_token",
    "get_github_tools_for_toolset",
    "get_all_github_tools",
    # Availability checks
    "is_binary_available",
    "is_docker_available",
    "find_github_mcp_binary",
    "get_platform_asset_name",
    # Constants
    "GITHUB_MCP_IMAGE",
    "GITHUB_MCP_BINARY",
    "GITHUB_MCP_BINARY_PATHS",
    "GITHUB_MCP_RELEASES_URL",
    "GITHUB_TOOLSETS",
    "GITHUB_DEFAULT_TOOLSETS",
    "GITHUB_PERMISSION_TIERS",
]
