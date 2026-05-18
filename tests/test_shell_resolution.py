"""shell_invocation picks an available binary."""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from ai_agent.utils.shell import ShellNotAvailable, shell_invocation


@pytest.fixture
def fake_which():
    """Patch shutil.which to control what 'exists' on PATH."""
    with patch("ai_agent.utils.shell.shutil.which") as m:
        yield m


def test_pwsh_falls_back_to_powershell_when_only_ps5(fake_which):
    # Only powershell.exe is installed (typical Windows)
    fake_which.side_effect = lambda x: "C:\\powershell.exe" if x == "powershell" else None
    argv = shell_invocation("pwsh", "echo hi")
    assert argv[0] == "C:\\powershell.exe"
    assert "-Command" in argv
    assert "echo hi" in argv


def test_pwsh_uses_pwsh_when_available(fake_which):
    fake_which.side_effect = lambda x: f"C:\\{x}.exe"
    argv = shell_invocation("pwsh", "echo hi")
    assert argv[0] == "C:\\pwsh.exe"


def test_powershell_falls_back_to_pwsh_when_only_core(fake_which):
    # Only pwsh installed (Linux/macOS with PS Core)
    fake_which.side_effect = lambda x: "/usr/bin/pwsh" if x == "pwsh" else None
    argv = shell_invocation("powershell", "echo hi")
    assert argv[0] == "/usr/bin/pwsh"


def test_no_powershell_at_all_raises(fake_which):
    fake_which.return_value = None
    with pytest.raises(ShellNotAvailable):
        shell_invocation("pwsh", "echo hi")


def test_cmd_invocation(fake_which):
    fake_which.side_effect = lambda x: "C:\\cmd.exe" if "cmd" in x else None
    argv = shell_invocation("cmd", "dir")
    assert argv[0] == "C:\\cmd.exe"
    assert argv[1:] == ["/d", "/c", "dir"]


def test_bash_invocation(fake_which):
    fake_which.side_effect = lambda x: "/bin/bash" if x == "bash" else None
    argv = shell_invocation("bash", "ls")
    assert argv == ["/bin/bash", "-c", "ls"]


def test_no_override_on_unix_prefers_bash(fake_which):
    if sys.platform == "win32":
        pytest.skip("unix-only behaviour")
    fake_which.side_effect = lambda x: f"/usr/bin/{x}"
    argv = shell_invocation("", "ls")
    assert "bash" in argv[0] or argv[0] == "/bin/sh"
