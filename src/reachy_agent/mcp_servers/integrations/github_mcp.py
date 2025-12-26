"""GitHub MCP Server Integration.

Uses the official GitHub MCP server from https://github.com/github/github-mcp-server
to provide GitHub integration capabilities to the Reachy agent.

The GitHub MCP server enables:
- Repository browsing and code search
- Issue and PR management
- GitHub Actions workflow monitoring
- Code security analysis (Dependabot, code scanning)
- Team collaboration features

Deployment Options:
    1. Native binary (recommended for Raspberry Pi / ARM64):
       - Download from GitHub releases
       - Place at ~/.reachy/bin/github-mcp-server or in PATH
       - Lightweight (~4MB), no Docker required

    2. Docker (recommended for development):
       - Requires Docker installed and running
       - Uses ghcr.io/github/github-mcp-server image

Configuration:
    Set GITHUB_PERSONAL_ACCESS_TOKEN environment variable with a PAT that has:
    - repo scope (for private repos)
    - read:org scope (for organization features)
    - read:packages scope (for package access)
"""

from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any

# GitHub MCP server Docker image
GITHUB_MCP_IMAGE = "ghcr.io/github/github-mcp-server"

# Binary name for native installation
GITHUB_MCP_BINARY = "github-mcp-server"

# Default binary installation paths (checked in order)
GITHUB_MCP_BINARY_PATHS = [
    Path.home() / ".reachy" / "bin" / GITHUB_MCP_BINARY,
    Path.home() / ".local" / "bin" / GITHUB_MCP_BINARY,
    Path("/usr/local/bin") / GITHUB_MCP_BINARY,
]

# GitHub releases URL for downloading binary
GITHUB_MCP_RELEASES_URL = "https://github.com/github/github-mcp-server/releases/latest"

# Available toolsets that can be enabled/disabled
GITHUB_TOOLSETS = [
    "repos",           # Repository operations
    "issues",          # Issue management
    "pull_requests",   # PR management
    "actions",         # GitHub Actions
    "code_security",   # Security scanning
    "gists",           # Gist management
    "discussions",     # GitHub Discussions
    "notifications",   # Notification management
    "teams",           # Team management
    "organizations",   # Organization management
]

# Default toolsets for Reachy (focused on practical use cases)
DEFAULT_TOOLSETS = [
    "repos",
    "issues",
    "pull_requests",
    "actions",
]


def find_github_mcp_binary() -> Path | None:
    """Find the GitHub MCP server binary.

    Checks in order:
    1. ~/.reachy/bin/github-mcp-server (Reachy-specific)
    2. ~/.local/bin/github-mcp-server (user local)
    3. /usr/local/bin/github-mcp-server (system)
    4. PATH (via shutil.which)

    Returns:
        Path to binary if found, None otherwise.
    """
    # Check known paths first
    for path in GITHUB_MCP_BINARY_PATHS:
        if path.exists() and path.is_file():
            return path

    # Fall back to PATH search
    which_result = shutil.which(GITHUB_MCP_BINARY)
    if which_result:
        return Path(which_result)

    return None


def is_binary_available() -> bool:
    """Check if the GitHub MCP server binary is installed."""
    return find_github_mcp_binary() is not None


def is_docker_available() -> bool:
    """Check if Docker is available on the system."""
    return shutil.which("docker") is not None


def get_platform_asset_name() -> str:
    """Get the GitHub release asset name for the current platform.

    Returns:
        Asset filename like 'github-mcp-server_Linux_arm64.tar.gz'
    """
    system = platform.system()  # Linux, Darwin, Windows
    machine = platform.machine()  # x86_64, arm64, aarch64

    # Normalize architecture names
    arch_map = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "i386": "i386",
        "i686": "i386",
    }
    arch = arch_map.get(machine.lower(), machine)

    if system == "Windows":
        return f"github-mcp-server_{system}_{arch}.zip"
    return f"github-mcp-server_{system}_{arch}.tar.gz"


