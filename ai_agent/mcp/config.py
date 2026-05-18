"""Schema and loader for `mcp.json` — the per-workspace MCP server registry.

Format follows the Claude Desktop / Cursor convention so existing configs
work out of the box:

    {
      "mcpServers": {
        "filesystem": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        },
        "github": {
          "command": "npx",
          "args": ["-y", "@modelcontextprotocol/server-github"],
          "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..."}
        }
      }
    }
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    command: str = Field(..., description="Executable for the MCP server (e.g. 'npx', 'python', 'docker')")
    args: list[str] = Field(default_factory=list, description="Arguments passed to the executable")
    env: dict[str, str] = Field(default_factory=dict, description="Extra environment variables for the subprocess")
    # Allow disabling a server without removing its config block
    disabled: bool = Field(False, description="If true, the server is skipped at startup")


class MCPConfigFile(BaseModel):
    """Top-level shape of mcp.json."""
    mcpServers: dict[str, MCPServerConfig] = Field(default_factory=dict)


def load_mcp_config(path: Path) -> dict[str, MCPServerConfig]:
    """Return server-name → MCPServerConfig. Empty dict if file missing or malformed."""
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    try:
        cfg = MCPConfigFile.model_validate(raw)
    except Exception:
        return {}
    return {name: server for name, server in cfg.mcpServers.items() if not server.disabled}


def load_merged_mcp_config(workspace_path: Path) -> dict[str, MCPServerConfig]:
    """Merge `~/.ai-agent/mcp.json` (user-wide) with `<workspace>/mcp.json`
    (project-specific). The workspace file wins on name collisions.

    This is what lets `ai-agent chat` carry the same servers (github,
    filesystem, etc.) into every folder: drop them in your home once.
    Project-specific servers stay in the repo.
    """
    merged: dict[str, MCPServerConfig] = {}
    user_path = Path.home() / ".ai-agent" / "mcp.json"
    if user_path.is_file():
        merged.update(load_mcp_config(user_path))
    if workspace_path.is_file():
        merged.update(load_mcp_config(workspace_path))
    return merged


# --- Curated catalogue of common MCP servers --------------------------------
# Each entry describes how to launch the server and what env vars (if any)
# the user needs to provide. Used by `ai-agent mcp install <name>`.

class CatalogEntry(BaseModel):
    command: str
    args: list[str]
    env_required: list[str] = Field(default_factory=list)
    description: str = ""
    docs: str = ""
    # Human-readable prompts for each {PLACEHOLDER} in args. Maps the
    # placeholder name to a (label, hint) shown when the user runs install.
    arg_prompts: dict[str, tuple[str, str]] = Field(default_factory=dict)


CATALOG: dict[str, CatalogEntry] = {
    "filesystem": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "{PATH}"],
        description="Read/write files in an allowed directory (sandboxed).",
        docs="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
        arg_prompts={
            "PATH": (
                "Allowed directory",
                "Absolute path the MCP server can read/write. e.g. C:\\Users\\you\\projects",
            ),
        },
    ),
    "github": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env_required=["GITHUB_PERSONAL_ACCESS_TOKEN"],
        description="Create issues/PRs, search code, browse repos. Needs a PAT.",
        docs="https://github.com/modelcontextprotocol/servers/tree/main/src/github",
    ),
    "brave-search": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-brave-search"],
        env_required=["BRAVE_API_KEY"],
        description="Web + local search via Brave's API (2000 free queries/month).",
        docs="https://brave.com/search/api/",
    ),
    "memory": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"],
        description="Persistent knowledge graph across sessions.",
        docs="https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
    ),
    "sequential-thinking": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        description="Structured chain-of-thought for complex problem solving.",
    ),
    "fetch": CatalogEntry(
        command="uvx",
        args=["mcp-server-fetch"],
        description="HTTP fetch with markdown extraction (alternative to web_fetch).",
    ),
    "time": CatalogEntry(
        command="uvx",
        args=["mcp-server-time"],
        description="Timezone-aware date/time lookups and conversions.",
    ),
    "postgres": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-postgres", "{POSTGRES_URL}"],
        description="Read-only SQL queries against a Postgres database.",
        docs="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
        arg_prompts={
            "POSTGRES_URL": (
                "Postgres connection URL",
                "Full URL incl. credentials. e.g. postgresql://user:pass@host:5432/dbname",
            ),
        },
    ),
    "slack": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-slack"],
        env_required=["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        description="Post messages, browse channels, search Slack.",
    ),
    "puppeteer": CatalogEntry(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-puppeteer"],
        description="Headless browser automation (screenshots, scraping, form fill).",
    ),
    "mt5": CatalogEntry(
        command="python",
        args=["mcp_servers/mt5_server.py"],
        env_required=["MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"],
        description="MetaTrader 5: account, symbols, history, positions, order placement (gated). Windows only.",
        docs="mcp_servers/mt5_server.py — read the docstring at the top.",
    ),
}


def add_server_to_config(
    path: Path,
    name: str,
    cfg: MCPServerConfig,
) -> None:
    """Append or replace a server entry in mcp.json. Creates the file if missing."""
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raw = {}
    else:
        raw = {}
    raw.setdefault("mcpServers", {})[name] = cfg.model_dump(exclude_defaults=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
