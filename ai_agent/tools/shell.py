"""Shell command execution — cross-platform, with timeout and output capture.

Safety note: the Validator must clear the command BEFORE this tool runs.
This module assumes that gate has already passed.
"""
from __future__ import annotations

import asyncio
import os

from pydantic import BaseModel, Field

from ..utils.shell import ShellNotAvailable, shell_invocation
from .base import Tool, ToolContext, ToolResult

_MAX_OUTPUT = 200_000  # bytes per stream


class ExecuteTerminalArgs(BaseModel):
    command: str = Field(..., description="Shell command to run. Will be executed in the system shell.")
    cwd: str | None = Field(None, description="Working directory (defaults to workspace root)")
    timeout: int = Field(120, description="Timeout in seconds")
    shell: str | None = Field(
        None,
        description="Override shell: 'pwsh', 'powershell', 'cmd', 'bash', 'sh'. Default: platform native.",
    )


class ExecuteTerminal(Tool):
    name = "execute_terminal"
    description = (
        "Execute a shell command. Captures stdout, stderr, and exit code. "
        "Use this for builds, tests, package managers, system queries. "
        "Destructive commands are blocked by the safety layer."
    )
    Args = ExecuteTerminalArgs
    requires_confirmation = True

    async def _run(self, args: ExecuteTerminalArgs, ctx: ToolContext) -> ToolResult:
        sandbox_cfg = getattr(getattr(ctx.settings, "safety", None), "sandbox", None)
        if sandbox_cfg and sandbox_cfg.enabled:
            return await self._run_sandboxed(args, ctx, sandbox_cfg)

        cwd = args.cwd or str(ctx.workspace)
        try:
            shell_argv = shell_invocation(args.shell, args.command)
        except ShellNotAvailable as e:
            return ToolResult(False, "", error=str(e))

        ctx.logger.info("shell_exec", command=args.command, cwd=cwd, shell=shell_argv[0])

        try:
            proc = await asyncio.create_subprocess_exec(
                *shell_argv,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
        except FileNotFoundError as e:
            return ToolResult(False, "", error=f"shell not found: {e}")

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=args.timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(False, "", error=f"command timed out after {args.timeout}s")

        out = stdout[:_MAX_OUTPUT].decode("utf-8", errors="replace")
        err = stderr[:_MAX_OUTPUT].decode("utf-8", errors="replace")
        truncated_out = len(stdout) > _MAX_OUTPUT
        truncated_err = len(stderr) > _MAX_OUTPUT

        rendered = self._render(proc.returncode or 0, out, err, truncated_out, truncated_err)
        return ToolResult(
            success=proc.returncode == 0,
            output=rendered,
            data={
                "exit_code": proc.returncode,
                "stdout": out,
                "stderr": err,
            },
            error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
        )

    async def _run_sandboxed(self, args: ExecuteTerminalArgs, ctx: ToolContext, sandbox_cfg) -> ToolResult:
        """Run the command inside a Docker container with /bin/sh -c."""
        from ..utils.sandbox import docker_available, run_in_docker

        if not docker_available():
            return ToolResult(False, "",
                              error="sandbox.enabled=true but `docker` is not on PATH")
        res = await run_in_docker(
            image=sandbox_cfg.shell_image,
            argv=["/bin/sh", "-c", args.command],
            workspace=ctx.workspace,
            allow_network=sandbox_cfg.allow_network,
            mount_workspace_writable=sandbox_cfg.mount_workspace_writable,
            timeout=min(args.timeout, sandbox_cfg.timeout_seconds),
        )
        if res.timed_out:
            return ToolResult(False, "", error=res.stderr)

        rendered = self._render(
            res.exit_code,
            res.stdout[:_MAX_OUTPUT],
            res.stderr[:_MAX_OUTPUT],
            len(res.stdout) > _MAX_OUTPUT,
            len(res.stderr) > _MAX_OUTPUT,
        )
        rendered = f"[sandboxed: {sandbox_cfg.shell_image}]\n" + rendered
        return ToolResult(
            res.exit_code == 0,
            rendered,
            data={"exit_code": res.exit_code, "sandboxed": True},
            error=None if res.exit_code == 0 else f"exit code {res.exit_code}",
        )

    @staticmethod
    def _render(rc: int, stdout: str, stderr: str, t_out: bool, t_err: bool) -> str:
        parts: list[str] = [f"exit_code={rc}"]
        if stdout:
            parts.append(f"--- stdout{' (truncated)' if t_out else ''} ---\n{stdout.rstrip()}")
        if stderr:
            parts.append(f"--- stderr{' (truncated)' if t_err else ''} ---\n{stderr.rstrip()}")
        return "\n".join(parts)
