"""Sandbox helper basics (no Docker required for these tests)."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.config import SandboxConfig, SafetyConfig
from ai_agent.utils.sandbox import SandboxResult, docker_available


def test_sandbox_config_defaults():
    s = SandboxConfig()
    assert s.enabled is False
    assert s.python_image == "python:3.13-slim"
    assert s.allow_network is False
    assert s.mount_workspace_writable is False


def test_safety_includes_sandbox():
    s = SafetyConfig()
    assert isinstance(s.sandbox, SandboxConfig)


def test_docker_available_returns_bool():
    assert isinstance(docker_available(), bool)


def test_sandbox_result_dataclass():
    r = SandboxResult(exit_code=0, stdout="hello", stderr="")
    assert r.exit_code == 0
    assert not r.timed_out


def _docker_daemon_running() -> bool:
    """CLI installed AND daemon responds. Skip integration test otherwise."""
    if not docker_available():
        return False
    import subprocess
    try:
        out = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(not _docker_daemon_running(), reason="docker daemon not running")
async def test_run_in_docker_echo(tmp_path):
    """Integration test — only runs if docker exists AND daemon is up."""
    from ai_agent.utils.sandbox import run_in_docker
    r = await run_in_docker(
        image="alpine:latest",
        argv=["echo", "from-sandbox"],
        workspace=tmp_path,
        allow_network=False,
        mount_workspace_writable=False,
        timeout=60,
    )
    assert r.exit_code == 0
    assert "from-sandbox" in r.stdout
