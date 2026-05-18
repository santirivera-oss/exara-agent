"""MCPClient — thin wrapper around the official `mcp` library for stdio transport.

Keeps a single subprocess + ClientSession alive for the lifetime of an
MCPManager. We expose the operations the agent actually needs:
  - initialize()
  - list_tools()
  - call_tool(name, args)
  - shutdown()

Resources and prompts are out of scope for v1.

stderr of the spawned MCP server is redirected to `logs/mcp_<name>.log`
by default so it doesn't pollute the user's chat console. Pass an explicit
file path or text stream to override.
"""
from __future__ import annotations

import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, TextIO

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClient:
    """Owns one MCP server subprocess and its async session.

    Use as: `await client.start()` ... `await client.shutdown()`.
    Don't reuse after shutdown — build a new one.
    """

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        *,
        stderr_path: str | Path | None = None,
    ):
        self.name = name
        self._params = StdioServerParameters(
            command=command,
            args=list(args),
            env={**os.environ, **(env or {})},
        )
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None
        self._tools_cache: list[dict[str, Any]] | None = None
        self._started = False
        # Default: send the server's stderr to its own log file in the agent's
        # log directory. The CLI then stays free of "running on stdio" banners.
        if stderr_path is None:
            log_dir = Path("./logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            stderr_path = log_dir / f"mcp_{name}.log"
        self._stderr_path = Path(stderr_path)
        self._errlog: TextIO | None = None

    @property
    def started(self) -> bool:
        return self._started

    async def start(self) -> None:
        """Spawn the subprocess, initialise the MCP session, prime the tools cache."""
        if self._started:
            return
        # Open stderr sink — kept open until shutdown(). The MCP server writes
        # to this instead of the CLI console.
        self._errlog = open(self._stderr_path, "a", encoding="utf-8", errors="replace")
        read, write = await self._stack.enter_async_context(
            stdio_client(self._params, errlog=self._errlog)
        )
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        self._started = True

    async def list_tools(self, *, refresh: bool = False) -> list[dict[str, Any]]:
        """Return tool metadata as dicts with {name, description, inputSchema}."""
        if self._session is None:
            raise RuntimeError(f"MCPClient {self.name!r} not started")
        if self._tools_cache is None or refresh:
            result = await self._session.list_tools()
            self._tools_cache = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema or {"type": "object", "properties": {}},
                }
                for t in result.tools
            ]
        return self._tools_cache

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool on the server. Returns {ok, text, raw}.

        - `ok`: False if the server flagged isError=True
        - `text`: concatenated text from all text content blocks
        - `raw`: the original CallToolResult, in case the caller wants structured data
        """
        if self._session is None:
            raise RuntimeError(f"MCPClient {self.name!r} not started")
        result = await self._session.call_tool(tool_name, arguments=arguments)
        # CallToolResult.content is a list of content blocks (Text/Image/Embedded).
        # For v1 we flatten text blocks; non-text blocks are summarised.
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
            else:
                kind = getattr(block, "type", type(block).__name__)
                parts.append(f"[{kind} content block]")
        return {
            "ok": not bool(getattr(result, "isError", False)),
            "text": "\n".join(parts).strip(),
            "raw": result,
        }

    async def shutdown(self) -> None:
        if not self._started:
            return
        try:
            await self._stack.aclose()
        finally:
            self._started = False
            self._session = None
            if self._errlog is not None:
                try:
                    self._errlog.close()
                except Exception:
                    pass
                self._errlog = None
