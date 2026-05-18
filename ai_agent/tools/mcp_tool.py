"""Adapter that wraps an MCP server tool as one of our `Tool` instances.

Built dynamically at startup once we know which tools each MCP server exposes.
The arg schema comes from the server's `inputSchema` (JSON Schema), surfaced
to the model verbatim — we don't rebuild Pydantic models for each, we just
pass the schema through `to_openai_spec()`.
"""
from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from ..mcp.manager import MCPToolMeta
from .base import Tool, ToolContext, ToolResult


class _PassthroughArgs(BaseModel):
    """Placeholder — MCPTool overrides Args at construction time."""
    model_config = {"extra": "allow"}


class MCPTool(Tool):
    """One instance per MCP tool. The class attributes (name/description/Args)
    are set per-instance, which deviates from the normal Tool pattern where
    they're ClassVars — but it lets us register many tools at runtime without
    metaclass tricks.
    """
    Args: ClassVar[type[BaseModel]] = _PassthroughArgs  # overridden in __init__
    read_only: ClassVar[bool] = False

    def __init__(self, meta: MCPToolMeta):
        self.meta = meta
        # Per-instance attributes shadow the class attrs
        self.name = meta.qualified_name  # type: ignore[misc]
        self.description = (
            f"[MCP:{meta.server}] {meta.description}".strip()
        )  # type: ignore[misc]
        # We override to_openai_spec so the JSON schema is the MCP one verbatim.

    def to_openai_spec(self) -> dict[str, Any]:  # type: ignore[override]
        schema = self.meta.input_schema or {"type": "object", "properties": {}}
        # Some MCP servers omit "type" — fill it in to keep providers happy.
        if "type" not in schema:
            schema = {**schema, "type": "object"}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }

    async def run(self, raw_args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        # Skip the Pydantic validation step the base Tool does — MCP servers
        # validate against their own schema, and ours is a passthrough.
        try:
            result = await self._dispatch(raw_args or {}, ctx)
        except Exception as e:
            ctx.logger.warning("mcp_tool_error", tool=self.name, error=str(e))
            return ToolResult(False, "", error=str(e))
        # Same secret scrubbing as built-in tools — MCP servers (especially
        # filesystem) routinely read configs that might contain keys.
        from ..utils.secrets import redact_secrets
        if result.output:
            redacted, n = redact_secrets(result.output)
            if n > 0:
                ctx.logger.warning("redacted_secrets", tool=self.name, count=n)
                result.output = redacted
        return result

    async def _dispatch(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        out = await self.meta.client.call_tool(self.meta.tool, args)
        return ToolResult(
            success=out["ok"],
            output=out["text"] or "(no text content returned)",
            data={"server": self.meta.server, "tool": self.meta.tool},
            error=None if out["ok"] else (out["text"] or "tool error"),
        )

    # Unused — _dispatch supersedes it for MCP tools.
    async def _run(self, args: BaseModel, ctx: ToolContext) -> ToolResult:  # pragma: no cover
        raise NotImplementedError
