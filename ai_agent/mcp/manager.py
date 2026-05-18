"""MCPManager — owns N MCPClients, exposes a flat catalogue of tools.

Each tool is identified by its full qualified name `mcp__{server}__{tool}` (the
Claude-Code convention), which avoids collisions between servers that happen
to publish the same tool name.

Failures during startup of one server are logged and the server is skipped.
The rest of the system keeps running.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ..utils.logging import get_logger
from .client import MCPClient
from .config import MCPServerConfig

logger = get_logger("mcp")

_QUALIFIER = "mcp__"  # prefix used in the qualified tool name


@dataclass
class MCPToolMeta:
    qualified_name: str  # "mcp__github__create_issue"
    server: str          # "github"
    tool: str            # "create_issue"
    description: str
    input_schema: dict[str, Any]
    client: MCPClient


def qualify(server: str, tool: str) -> str:
    return f"{_QUALIFIER}{_safe(server)}__{_safe(tool)}"


def _safe(name: str) -> str:
    """Tool names sent to the model must be a-zA-Z0-9_- per OpenAI spec.
    Replace anything else with underscore so qualified names are always valid.
    """
    return "".join(c if (c.isalnum() or c in "_-") else "_" for c in name)


class MCPManager:
    def __init__(self) -> None:
        self.clients: dict[str, MCPClient] = {}
        self.tools: dict[str, MCPToolMeta] = {}  # qualified name → meta

    async def start_all(self, servers: dict[str, MCPServerConfig]) -> dict[str, str]:
        """Spawn all configured servers concurrently. Returns server-name → status string
        ("ok N tools" or "error: <message>"). Servers that fail are simply omitted from
        self.clients; they don't take down the rest.
        """
        results: dict[str, str] = {}

        async def _start_one(name: str, cfg: MCPServerConfig) -> tuple[str, str]:
            client = MCPClient(name=name, command=cfg.command, args=cfg.args, env=cfg.env)
            try:
                await client.start()
                tools = await client.list_tools()
            except Exception as e:
                logger.warning("mcp_start_failed", server=name, error=str(e))
                # Best-effort cleanup
                try:
                    await client.shutdown()
                except Exception:
                    pass
                return name, f"error: {e}"
            self.clients[name] = client
            for t in tools:
                qname = qualify(name, t["name"])
                self.tools[qname] = MCPToolMeta(
                    qualified_name=qname,
                    server=name,
                    tool=t["name"],
                    description=t["description"],
                    input_schema=t["input_schema"],
                    client=client,
                )
            return name, f"ok ({len(tools)} tools)"

        if not servers:
            return {}

        pairs = await asyncio.gather(
            *(_start_one(n, c) for n, c in servers.items()),
            return_exceptions=False,
        )
        for n, status in pairs:
            results[n] = status
        return results

    async def shutdown_all(self) -> None:
        await asyncio.gather(
            *(c.shutdown() for c in self.clients.values()),
            return_exceptions=True,
        )
        self.clients.clear()
        self.tools.clear()

    def list_tools(self) -> list[MCPToolMeta]:
        return list(self.tools.values())

    def get(self, qualified_name: str) -> MCPToolMeta | None:
        return self.tools.get(qualified_name)
