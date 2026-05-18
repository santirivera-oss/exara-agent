"""Background process manager + bash_background / monitor / kill."""
from __future__ import annotations

import sys
import time

import pytest

from ai_agent.tools.background import BashBackground, KillProcess, Monitor, ProcessManager
from ai_agent.tools.base import ToolContext


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


@pytest.fixture
async def manager():
    m = ProcessManager()
    yield m
    await m.kill_all()


@pytest.fixture
def ctx(tmp_path, manager):
    return ToolContext(
        workspace=tmp_path, settings=None, logger=_DummyLogger(),
        extra={"processes": manager},
    )


async def test_bash_background_returns_id(ctx, manager):
    # A short-lived command — should still get an id.
    if sys.platform == "win32":
        cmd = "echo hi"
    else:
        cmd = "echo hi"
    r = await BashBackground().run({"command": cmd}, ctx)
    assert r.success
    assert "started" in r.output
    pid = r.data["id"]
    assert pid in manager.procs


async def test_monitor_reads_output(ctx, manager):
    # Spawn a process that prints lines slowly. Use python so it's cross-platform.
    code = "import time, sys\nfor i in range(3):\n  print('line', i, flush=True)\n  time.sleep(0.1)\n"
    cmd = f'{sys.executable} -c "{code}"'
    r = await BashBackground().run({"command": cmd}, ctx)
    pid = r.data["id"]

    # Wait a moment for output to land
    import asyncio
    await asyncio.sleep(1.0)

    m = await Monitor().run({"id": pid, "max_lines": 50}, ctx)
    assert m.success
    assert "line 0" in m.output or "line 1" in m.output or "line 2" in m.output


async def test_monitor_until_pattern(ctx, manager):
    code = "import time, sys\nprint('starting', flush=True)\ntime.sleep(0.3)\nprint('READY', flush=True)\ntime.sleep(2)\n"
    cmd = f'{sys.executable} -c "{code}"'
    r = await BashBackground().run({"command": cmd}, ctx)
    pid = r.data["id"]

    t0 = time.time()
    m = await Monitor().run({"id": pid, "until_pattern": r"READY", "timeout": 5}, ctx)
    elapsed = time.time() - t0

    assert m.success
    assert "READY" in m.output
    # Should have returned shortly after READY appeared, not waited the full timeout
    assert elapsed < 4.0


async def test_monitor_unknown_id_errors(ctx):
    r = await Monitor().run({"id": "deadbeef", "max_lines": 10}, ctx)
    assert not r.success
    assert "unknown process id" in (r.error or "").lower()


async def test_kill_process(ctx, manager):
    # Use a longer-running process
    if sys.platform == "win32":
        code = "import time\nwhile True:\n  time.sleep(1)\n"
        cmd = f'{sys.executable} -c "{code}"'
    else:
        cmd = "sleep 30"
    r = await BashBackground().run({"command": cmd}, ctx)
    pid = r.data["id"]
    bp = manager.get(pid)
    assert bp.alive

    k = await KillProcess().run({"id": pid}, ctx)
    assert k.success
    # Re-fetch — should no longer be alive
    import asyncio
    await asyncio.sleep(0.1)
    assert not bp.alive
