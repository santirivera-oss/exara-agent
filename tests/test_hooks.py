"""Lifecycle hooks runner."""
from __future__ import annotations

import sys

import pytest

from ai_agent.config import HookSpec
from ai_agent.core.hooks import run_hooks


async def test_hook_runs_and_captures_output():
    spec = HookSpec(command=f"{sys.executable} -c \"print('hello from hook')\"", timeout=5)
    results = await run_hooks([spec], {"event": "test"})
    assert len(results) == 1
    assert results[0].ok
    assert "hello from hook" in results[0].stdout


async def test_hook_failing_command_does_not_block_by_default():
    spec = HookSpec(command=f'{sys.executable} -c "import sys; sys.exit(1)"', timeout=5)
    results = await run_hooks([spec], {"event": "test"})
    assert len(results) == 1
    assert not results[0].ok
    assert not results[0].blocked


async def test_pre_tool_use_blocks_when_block_on_error():
    spec = HookSpec(
        command=f"{sys.executable} -c \"import sys; print('nope', file=sys.stderr); sys.exit(2)\"",
        block_on_error=True, timeout=5,
    )
    results = await run_hooks([spec], {"tool": "x"}, tool_name="x", blocking=True)
    assert len(results) == 1
    assert results[0].blocked
    assert "nope" in results[0].stderr


async def test_pre_tool_use_does_not_block_when_blocking_false():
    """Same failing hook but blocking=False (post_tool_use behavior)."""
    spec = HookSpec(command=f'{sys.executable} -c "import sys; sys.exit(2)"', block_on_error=True, timeout=5)
    results = await run_hooks([spec], {"tool": "x"}, tool_name="x", blocking=False)
    assert not results[0].blocked


async def test_tools_allowlist_filters_hooks():
    spec = HookSpec(command='echo wrong', tools=["only_this_tool"], timeout=5)
    results = await run_hooks([spec], {"tool": "different"}, tool_name="different")
    assert len(results) == 0


async def test_payload_reaches_hook_via_stdin():
    spec = HookSpec(
        command=f"{sys.executable} -c \"import sys, json; print(json.load(sys.stdin)['event'])\"",
        timeout=5,
    )
    results = await run_hooks([spec], {"event": "hello-payload"})
    assert results[0].ok
    assert "hello-payload" in results[0].stdout


async def test_hook_timeout_is_enforced():
    # Sleep longer than timeout
    spec = HookSpec(
        command=f'{sys.executable} -c "import time; time.sleep(3)"',
        timeout=1,
    )
    results = await run_hooks([spec], {})
    assert not results[0].ok
    assert "timed out" in results[0].stderr


async def test_first_blocking_hook_short_circuits_rest():
    """A blocking failure stops further hooks from running."""
    blocked = HookSpec(command=f'{sys.executable} -c "exit(1)"', block_on_error=True, timeout=5)
    after = HookSpec(command=f'{sys.executable} -c "print(\\"after\\")"', timeout=5)
    results = await run_hooks([blocked, after], {}, blocking=True)
    assert len(results) == 1  # didn't get to `after`
    assert results[0].blocked
