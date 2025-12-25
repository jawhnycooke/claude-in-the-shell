"""Reachy MCP Server - Exposes robot body control as MCP tools."""

from reachy_agent.mcp_servers.reachy.reachy_mcp import create_reachy_mcp_server

__all__ = ["create_reachy_mcp_server"]
