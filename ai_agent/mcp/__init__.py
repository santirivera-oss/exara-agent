"""MCP (Model Context Protocol) integration.

Lets the agent consume tools from any process that speaks MCP — GitHub,
Slack, Linear, filesystem, Postgres, Brave Search, etc. — without writing
a per-service wrapper.

Configure with a `mcp.json` in the workspace root (or via `settings.mcp.config_path`).
"""
from .client import MCPClient
from .config import MCPServerConfig, load_mcp_config, load_merged_mcp_config
from .manager import MCPManager, MCPToolMeta

__all__ = [
    "MCPClient",
    "MCPManager",
    "MCPServerConfig",
    "MCPToolMeta",
    "load_mcp_config",
    "load_merged_mcp_config",
]
