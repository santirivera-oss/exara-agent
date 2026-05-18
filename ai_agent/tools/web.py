"""web_fetch — download a URL and return readable plain text.

Uses httpx + stdlib HTMLParser so we don't need to pull in BeautifulSoup/lxml
for the basic case. For sites that need JS execution this won't work — that
belongs in a future browser/playwright tool.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Iterable

import httpx
from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult

_DEFAULT_TIMEOUT = 30.0
_MAX_BYTES = 2_000_000  # 2MB hard cap on download size

_BLOCK_TAGS = {"script", "style", "noscript", "head", "iframe", "svg"}
_BREAK_TAGS = {
    "p", "br", "div", "li", "tr", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "pre",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Iterable[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in _BLOCK_TAGS:
            self._skip_depth += 1
        elif t in _BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in _BLOCK_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif t in _BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)

    def get_text(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _strip_html(body: str) -> str:
    extractor = _TextExtractor()
    try:
        extractor.feed(body)
    except Exception:
        # If the parser chokes on broken HTML, fall back to a regex strip.
        return re.sub(r"<[^>]+>", "", body).strip()
    return extractor.get_text()


def _extract_around(text: str, query: str, context_lines: int, max_chunks: int = 12) -> tuple[str, int]:
    """Return merged context windows around every case-insensitive occurrence
    of `query`. Returns (joined_chunks, total_matches). If query is not found,
    returns ("", 0) so the caller can decide what to do.
    """
    lines = text.splitlines()
    q = query.lower()
    match_lines = [i for i, line in enumerate(lines) if q in line.lower()]
    if not match_lines:
        return "", 0

    # Merge overlapping windows.
    windows: list[list[int]] = []
    for m in match_lines:
        start = max(0, m - context_lines)
        end = min(len(lines), m + context_lines + 1)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])

    visible = windows[:max_chunks]
    omitted_windows = len(windows) - len(visible)
    chunks = ["\n".join(lines[s:e]).rstrip() for s, e in visible]
    result = "\n\n--- match ---\n\n".join(chunks)
    if omitted_windows > 0:
        result += f"\n\n... ({omitted_windows} more matching section(s) omitted)"
    return result, len(match_lines)


class WebFetchArgs(BaseModel):
    url: str = Field(..., description="HTTP(S) URL to fetch")
    max_chars: int = Field(50_000, description="Cap on returned text length")
    raw: bool = Field(False, description="If true, return the raw body without HTML stripping")
    extract: str | None = Field(
        None,
        description=(
            "Optional case-insensitive query. If provided, only sections of the page "
            "containing this string are returned (with context_lines of context above "
            "and below). Use this to keep the context tight when you only care about a "
            "specific term — e.g. extract='get_nowait' on a long docs page."
        ),
    )
    context_lines: int = Field(
        6, description="Lines of context above and below each extract match",
    )


class WebFetch(Tool):
    name = "web_fetch"
    description = (
        "Fetch a URL and return its text content. Strips HTML to readable text "
        "by default. Use for documentation, blog posts, RFCs, GitHub READMEs, "
        "API docs. Won't render JS-only pages."
    )
    Args = WebFetchArgs
    read_only = True

    async def _run(self, args: WebFetchArgs, ctx: ToolContext) -> ToolResult:
        if not args.url.startswith(("http://", "https://")):
            return ToolResult(False, "", error="url must start with http:// or https://")
        try:
            async with httpx.AsyncClient(
                timeout=_DEFAULT_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "ai-agent/0.1 (+local)"},
            ) as client:
                resp = await client.get(args.url)
                resp.raise_for_status()
                body = resp.text
        except httpx.HTTPStatusError as e:
            return ToolResult(False, "", error=f"HTTP {e.response.status_code} for {args.url}")
        except httpx.HTTPError as e:
            return ToolResult(False, "", error=f"fetch failed: {e}")

        if len(body) > _MAX_BYTES:
            body = body[:_MAX_BYTES]

        content_type = resp.headers.get("content-type", "").lower()
        if args.raw or not any(t in content_type for t in ("html", "xml")):
            text = body
        else:
            text = _strip_html(body)

        extract_note = ""
        match_count = 0
        if args.extract:
            extracted, match_count = _extract_around(
                text, args.extract, max(0, args.context_lines),
            )
            if extracted:
                text = extracted
                extract_note = f"Extracted {match_count} match(es) for {args.extract!r}\n"
            else:
                extract_note = (
                    f"No matches for {args.extract!r}. Returning the head of the full page.\n"
                )
                text = text[: min(len(text), 8000)]

        truncated = False
        if len(text) > args.max_chars:
            text = text[: args.max_chars]
            truncated = True

        header = f"URL: {args.url}\nHTTP: {resp.status_code}\nContent-Type: {content_type}\n"
        if extract_note:
            header += extract_note
        if truncated:
            header += f"[truncated to {args.max_chars} chars]\n"
        return ToolResult(
            True,
            header + "\n" + text,
            data={
                "url": str(resp.url),
                "status_code": resp.status_code,
                "content_type": content_type,
                "length": len(text),
                "extract": args.extract,
                "matches": match_count,
            },
        )
