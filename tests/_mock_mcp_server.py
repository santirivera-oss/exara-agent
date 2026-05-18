"""Minimal MCP stdio server used in tests — exposes a single echo tool."""
from __future__ import annotations

import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


def make_server() -> Server:
    server = Server("mock-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="echo",
                description="Return the provided text verbatim",
                inputSchema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        if name != "echo":
            raise ValueError(f"unknown tool: {name}")
        return [TextContent(type="text", text=arguments.get("text", ""))]

    return server


async def _main() -> None:
    server = make_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
