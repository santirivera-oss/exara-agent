"""Shell resolution shared by execute_terminal and bash_background.

Picks an actually-available shell rather than blindly trying the requested
binary. This avoids the classic Windows trap where the model asks for
`pwsh` (PowerShell Core) on a machine that only has `powershell` (PS 5.1).
"""
from __future__ import annotations

import shutil
import sys


class ShellNotAvailable(FileNotFoundError):
    pass


def shell_invocation(override: str | None, command: str) -> list[str]:
    """Return argv for running `command` through the best available shell.

    Precedence:
      1. Explicit `override` is honoured if the binary exists.
      2. If override is 'pwsh' but only 'powershell' exists (typical Windows),
         silently downgrade — they accept the same `-Command` flag.
      3. With no override on Windows: prefer pwsh, then powershell.
      4. With no override on Unix: prefer bash, then sh.
    """
    choice = (override or "").lower().strip()
    is_windows = sys.platform == "win32"

    # PowerShell — Core or Windows variant
    if choice in ("pwsh", "powershell") or (not choice and is_windows):
        # Try the requested binary first; if absent, fall back to the other PS variant.
        if choice == "pwsh":
            exe = shutil.which("pwsh") or shutil.which("powershell")
        elif choice == "powershell":
            exe = shutil.which("powershell") or shutil.which("pwsh")
        else:  # no override on Windows
            exe = shutil.which("pwsh") or shutil.which("powershell")
        if not exe:
            raise ShellNotAvailable("no PowerShell binary found on PATH (looked for pwsh, powershell)")
        return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]

    if choice == "cmd":
        exe = shutil.which("cmd") or shutil.which("cmd.exe")
        if not exe:
            raise ShellNotAvailable("cmd.exe not found on PATH")
        return [exe, "/d", "/c", command]

    # POSIX
    if choice in ("sh", ""):
        exe = shutil.which("bash") or shutil.which("sh") or "/bin/sh"
        return [exe, "-c", command]
    if choice == "bash":
        exe = shutil.which("bash") or "/bin/bash"
        return [exe, "-c", command]

    # Unknown override — try as a literal binary on PATH
    exe = shutil.which(choice)
    if not exe:
        raise ShellNotAvailable(f"shell {choice!r} not found on PATH")
    return [exe, "-c", command]
