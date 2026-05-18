"""Run Python code in a subprocess — isolates execution from the agent process.

NOT a sandbox. Treat as having full host privileges. The safety layer must gate
this for normal-mode users (requires_confirmation=True).
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult

_MAX_OUTPUT = 200_000


class RunPythonArgs(BaseModel):
    code: str = Field(..., description="Python source code to execute")
    timeout: int = Field(60, description="Timeout in seconds")
    cwd: str | None = Field(None, description="Working directory")


class RunPython(Tool):
    name = "run_python"
    description = (
        "Execute a Python snippet in a subprocess using the current interpreter. "
        "Captures stdout, stderr, exit code. Use for ad-hoc computation, parsing, prototypes."
    )
    Args = RunPythonArgs
    requires_confirmation = True

    async def _run(self, args: RunPythonArgs, ctx: ToolContext) -> ToolResult:
        # Sandbox path: run inside a Docker container.
        sandbox_cfg = getattr(getattr(ctx.settings, "safety", None), "sandbox", None)
        if sandbox_cfg and sandbox_cfg.enabled:
            return await self._run_sandboxed(args, ctx, sandbox_cfg)

        cwd = args.cwd or str(ctx.workspace)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(args.code)
            tmp_path = Path(f.name)

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-I", str(tmp_path),
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=args.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(False, "", error=f"python execution timed out after {args.timeout}s")
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

        out = stdout[:_MAX_OUTPUT].decode("utf-8", errors="replace")
        err = stderr[:_MAX_OUTPUT].decode("utf-8", errors="replace")
        parts = [f"exit_code={proc.returncode}"]
        if out:
            parts.append(f"--- stdout ---\n{out.rstrip()}")
        if err:
            parts.append(f"--- stderr ---\n{err.rstrip()}")
        return ToolResult(
            proc.returncode == 0,
            "\n".join(parts),
            data={"exit_code": proc.returncode, "stdout": out, "stderr": err},
            error=None if proc.returncode == 0 else f"exit code {proc.returncode}",
        )

    async def _run_sandboxed(self, args: RunPythonArgs, ctx: ToolContext, sandbox_cfg) -> ToolResult:
        """Execute the snippet inside a Docker container — see SandboxConfig."""
        from ..utils.sandbox import docker_available, run_in_docker

        if not docker_available():
            return ToolResult(False, "",
                              error="sandbox.enabled=true but `docker` is not on PATH")

        # Write code to a temp file INSIDE the workspace so docker can mount it.
        code_path = ctx.workspace / ".ai_agent_sandbox_code.py"
        code_path.write_text(args.code, encoding="utf-8")
        try:
            res = await run_in_docker(
                image=sandbox_cfg.python_image,
                argv=["python", "-I", "/workspace/.ai_agent_sandbox_code.py"],
                workspace=ctx.workspace,
                allow_network=sandbox_cfg.allow_network,
                mount_workspace_writable=sandbox_cfg.mount_workspace_writable,
                timeout=min(args.timeout, sandbox_cfg.timeout_seconds),
            )
        finally:
            try:
                code_path.unlink()
            except OSError:
                pass

        if res.timed_out:
            return ToolResult(False, "", error=res.stderr)

        out = res.stdout[:_MAX_OUTPUT]
        err = res.stderr[:_MAX_OUTPUT]
        parts = [f"exit_code={res.exit_code}  [sandboxed: {sandbox_cfg.python_image}]"]
        if out:
            parts.append(f"--- stdout ---\n{out.rstrip()}")
        if err:
            parts.append(f"--- stderr ---\n{err.rstrip()}")
        return ToolResult(
            res.exit_code == 0,
            "\n".join(parts),
            data={"exit_code": res.exit_code, "sandboxed": True},
            error=None if res.exit_code == 0 else f"exit code {res.exit_code}",
        )
