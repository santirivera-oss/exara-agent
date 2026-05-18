"""Project search — content grep + filename glob, with sensible defaults."""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from pydantic import BaseModel, Field

from ..utils.paths import resolve_in_workspace
from .base import Tool, ToolContext, ToolResult

_DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
    ".next", ".turbo", "target",
}
_BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz",
               ".tar", ".exe", ".dll", ".so", ".dylib", ".bin", ".ico",
               ".mp4", ".mp3", ".wav", ".woff", ".woff2"}


class SearchProjectArgs(BaseModel):
    pattern: str = Field(..., description="Regex pattern to search for (file content) — or glob if mode='filename'")
    mode: str = Field("content", description="'content' (regex search inside files) or 'filename' (glob match against paths)")
    path: str = Field(".", description="Directory to search")
    glob: str | None = Field(None, description="Restrict content search to filenames matching this glob (e.g. '*.py')")
    case_sensitive: bool = Field(False)
    max_results: int = Field(200)


class SearchProject(Tool):
    name = "search_project"
    description = (
        "Search project files. mode='content' greps inside text files using regex; "
        "mode='filename' globs against file paths. Skips common build/vendor dirs."
    )
    Args = SearchProjectArgs
    read_only = True

    async def _run(self, args: SearchProjectArgs, ctx: ToolContext) -> ToolResult:
        root = resolve_in_workspace(args.path, ctx.workspace)
        if not root.exists() or not root.is_dir():
            return ToolResult(False, "", error=f"not a directory: {root}")

        if args.mode == "filename":
            return self._search_filenames(root, args)
        if args.mode != "content":
            return ToolResult(False, "", error=f"unknown mode {args.mode!r}")
        try:
            flags = 0 if args.case_sensitive else re.IGNORECASE
            rx = re.compile(args.pattern, flags)
        except re.error as e:
            return ToolResult(False, "", error=f"invalid regex: {e}")

        results: list[str] = []
        for file in self._walk_files(root):
            if args.glob and not fnmatch.fnmatch(file.name, args.glob):
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    rel = file.relative_to(root)
                    snippet = line.strip()[:300]
                    results.append(f"{rel}:{i}: {snippet}")
                    if len(results) >= args.max_results:
                        results.append(f"... (truncated at {args.max_results})")
                        return ToolResult(True, "\n".join(results), data={"matches": len(results)})
        return ToolResult(
            True,
            "\n".join(results) if results else "(no matches)",
            data={"matches": len(results)},
        )

    def _search_filenames(self, root: Path, args: SearchProjectArgs) -> ToolResult:
        pat = args.pattern if args.case_sensitive else args.pattern.lower()
        hits: list[str] = []
        for file in self._walk_files(root):
            rel = str(file.relative_to(root))
            target = rel if args.case_sensitive else rel.lower()
            if fnmatch.fnmatch(target, pat):
                hits.append(rel)
                if len(hits) >= args.max_results:
                    hits.append(f"... (truncated at {args.max_results})")
                    break
        return ToolResult(True, "\n".join(hits) if hits else "(no matches)", data={"matches": len(hits)})

    @staticmethod
    def _walk_files(root: Path):
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _DEFAULT_IGNORE_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in _BINARY_EXT:
                continue
            yield path
