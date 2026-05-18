"""Background shell processes.

`bash_background` launches a command that may run indefinitely (dev servers,
test watchers, build pipelines) without blocking the agent loop. The
`ProcessManager` owns the subprocesses, drains their stdout/stderr into bounded
ring buffers, and exposes them via id.

Companion tools:
  monitor(id, until_pattern?, timeout?) — read what's accumulated so far,
                                          optionally wait for a regex to appear
  kill_process(id)
  list_processes()
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from ..utils.shell import ShellNotAvailable, shell_invocation
from .base import Tool, ToolContext, ToolResult

_BUF_LINES = 2000
_MAX_OUT_LINES = 400  # cap returned to the model per monitor call


@dataclass
class BackgroundProcess:
    id: str
    command: str
    cwd: str
    proc: asyncio.subprocess.Process
    started_at: float
    stdout_buf: deque[str] = field(default_factory=lambda: deque(maxlen=_BUF_LINES))
    stderr_buf: deque[str] = field(default_factory=lambda: deque(maxlen=_BUF_LINES))
    _drain_task: asyncio.Task | None = None

    @property
    def exit_code(self) -> int | None:
        return self.proc.returncode

    @property
    def alive(self) -> bool:
        return self.proc.returncode is None


class ProcessManager:
    def __init__(self) -> None:
        self.procs: dict[str, BackgroundProcess] = {}

    async def spawn(self, command: str, cwd: str, shell: str | None) -> BackgroundProcess:
        argv = shell_invocation(shell, command)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        bp = BackgroundProcess(
            id=uuid.uuid4().hex[:8],
            command=command,
            cwd=cwd,
            proc=proc,
            started_at=time.time(),
        )
        self.procs[bp.id] = bp
        bp._drain_task = asyncio.create_task(self._drain(bp))
        return bp

    @staticmethod
    async def _drain(bp: BackgroundProcess) -> None:
        async def reader(stream, buf):
            while True:
                line = await stream.readline()
                if not line:
                    break
                buf.append(line.decode("utf-8", errors="replace").rstrip("\r\n"))
        await asyncio.gather(
            reader(bp.proc.stdout, bp.stdout_buf),
            reader(bp.proc.stderr, bp.stderr_buf),
        )
        await bp.proc.wait()

    def get(self, pid: str) -> BackgroundProcess | None:
        return self.procs.get(pid)

    async def kill(self, pid: str) -> bool:
        bp = self.procs.get(pid)
        if not bp or not bp.alive:
            return False
        try:
            bp.proc.kill()
        except ProcessLookupError:
            return False
        try:
            await asyncio.wait_for(bp.proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            return False
        return True

    async def kill_all(self) -> None:
        for pid in list(self.procs):
            await self.kill(pid)

    def list_all(self) -> list[BackgroundProcess]:
        return list(self.procs.values())


# --- bash_background --------------------------------------------------------

class BashBackgroundArgs(BaseModel):
    command: str = Field(..., description="Shell command. Will run in the background until killed or finished.")
    cwd: str | None = Field(None, description="Working directory (defaults to workspace)")
    shell: str | None = Field(
        None,
        description="Override shell ('pwsh', 'powershell', 'cmd', 'bash', 'sh'). Defaults to platform native.",
    )


class BashBackground(Tool):
    name = "bash_background"
    description = (
        "Launch a shell command in the background — returns immediately with a process id "
        "instead of waiting. Use for dev servers, file watchers, long builds, anything that "
        "doesn't terminate quickly. Then use `monitor` with the returned id to read output."
    )
    Args = BashBackgroundArgs
    requires_confirmation = True

    async def _run(self, args: BashBackgroundArgs, ctx: ToolContext) -> ToolResult:
        mgr: ProcessManager | None = ctx.extra.get("processes")
        if mgr is None:
            return ToolResult(False, "", error="bash_background: no process manager in context")
        cwd = args.cwd or str(ctx.workspace)
        try:
            bp = await mgr.spawn(args.command, cwd, args.shell)
        except ShellNotAvailable as e:
            return ToolResult(False, "", error=str(e))
        except FileNotFoundError as e:
            return ToolResult(False, "", error=f"shell not found: {e}")
        return ToolResult(
            True,
            f"started [{bp.id}] {args.command}\n(use `monitor` with id={bp.id!r} to read output)",
            data={"id": bp.id, "command": args.command, "cwd": cwd, "pid": bp.proc.pid},
        )


# --- monitor ----------------------------------------------------------------

class MonitorArgs(BaseModel):
    id: str = Field(..., description="Process id returned by bash_background")
    max_lines: int = Field(200, description="Cap on output lines returned per stream")
    until_pattern: str | None = Field(
        None,
        description="Optional regex. If provided, monitor waits (up to timeout) for the pattern to appear in stdout or stderr before returning. Useful for 'wait until server is ready'.",
    )
    timeout: int = Field(30, description="Max seconds to wait when until_pattern is set")


class Monitor(Tool):
    name = "monitor"
    description = (
        "Read accumulated output from a background process. With `until_pattern`, waits "
        "(up to `timeout` seconds) for the regex to appear before returning — use it to "
        "block until a server prints 'Listening on port', a test starts, etc."
    )
    Args = MonitorArgs
    read_only = True

    async def _run(self, args: MonitorArgs, ctx: ToolContext) -> ToolResult:
        mgr: ProcessManager | None = ctx.extra.get("processes")
        if mgr is None:
            return ToolResult(False, "", error="monitor: no process manager in context")
        bp = mgr.get(args.id)
        if bp is None:
            return ToolResult(False, "", error=f"unknown process id: {args.id!r}")

        if args.until_pattern:
            try:
                rx = re.compile(args.until_pattern)
            except re.error as e:
                return ToolResult(False, "", error=f"invalid regex: {e}")
            deadline = time.time() + max(1, args.timeout)
            while time.time() < deadline:
                if any(rx.search(line) for line in bp.stdout_buf) or \
                        any(rx.search(line) for line in bp.stderr_buf):
                    break
                if not bp.alive:
                    break
                await asyncio.sleep(0.3)

        max_lines = max(1, min(args.max_lines, _MAX_OUT_LINES))
        out = list(bp.stdout_buf)[-max_lines:]
        err = list(bp.stderr_buf)[-max_lines:]

        parts = [
            f"[{bp.id}] {bp.command}",
            f"alive={bp.alive}  exit_code={bp.exit_code}  "
            f"runtime={time.time() - bp.started_at:.1f}s",
        ]
        if out:
            parts.append(f"--- stdout (last {len(out)} line(s)) ---")
            parts.extend(out)
        if err:
            parts.append(f"--- stderr (last {len(err)} line(s)) ---")
            parts.extend(err)
        if not out and not err:
            parts.append("(no output yet)")

        return ToolResult(
            True,
            "\n".join(parts),
            data={
                "id": bp.id, "alive": bp.alive, "exit_code": bp.exit_code,
                "stdout_lines_total": len(bp.stdout_buf),
                "stderr_lines_total": len(bp.stderr_buf),
            },
        )


# --- kill_process -----------------------------------------------------------

class KillProcessArgs(BaseModel):
    id: str


class KillProcess(Tool):
    name = "kill_process"
    description = "Terminate a background process started with bash_background."
    Args = KillProcessArgs
    requires_confirmation = True

    async def _run(self, args: KillProcessArgs, ctx: ToolContext) -> ToolResult:
        mgr: ProcessManager | None = ctx.extra.get("processes")
        if mgr is None:
            return ToolResult(False, "", error="kill_process: no process manager in context")
        bp = mgr.get(args.id)
        if bp is None:
            return ToolResult(False, "", error=f"unknown process id: {args.id!r}")
        if not bp.alive:
            return ToolResult(True, f"[{bp.id}] already exited (code={bp.exit_code})")
        ok = await mgr.kill(args.id)
        if ok:
            return ToolResult(True, f"killed [{bp.id}] (exit_code={bp.exit_code})")
        return ToolResult(False, "", error=f"could not kill [{bp.id}]")


# --- list_processes ---------------------------------------------------------

class _NoArgs(BaseModel):
    pass


class ListProcesses(Tool):
    name = "list_processes"
    description = "List background processes spawned in this session."
    Args = _NoArgs
    read_only = True

    async def _run(self, args: _NoArgs, ctx: ToolContext) -> ToolResult:
        mgr: ProcessManager | None = ctx.extra.get("processes")
        if mgr is None:
            return ToolResult(True, "(no process manager)")
        procs = mgr.list_all()
        if not procs:
            return ToolResult(True, "(no background processes)")
        now = time.time()
        rows = [
            f"[{bp.id}] alive={bp.alive} exit={bp.exit_code} "
            f"runtime={now - bp.started_at:.1f}s  cmd={bp.command[:80]}"
            for bp in procs
        ]
        return ToolResult(True, "\n".join(rows), data={"count": len(procs)})
