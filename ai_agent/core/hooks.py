"""Lifecycle hook runner.

For each configured event, runs the user's shell command and pipes a JSON
payload to stdin. Captures stdout/stderr and exit code.

For `pre_tool_use` with `block_on_error=True`, a non-zero exit prevents the
tool from running — the result is a "denied" event with the hook's stderr.
This is the only hook that can change the agent's behaviour; all others are
fire-and-forget.

Hooks run sequentially in declaration order. Exceptions never crash the
agent loop — they're logged and skipped.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from ..config import HookSpec
from ..utils.logging import get_logger
from ..utils.shell import shell_invocation

logger = get_logger("hooks")


@dataclass
class HookResult:
    ok: bool                 # True = command exited 0
    exit_code: int | None
    stdout: str
    stderr: str
    blocked: bool = False    # True if this hook should block the action (pre_tool_use only)


async def run_hooks(
    hooks: list[HookSpec],
    payload: dict[str, Any],
    *,
    tool_name: str | None = None,
    blocking: bool = False,
) -> list[HookResult]:
    """Execute every matching hook. Returns one HookResult per executed hook.

    `tool_name` lets pre/post_tool_use hooks filter by their `tools` allowlist.
    `blocking=True` honours each hook's `block_on_error` (used by pre_tool_use).
    """
    results: list[HookResult] = []
    if not hooks:
        return results
    payload_json = json.dumps(payload, default=str)

    for spec in hooks:
        if spec.tools and tool_name is not None and tool_name not in spec.tools:
            continue
        try:
            result = await _exec_hook(spec, payload_json)
        except Exception as e:
            logger.warning("hook_error", command=spec.command, error=str(e))
            result = HookResult(False, None, "", str(e))
        if blocking and spec.block_on_error and not result.ok:
            result.blocked = True
            results.append(result)
            # Stop running further hooks once one blocks
            return results
        results.append(result)
    return results


async def _exec_hook(spec: HookSpec, payload_json: str) -> HookResult:
    argv = shell_invocation(None, spec.command)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(payload_json.encode("utf-8")),
            timeout=spec.timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return HookResult(False, None, "", f"hook timed out after {spec.timeout}s")

    return HookResult(
        ok=proc.returncode == 0,
        exit_code=proc.returncode,
        stdout=stdout.decode("utf-8", errors="replace"),
        stderr=stderr.decode("utf-8", errors="replace"),
    )
