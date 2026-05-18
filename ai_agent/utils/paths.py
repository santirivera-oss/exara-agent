"""Path safety helpers — keep filesystem ops inside the workspace by default."""
from __future__ import annotations

from pathlib import Path


def resolve_in_workspace(path: str | Path, workspace: Path, *, allow_outside: bool = False) -> Path:
    """Resolve a (possibly relative) path against the workspace root.

    Raises ValueError if the resolved path escapes the workspace and `allow_outside`
    is False — this is the first line of defence against tools writing to arbitrary
    locations on disk. Tools that legitimately need to escape (e.g. installing global
    packages) opt in via allow_outside=True and the safety layer logs the action.
    """
    p = Path(path)
    if not p.is_absolute():
        p = workspace / p
    p = p.resolve()
    ws = workspace.resolve()
    if not allow_outside:
        try:
            p.relative_to(ws)
        except ValueError as e:
            raise ValueError(
                f"Path '{p}' is outside workspace '{ws}'. "
                "Pass allow_outside=True if this is intentional."
            ) from e
    return p