def get_github_token() -> str | None:
    """Get GitHub Personal Access Token from environment.

    Checks in order:
    1. GITHUB_PERSONAL_ACCESS_TOKEN (official MCP server var)
    2. GITHUB_TOKEN (common alternative)
    3. GH_TOKEN (GitHub CLI convention)
    """
    return (
        os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("GH_TOKEN")
    )


def build_github_mcp_config(
    toolsets: list[str] | None = None,
    github_host: str | None = None,
    enable_dynamic_toolsets: bool = False,
    prefer_docker: bool = False,
) -> dict[str, Any]:
    """Build GitHub MCP server configuration for stdio transport.

    By default, prefers the native binary over Docker for better performance
    and compatibility with resource-constrained devices like Raspberry Pi.

    Args:
        toolsets: List of toolsets to enable. Uses DEFAULT_TOOLSETS if None.
        github_host: GitHub Enterprise Server hostname (optional).
        enable_dynamic_toolsets: Allow Claude to enable/disable toolsets dynamically.
        prefer_docker: If True, use Docker even if binary is available.

    Returns:
        MCP server configuration dictionary for Claude SDK.

    Raises:
        RuntimeError: If neither binary nor Docker is available.
        ValueError: If GITHUB_PERSONAL_ACCESS_TOKEN is not set.
    """
    token = get_github_token()
    if not token:
        raise ValueError(
            "GitHub Personal Access Token required. "
            "Set GITHUB_PERSONAL_ACCESS_TOKEN environment variable."
        )

    # Configure toolsets
    enabled_toolsets = toolsets or DEFAULT_TOOLSETS

    # Determine which mode to use (binary preferred by default)
    binary_path = find_github_mcp_binary()
    use_binary = binary_path is not None and not prefer_docker

    if use_binary:
        return _build_binary_config(
            binary_path=binary_path,  # type: ignore[arg-type]
            token=token,
            toolsets=enabled_toolsets,
            github_host=github_host,
            enable_dynamic_toolsets=enable_dynamic_toolsets,
        )

    if is_docker_available():
        return _build_docker_config(
            token=token,
            toolsets=enabled_toolsets,
            github_host=github_host,
            enable_dynamic_toolsets=enable_dynamic_toolsets,
        )

    # Neither available
    raise RuntimeError(
        "GitHub MCP server not available. Install either:\n"
        f"  1. Binary: Download from {GITHUB_MCP_RELEASES_URL}\n"
        f"     Place at: {GITHUB_MCP_BINARY_PATHS[0]}\n"
        "  2. Docker: Install Docker and pull ghcr.io/github/github-mcp-server"
    )


def _build_binary_config(
    binary_path: Path,
    token: str,
    toolsets: list[str],
    github_host: str | None,
    enable_dynamic_toolsets: bool,
) -> dict[str, Any]:
    """Build config for native binary mode."""
    args = ["stdio", f"--toolsets={','.join(toolsets)}"]

    if github_host:
        args.append(f"--gh-host={github_host}")

    if enable_dynamic_toolsets:
        args.append("--dynamic-toolsets")

    return {
        "type": "stdio",
        "command": str(binary_path),
        "args": args,
        "env": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": token,
        },
    }


def _build_docker_config(
    token: str,
    toolsets: list[str],
    github_host: str | None,
    enable_dynamic_toolsets: bool,
) -> dict[str, Any]:
    """Build config for Docker mode."""
    docker_args = [
        "run",
        "-i",           # Interactive (for stdio)
        "--rm",         # Remove container on exit
        "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={token}",
    ]

    # Add the image
    docker_args.append(GITHUB_MCP_IMAGE)

    # Add the stdio subcommand
    docker_args.append("stdio")

    # Add toolsets flag
    docker_args.append(f"--toolsets={','.join(toolsets)}")

    # GitHub Enterprise Server support via flag
    if github_host:
        docker_args.append(f"--gh-host={github_host}")

    # Dynamic toolset management
    if enable_dynamic_toolsets:
        docker_args.append("--dynamic-toolsets")

    return {
        "type": "stdio",
        "command": "docker",
        "args": docker_args,
    }


def get_github_tools_for_toolset(toolset: str) -> list[str]:
    """Get the MCP tool names for a given toolset.

    This helps with permission configuration - knowing which tools
    belong to which toolset.

    Args:
        toolset: One of the GITHUB_TOOLSETS values.

    Returns:
        List of tool names in the toolset.
    """
    toolset_tools = {
        "repos": [
            "get_file_contents",
            "create_or_update_file",
            "push_files",
            "search_repositories",
            "create_repository",
            "fork_repository",
            "list_branches",
            "create_branch",
            "list_commits",
            "get_commit",
        ],
        "issues": [
            "list_issues",
            "get_issue",
            "create_issue",
            "update_issue",
            "add_issue_comment",
            "search_issues",
        ],
        "pull_requests": [
            "list_pull_requests",
            "get_pull_request",
            "create_pull_request",
            "update_pull_request",
            "merge_pull_request",
            "list_pull_request_files",
            "create_pull_request_review",
        ],
        "actions": [
            "list_workflows",
            "list_workflow_runs",
            "get_workflow_run",
            "trigger_workflow",
            "cancel_workflow_run",
            "list_workflow_jobs",
            "get_workflow_run_logs",
        ],
        "code_security": [
            "list_code_scanning_alerts",
            "get_code_scanning_alert",
            "list_secret_scanning_alerts",
            "list_dependabot_alerts",
        ],
        "gists": [
            "list_gists",
            "get_gist",
            "create_gist",
            "update_gist",
            "delete_gist",
        ],
        "discussions": [
            "list_discussions",
            "get_discussion",
            "create_discussion",
        ],
        "notifications": [
            "list_notifications",
            "mark_notification_read",
            "mark_all_notifications_read",
        ],
        "teams": [
            "list_teams",
            "get_team",
            "list_team_members",
        ],
        "organizations": [
            "list_org_repos",
            "get_organization",
        ],
    }
    return toolset_tools.get(toolset, [])


def get_all_github_tools(toolsets: list[str] | None = None) -> list[str]:
    """Get all GitHub MCP tool names for the specified toolsets.

    Args:
        toolsets: List of toolsets. Uses DEFAULT_TOOLSETS if None.

    Returns:
        List of all tool names across the specified toolsets.
    """
    enabled = toolsets or DEFAULT_TOOLSETS
    tools: list[str] = []
    for toolset in enabled:
        tools.extend(get_github_tools_for_toolset(toolset))
    return tools


# Permission tier suggestions for GitHub tools
GITHUB_PERMISSION_TIERS = {
    # Tier 1: Autonomous (read-only operations)
    "autonomous": [
        "get_file_contents",
        "search_repositories",
        "list_branches",
        "list_commits",
        "get_commit",
        "list_issues",
        "get_issue",
        "search_issues",
        "list_pull_requests",
        "get_pull_request",
        "list_pull_request_files",
        "list_workflows",
        "list_workflow_runs",
        "get_workflow_run",
        "list_workflow_jobs",
        "get_workflow_run_logs",
        "list_code_scanning_alerts",
        "get_code_scanning_alert",
        "list_secret_scanning_alerts",
        "list_dependabot_alerts",
        "list_gists",
        "get_gist",
        "list_discussions",
        "get_discussion",
        "list_notifications",
        "list_teams",
        "get_team",
        "list_team_members",
        "list_org_repos",
        "get_organization",
    ],
    # Tier 2: Notify (safe write operations)
    "notify": [
        "add_issue_comment",
        "mark_notification_read",
        "mark_all_notifications_read",
    ],
    # Tier 3: Confirm (operations that create/modify content)
    "confirm": [
        "create_or_update_file",
        "push_files",
        "create_repository",
        "fork_repository",
        "create_branch",
        "create_issue",
        "update_issue",
        "create_pull_request",
        "update_pull_request",
        "create_pull_request_review",
        "trigger_workflow",
        "cancel_workflow_run",
        "create_gist",
        "update_gist",
        "create_discussion",
    ],
    # Tier 4: Forbidden (destructive operations)
    "forbidden": [
        "merge_pull_request",  # Requires explicit confirmation
        "delete_gist",         # Destructive
    ],
}
