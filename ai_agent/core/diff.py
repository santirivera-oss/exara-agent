"""Generate human-readable unified diffs for write/edit/create/delete previews."""
from __future__ import annotations

import difflib
from pathlib import Path

from ..utils.paths import resolve_in_workspace

_MAX_DIFF_LINES = 400


def preview_for_tool(name: str, args: dict, workspace: Path) -> str | None:
    """Return a textual diff/preview, or None if no preview is meaningful."""
    try:
        if name == "write_file":
            return _diff_existing(workspace, args.get("path", ""), args.get("content", ""))
        if name == "edit_file":
            return _diff_edit(workspace, args)
        if name == "multi_edit":
            return _diff_multi_edit(workspace, args)
        if name == "create_file":
            return _diff_create(workspace, args.get("path", ""), args.get("content", ""))
        if name == "delete_file":
            return _diff_delete(workspace, args.get("path", ""))
    except Exception:
        # Previews are advisory — never block the tool because preview generation failed.
        return None
    return None


def _read(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _unified(old: str, new: str, label: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
        n=3,
    )
    out_lines = list(diff)
    if len(out_lines) > _MAX_DIFF_LINES:
        out_lines = out_lines[:_MAX_DIFF_LINES] + [f"... (+{len(out_lines) - _MAX_DIFF_LINES} more lines)\n"]
    return "".join(out_lines) or "(no textual change)"


def _diff_existing(workspace: Path, rel: str, new_content: str) -> str:
    p = resolve_in_workspace(rel, workspace)
    old = _read(p) or ""
    return _unified(old, new_content, p.name)


def _diff_edit(workspace: Path, args: dict) -> str:
    p = resolve_in_workspace(args.get("path", ""), workspace)
    old = _read(p)
    if old is None:
        return f"(file does not exist: {p.name})"
    old_s = args.get("old_string", "")
    new_s = args.get("new_string", "")
    if args.get("replace_all"):
        new = old.replace(old_s, new_s)
    else:
        new = old.replace(old_s, new_s, 1)
    return _unified(old, new, p.name)


def _diff_multi_edit(workspace: Path, args: dict) -> str:
    p = resolve_in_workspace(args.get("path", ""), workspace)
    old = _read(p)
    if old is None:
        return f"(file does not exist: {p.name})"
    working = old
    for op in args.get("edits") or []:
        o = op.get("old_string", "")
        n = op.get("new_string", "")
        working = working.replace(o, n) if op.get("replace_all") else working.replace(o, n, 1)
    return _unified(old, working, p.name)


def _diff_create(workspace: Path, rel: str, content: str) -> str:
    p = resolve_in_workspace(rel, workspace)
    return _unified("", content, p.name)


def _diff_delete(workspace: Path, rel: str) -> str:
    p = resolve_in_workspace(rel, workspace)
    old = _read(p) or ""
    return _unified(old, "", p.name)
