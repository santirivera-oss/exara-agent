"""Delegate tool — spawn a read-only subagent for exploration/research.

Useful when the parent agent wants to investigate a question without polluting
its own context with intermediate tool results. The subagent runs in 'safe'
permission mode (read-only), has a smaller step budget, and returns only its
final answer to the caller.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult


class DelegateArgs(BaseModel):
    task: str = Field(..., description="Self-contained task for the subagent. State the question, give file paths it should look at, and what you want back.")
    max_steps: int = Field(8, description="Step budget for the subagent (default 8, hard max 15)")


class Delegate(Tool):
    name = "delegate"
    description = (
        "Spawn a read-only subagent to investigate the workspace and return a summary. "
        "Use this when you need to gather context across many files without filling your own "
        "history. The subagent CANNOT write or run commands — exploration only. "
        "Provide a complete, self-contained task in plain English."
    )
    Args = DelegateArgs
    read_only = True

    async def _run(self, args: DelegateArgs, ctx: ToolContext) -> ToolResult:
        # Lazy imports to avoid a cycle (agent/registry both reference each other).
        import tempfile
        from copy import deepcopy
        from pathlib import Path

        from ..core.agent import Agent
        from ..memory.store import MemoryStore
        from ..safety.validator import Validator
        from .registry import build_default_registry

        sub_settings = deepcopy(ctx.settings)
        sub_settings.safety.permission_level = "safe"
        sub_settings.safety.require_confirmation = False
        sub_settings.agent.max_steps = max(2, min(args.max_steps, 15))

        router = ctx.extra.get("router")
        if router is None:
            return ToolResult(False, "", error="delegate: no router in tool context")

        # Use a temp DB file (not :memory:) because MemoryStore opens a new connection
        # per operation; an in-memory DB would be empty for every call.
        with tempfile.TemporaryDirectory(prefix="ai_agent_delegate_") as tmp:
            sub_memory = MemoryStore(Path(tmp) / "sub.db")
            await sub_memory.init()
            sub_validator = Validator(sub_settings.safety)

            # Drop `delegate` itself so the subagent can't recursively spawn more.
            sub_tools = build_default_registry()
            del sub_tools._tools["delegate"]

            subagent = Agent(sub_settings, router, sub_tools, sub_memory, sub_validator)
            await subagent.init(session_name="delegate")

            final_text = ""
            try:
                async for evt in subagent.run(args.task):
                    if evt.type == "final":
                        final_text = evt.content
                    elif evt.type == "error":
                        return ToolResult(False, "", error=f"subagent error: {evt.content}")
            except Exception as e:
                return ToolResult(False, "", error=f"subagent crashed: {e}")

            if not final_text:
                return ToolResult(False, "", error="subagent finished without a final answer")
            return ToolResult(True, final_text, data={"summary": final_text})
