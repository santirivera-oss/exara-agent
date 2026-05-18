"""File operations — read, write, edit, create, delete, list."""
from __future__ import annotations

from pathlib import Path

import anyio
from pydantic import BaseModel, Field

from ..utils.paths import resolve_in_workspace
from .base import Tool, ToolContext, ToolResult


def _looks_binary(data: bytes, sample: int = 8192) -> bool:
    """Heuristic: null bytes or >30% non-text chars in the first 8KB → binary."""
    if not data:
        return False
    head = data[:sample]
    if b"\x00" in head:
        return True
    text_chars = bytes(range(32, 127)) + b"\n\r\t\b\f"
    nontext = sum(1 for b in head if b not in text_chars)
    return nontext / len(head) > 0.30


# --- read_file ----------------------------------------------------------------

class ReadFileArgs(BaseModel):
    path: str = Field(..., description="Path to file (relative to workspace or absolute)")
    start_line: int | None = Field(None, description="1-indexed start line")
    end_line: int | None = Field(None, description="1-indexed end line (inclusive)")
    max_bytes: int = Field(200_000, description="Hard cap on bytes returned")


class ReadFile(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file. Optionally slice by line range. Returns line-numbered content. Refuses binary files — use run_python with sqlite3/Pillow/etc. for those."
    Args = ReadFileArgs
    read_only = True

    async def _run(self, args: ReadFileArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"file not found: {p}")
        if not p.is_file():
            return ToolResult(False, "", error=f"not a file: {p}")
        data = await anyio.Path(p).read_bytes()
        if _looks_binary(data):
            return ToolResult(
                False, "",
                error=(
                    f"{p.name} appears to be binary ({len(data)} bytes). "
                    "read_file only handles text. For databases use run_python "
                    "with sqlite3; for images use a vision-capable tool."
                ),
            )
        if len(data) > args.max_bytes:
            data = data[: args.max_bytes]
            truncated = True
        else:
            truncated = False
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()
        s = (args.start_line or 1) - 1
        e = args.end_line if args.end_line is not None else len(lines)
        s = max(0, s)
        e = max(s, min(e, len(lines)))
        chunk = lines[s:e]
        numbered = "\n".join(f"{i + s + 1:6d}\t{line}" for i, line in enumerate(chunk))
        suffix = "\n[truncated]" if truncated else ""
        return ToolResult(True, numbered + suffix, data={"path": str(p), "lines": len(chunk)})


# --- write_file ---------------------------------------------------------------

class WriteFileArgs(BaseModel):
    path: str = Field(..., description="Path to file")
    content: str = Field(..., description="Full new file contents (replaces existing)")


class WriteFile(Tool):
    name = "write_file"
    description = "Overwrite a file with the given content. Creates parent directories. Use for new files or full rewrites; prefer edit_file for small changes."
    Args = WriteFileArgs

    async def _run(self, args: WriteFileArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        p.parent.mkdir(parents=True, exist_ok=True)
        await anyio.Path(p).write_text(args.content, encoding="utf-8")
        return ToolResult(True, f"wrote {len(args.content)} chars to {p}", data={"path": str(p)})


# --- edit_file ----------------------------------------------------------------

class EditFileArgs(BaseModel):
    path: str = Field(..., description="Path to file")
    old_string: str = Field(..., description="Exact text to find (must match once unless replace_all=true)")
    new_string: str = Field(..., description="Replacement text")
    replace_all: bool = Field(False, description="Replace every occurrence")


class EditFile(Tool):
    name = "edit_file"
    description = "Find-and-replace inside a file. Fails if old_string is missing or not unique (unless replace_all=true)."
    Args = EditFileArgs

    async def _run(self, args: EditFileArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"file not found: {p}")
        text = await anyio.Path(p).read_text(encoding="utf-8")
        count = text.count(args.old_string)
        if count == 0:
            return ToolResult(False, "", error="old_string not found")
        if count > 1 and not args.replace_all:
            return ToolResult(False, "", error=f"old_string matches {count} times; pass replace_all=true or extend context")
        new_text = text.replace(args.old_string, args.new_string)
        await anyio.Path(p).write_text(new_text, encoding="utf-8")
        return ToolResult(True, f"replaced {count} occurrence(s) in {p}", data={"path": str(p), "replacements": count})


# --- multi_edit ---------------------------------------------------------------

class _EditOp(BaseModel):
    old_string: str = Field(..., description="Text to find")
    new_string: str = Field(..., description="Replacement text")
    replace_all: bool = Field(False, description="Replace every occurrence")


class MultiEditArgs(BaseModel):
    path: str = Field(..., description="Path to file")
    edits: list[_EditOp] = Field(..., description="Ordered list of edits to apply atomically")


class MultiEdit(Tool):
    name = "multi_edit"
    description = (
        "Apply several find/replace edits to a single file atomically. "
        "Edits are applied in order; if any one fails (missing or ambiguous match) "
        "the file is left untouched. Prefer this over multiple edit_file calls."
    )
    Args = MultiEditArgs

    async def _run(self, args: MultiEditArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"file not found: {p}")
        text = await anyio.Path(p).read_text(encoding="utf-8")

        working = text
        applied = 0
        for i, op in enumerate(args.edits, start=1):
            count = working.count(op.old_string)
            if count == 0:
                return ToolResult(False, "", error=f"edit {i}: old_string not found")
            if count > 1 and not op.replace_all:
                return ToolResult(False, "", error=f"edit {i}: matches {count} times; set replace_all or extend context")
            working = working.replace(op.old_string, op.new_string) if op.replace_all \
                else working.replace(op.old_string, op.new_string, 1)
            applied += 1

        await anyio.Path(p).write_text(working, encoding="utf-8")
        return ToolResult(
            True,
            f"applied {applied} edit(s) to {p}",
            data={"path": str(p), "edits_applied": applied},
        )


# --- create_file --------------------------------------------------------------

class CreateFileArgs(BaseModel):
    path: str = Field(..., description="Path to new file")
    content: str = Field("", description="Initial content")


class CreateFile(Tool):
    name = "create_file"
    description = "Create a new file. Fails if the file already exists."
    Args = CreateFileArgs

    async def _run(self, args: CreateFileArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if p.exists():
            return ToolResult(False, "", error=f"file already exists: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        await anyio.Path(p).write_text(args.content, encoding="utf-8")
        return ToolResult(True, f"created {p}", data={"path": str(p)})


# --- delete_file --------------------------------------------------------------

class DeleteFileArgs(BaseModel):
    path: str = Field(..., description="Path to file (not a directory)")


class DeleteFile(Tool):
    name = "delete_file"
    description = "Delete a single file. Refuses to delete directories — use execute_terminal with explicit user consent for those."
    Args = DeleteFileArgs
    requires_confirmation = True

    async def _run(self, args: DeleteFileArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"path does not exist: {p}")
        if p.is_dir():
            return ToolResult(False, "", error="refusing to delete a directory via delete_file")
        p.unlink()
        return ToolResult(True, f"deleted {p}", data={"path": str(p)})


# --- list_directory -----------------------------------------------------------

# Directories that almost never have signal — skipped by default in recursive listings.
_LIST_IGNORE_DIRS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".turbo", "target", ".egg-info",
}


class ListDirectoryArgs(BaseModel):
    path: str = Field(".", description="Directory path")
    recursive: bool = Field(False, description="Walk subdirectories")
    max_entries: int = Field(500, description="Cap on number of entries returned")
    include_hidden: bool = Field(False, description="Include dot-files")
    include_cache: bool = Field(
        False,
        description="Include __pycache__, node_modules, .git, build dirs, etc. Default: false.",
    )


class ListDirectory(Tool):
    name = "list_directory"
    description = (
        "List entries in a directory. recursive=true walks subdirectories. "
        "Cache and vendor dirs (__pycache__, node_modules, .git, .venv, dist/build) "
        "are skipped by default — set include_cache=true to see them."
    )
    Args = ListDirectoryArgs
    read_only = True

    async def _run(self, args: ListDirectoryArgs, ctx: ToolContext) -> ToolResult:
        root = resolve_in_workspace(args.path, ctx.workspace)
        if not root.exists():
            return ToolResult(False, "", error=f"directory not found: {root}")
        if not root.is_dir():
            return ToolResult(False, "", error=f"not a directory: {root}")

        entries: list[str] = []
        iterator = root.rglob("*") if args.recursive else root.iterdir()
        for entry in iterator:
            rel = entry.relative_to(root)
            parts = rel.parts
            if not args.include_hidden and any(p.startswith(".") for p in parts):
                continue
            if not args.include_cache and any(p in _LIST_IGNORE_DIRS for p in parts):
                continue
            marker = "/" if entry.is_dir() else ""
            entries.append(f"{rel}{marker}")
            if len(entries) >= args.max_entries:
                entries.append(f"... (truncated at {args.max_entries})")
                break
        entries.sort()
        return ToolResult(True, "\n".join(entries) or "(empty)", data={"path": str(root), "count": len(entries)})
