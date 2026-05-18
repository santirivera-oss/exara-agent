"""Plan mode tools.

The `exit_plan_mode` tool surfaces a finished plan to the user and is the *only*
way the agent should signal it is done planning. The CLI / API watches for this
tool call, prompts the user to approve, and toggles plan_mode off on the agent.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult


class ExitPlanModeArgs(BaseModel):
    plan: str = Field(..., description="Numbered markdown plan describing what you intend to do.")


class ExitPlanMode(Tool):
    name = "exit_plan_mode"
    description = (
        "Submit your plan for user approval. Use this ONLY when in plan mode. "
        "Provide a concise numbered plan in markdown. The user reviews and "
        "either approves (you exit plan mode and may proceed) or rejects."
    )
    Args = ExitPlanModeArgs
    read_only = True  # planning itself is read-only

    async def _run(self, args: ExitPlanModeArgs, ctx: ToolContext) -> ToolResult:
        # The actual approval is handled by the agent loop, not here.
        # This tool just records the plan and returns it. The loop intercepts
        # the call and prompts the user before unblocking the next step.
        return ToolResult(
            True,
            args.plan,
            data={"plan": args.plan, "kind": "plan_submission"},
        )
