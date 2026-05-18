"""Docker sandbox helpers — used by run_python and execute_terminal when
`settings.safety.sandbox.enabled` is true.

We don't pull a heavyweight Python lib (docker-py); instead we just shell
out to the `docker` CLI. That keeps the dependency tree zero and respects
whatever Docker setup the user already has (Docker Desktop, Rancher, podman
aliased as docker, etc.).
"""
from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


def docker_available() -> bool:
    return shutil.which("docker") is not None


async def run_in_docker(
    *,
    image: str,
    argv: list[str],
    workspace: Path,
    allow_network: bool,
    mount_workspace_writable: bool,
    timeout: int,
) -> SandboxResult:
    """Run `argv` inside a one-shot Docker container.

    Container is removed after exit (`--rm`). Workspace is mounted at
    /workspace; the container's working directory is set there. Network
    can be disabled (`--network=none`) for full isolation.
    """
    mount_mode = "rw" if mount_workspace_writable else "ro"
    docker_cmd = [
        "docker", "run", "--rm",
        "-i",
        "--workdir", "/workspace",
        "-v", f"{str(workspace.resolve())}:/workspace:{mount_mode}",
    ]
    if not allow_network:
        docker_cmd += ["--network", "none"]
    docker_cmd.append(image)
    docker_cmd.extend(argv)

    proc = await asyncio.create_subprocess_exec(
        *docker_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return SandboxResult(-1, "", f"sandboxed command timed out after {timeout}s", timed_out=True)

    return SandboxResult(
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )
