"""PDF reading tool — extract text from PDF documents.

Uses PyMuPDF (`fitz`). For huge PDFs the caller should pass `pages` to read
a slice, otherwise output is capped at `max_chars`.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..utils.paths import resolve_in_workspace
from .base import Tool, ToolContext, ToolResult


class ReadPdfArgs(BaseModel):
    path: str = Field(..., description="Path to PDF file in the workspace")
    pages: str | None = Field(
        None,
        description=(
            "Optional page range, e.g. '1-5' (inclusive), '3', or '10-20'. "
            "Defaults to whole document. Pages are 1-indexed."
        ),
    )
    max_chars: int = Field(
        80_000,
        description="Hard cap on returned text length. Output is truncated past this.",
    )


class ReadPdf(Tool):
    name = "read_pdf"
    description = (
        "Extract text from a PDF file. Specify `pages` (e.g. '1-5') to read a slice; "
        "leave empty for the whole document. Useful for docs, papers, contracts, "
        "manuals — anything where you'd otherwise have to copy/paste."
    )
    Args = ReadPdfArgs
    read_only = True

    async def _run(self, args: ReadPdfArgs, ctx: ToolContext) -> ToolResult:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return ToolResult(False, "", error="pymupdf not installed — run: pip install pymupdf")

        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"PDF not found: {p}")
        if not p.is_file():
            return ToolResult(False, "", error=f"not a file: {p}")

        try:
            doc = fitz.open(str(p))
        except Exception as e:
            return ToolResult(False, "", error=f"failed to open PDF: {e}")

        try:
            total = doc.page_count
            start, end = _parse_page_range(args.pages, total)
            if start < 1 or end > total or start > end:
                return ToolResult(
                    False, "",
                    error=f"page range {args.pages!r} out of bounds (PDF has {total} pages)",
                )

            chunks: list[str] = [f"PDF: {p.name}  ({total} pages, reading {start}-{end})\n"]
            for n in range(start - 1, end):  # PyMuPDF is 0-indexed
                page = doc.load_page(n)
                text = page.get_text("text") or ""
                if text.strip():
                    chunks.append(f"\n--- page {n + 1} ---\n{text.rstrip()}")
            body = "\n".join(chunks)

            truncated = False
            if len(body) > args.max_chars:
                body = body[: args.max_chars] + f"\n... (+{len(body) - args.max_chars} chars truncated)"
                truncated = True

            return ToolResult(
                True,
                body,
                data={
                    "path": str(p),
                    "total_pages": total,
                    "pages_read": end - start + 1,
                    "truncated": truncated,
                },
            )
        finally:
            doc.close()


def _parse_page_range(spec: str | None, total: int) -> tuple[int, int]:
    """Parse '1-5' / '3' / None into (start, end) inclusive, 1-indexed."""
    if not spec:
        return 1, total
    spec = spec.strip()
    if "-" in spec:
        a, b = spec.split("-", 1)
        return int(a.strip()), int(b.strip())
    n = int(spec)
    return n, n
