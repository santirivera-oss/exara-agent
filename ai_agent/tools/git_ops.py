"""Git helpers — status, diff, log, commit. All shell out to `git`."""
from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult


async def _run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


class _Empty(BaseModel):
    pass


# --- git_status ---------------------------------------------------------------

class GitStatus(Tool):
    name = "git_status"
    description = "Run `git status --short` in the workspace."
    Args = _Empty
    read_only = True

    async def _run(self, args: _Empty, ctx: ToolContext) -> ToolResult:
        rc, out, err = await _run_git(["status", "--short", "--branch"], str(ctx.workspace))
        if rc != 0:
            return ToolResult(False, "", error=err.strip() or "git status failed")
        return ToolResult(True, out.rstrip() or "(clean)", data={"output": out})


# --- git_diff -----------------------------------------------------------------

class GitDiffArgs(BaseModel):
    path: str | None = Field(None, description="Limit diff to a path")
    staged: bool = Field(False, description="Show staged diff (--cached)")


class GitDiff(Tool):
    name = "git_diff"
    description = "Show working-tree (or staged) diff."
    Args = GitDiffArgs
    read_only = True

    async def _run(self, args: GitDiffArgs, ctx: ToolContext) -> ToolResult:
        cmd = ["diff", "--no-color"]
        if args.staged:
            cmd.append("--cached")
        if args.path:
            cmd.extend(["--", args.path])
        rc, out, err = await _run_git(cmd, str(ctx.workspace))
        if rc != 0:
            return ToolResult(False, "", error=err.strip() or "git diff failed")
        return ToolResult(True, out.rstrip() or "(no diff)", data={"output": out})


# --- git_log ------------------------------------------------------------------

class GitLogArgs(BaseModel):
    limit: int = Field(20, description="Number of commits to show")


class GitLog(Tool):
    name = "git_log"
    description = "Show recent commit log (oneline)."
    Args = GitLogArgs
    read_only = True

    async def _run(self, args: GitLogArgs, ctx: ToolContext) -> ToolResult:
        rc, out, err = await _run_git(
            ["log", f"--max-count={args.limit}", "--oneline", "--decorate"],
            str(ctx.workspace),
        )
        if rc != 0:
            return ToolResult(False, "", error=err.strip() or "git log failed")
        return ToolResult(True, out.rstrip() or "(no commits)")


# --- git_commit ---------------------------------------------------------------

class GitCommitArgs(BaseModel):
    message: str = Field(..., description="Commit message")
    add_all: bool = Field(False, description="Stage all changes first (git add -A)")
    paths: list[str] | None = Field(None, description="Specific paths to stage instead of -A")


class GitCommit(Tool):
    name = "git_commit"
    description = "Create a git commit. Stages files first if add_all=true or paths provided."
    Args = GitCommitArgs
    requires_confirmation = True

    async def _run(self, args: GitCommitArgs, ctx: ToolContext) -> ToolResult:
        cwd = str(ctx.workspace)
        if args.add_all:
            rc, _, err = await _run_git(["add", "-A"], cwd)
            if rc != 0:
                return ToolResult(False, "", error=err.strip() or "git add failed")
        elif args.paths:
            rc, _, err = await _run_git(["add", *args.paths], cwd)
            if rc != 0:
                return ToolResult(False, "", error=err.strip() or "git add failed")
        rc, out, err = await _run_git(["commit", "-m", args.message], cwd)
        if rc != 0:
            return ToolResult(False, out + err, error=err.strip() or "commit failed")
        return ToolResult(True, out.strip(), data={"output": out})
