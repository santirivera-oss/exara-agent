"""Per-session task list — the agent maintains a visible plan.

This is the pattern Claude Code uses: when the agent is in the middle of a
multi-step task, it keeps a checklist in sync with its progress, and the UI
renders the current state. The user can see what's done, what's next, and
what's still pending without asking.

Storage: `todos` table in the existing SQLite memory store, keyed by session.
The list survives session reloads via /resume.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult


TodoStatus = Literal["pending", "in_progress", "completed"]


class TodoItem(BaseModel):
    content: str = Field(..., description="Short imperative description, e.g. 'Add JWT middleware'")
    status: TodoStatus = Field("pending", description="pending | in_progress | completed")


class TodoWriteArgs(BaseModel):
    items: list[TodoItem] = Field(
        ...,
        description=(
            "The COMPLETE current todo list — this REPLACES the previous list. "
            "Always pass every item you want to keep, not just changes. Mark items "
            "completed as you finish them, and add new ones as you discover them."
        ),
    )


class TodoWrite(Tool):
    name = "todo_write"
    description = (
        "Set the agent's task list for this session. Pass the COMPLETE current list "
        "(REPLACES the previous one). Use this at the start of multi-step work, and "
        "update it after each step: set the current step to 'in_progress' before "
        "doing it, mark it 'completed' afterwards. The user sees the rendered list. "
        "Use it whenever the work has 3+ distinct steps."
    )
    Args = TodoWriteArgs

    async def _run(self, args: TodoWriteArgs, ctx: ToolContext) -> ToolResult:
        memory = ctx.extra.get("memory")
        session_id = ctx.extra.get("session_id")
        if not memory or not session_id:
            return ToolResult(False, "", error="todo_write requires memory + session context")

        items = [{"content": i.content, "status": i.status} for i in args.items]
        await memory.set_todos(session_id, items)
        return ToolResult(
            True,
            _render(items),
            data={"items": items, "count": len(items), "kind": "todos_set"},
        )


class _NoArgs(BaseModel):
    pass


class TodoRead(Tool):
    name = "todo_read"
    description = "Read the current task list for this session."
    Args = _NoArgs
    read_only = True

    async def _run(self, args: _NoArgs, ctx: ToolContext) -> ToolResult:
        memory = ctx.extra.get("memory")
        session_id = ctx.extra.get("session_id")
        if not memory or not session_id:
            return ToolResult(False, "", error="todo_read requires memory + session context")
        items = await memory.get_todos(session_id)
        return ToolResult(True, _render(items) if items else "(no todos yet)", data={"items": items})


# Use parentheses instead of square brackets to avoid Rich interpreting
# things like "[x]" as a markup tag (which made completed items render blank).
_GLYPHS = {"pending": "( )", "in_progress": "(~)", "completed": "(x)"}


def _render(items: list[dict]) -> str:
    if not items:
        return "(empty)"
    return "\n".join(f"  {_GLYPHS.get(it['status'], '[?]')} {it['content']}" for it in items)
