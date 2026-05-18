"""Browser automation tools via Playwright (optional dependency).

These let the agent open JS-rendered pages, click, fill forms, screenshot.
A single headless browser + context lives for the lifetime of the session
(persistent state across tool calls), kept by the Agent so cookies and
login state survive.

Install:
    pip install -e .[browser]
    playwright install chromium
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..utils.paths import resolve_in_workspace
from .base import Tool, ToolContext, ToolResult

_BROWSER_KEY = "_playwright_browser"

_MAX_TEXT = 20_000  # cap per get_text call


async def _get_or_open_browser(ctx: ToolContext) -> tuple[Any, Any]:
    """Lazily start a Playwright browser+page for this session. Returns (browser, page)."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise RuntimeError("playwright not installed — run: pip install -e .[browser] && playwright install chromium") from e

    cache = ctx.extra.setdefault(_BROWSER_KEY, {})
    if cache.get("page") is not None:
        return cache["browser"], cache["page"]

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1280, "height": 800})
    cache.update({"pw": pw, "browser": browser, "page": page})
    return browser, page


async def close_browser_if_open(extra: dict[str, Any]) -> None:
    """Tear down the browser cached in ctx.extra. Called from Agent.shutdown()."""
    cache = extra.get(_BROWSER_KEY)
    if not cache:
        return
    try:
        page = cache.get("page")
        browser = cache.get("browser")
        pw = cache.get("pw")
        if page:
            await page.close()
        if browser:
            await browser.close()
        if pw:
            await pw.stop()
    except Exception:
        pass


# --- browser_navigate -------------------------------------------------------

class NavigateArgs(BaseModel):
    url: str = Field(..., description="URL to navigate to (http/https)")
    wait_until: str = Field("load", description="load | domcontentloaded | networkidle")
    timeout_ms: int = Field(15000)


class BrowserNavigate(Tool):
    name = "browser_navigate"
    description = "Open a URL in a persistent headless browser. State (cookies, scroll) survives between calls."
    Args = NavigateArgs

    async def _run(self, args: NavigateArgs, ctx: ToolContext) -> ToolResult:
        if not args.url.startswith(("http://", "https://")):
            return ToolResult(False, "", error="url must start with http(s)://")
        _, page = await _get_or_open_browser(ctx)
        resp = await page.goto(args.url, wait_until=args.wait_until, timeout=args.timeout_ms)
        title = await page.title()
        return ToolResult(True, f"opened {args.url}\nstatus={resp.status if resp else '?'}\ntitle={title}")


# --- browser_get_text -------------------------------------------------------

class GetTextArgs(BaseModel):
    selector: str | None = Field(None, description="CSS selector. If empty, returns the whole page text.")
    max_chars: int = Field(_MAX_TEXT)


class BrowserGetText(Tool):
    name = "browser_get_text"
    description = "Extract visible text from the current page (or from a CSS selector)."
    Args = GetTextArgs
    read_only = True

    async def _run(self, args: GetTextArgs, ctx: ToolContext) -> ToolResult:
        _, page = await _get_or_open_browser(ctx)
        if args.selector:
            text = await page.inner_text(args.selector)
        else:
            text = await page.inner_text("body")
        if len(text) > args.max_chars:
            text = text[: args.max_chars] + f"\n... (+{len(text) - args.max_chars} chars truncated)"
        return ToolResult(True, text)


# --- browser_click ----------------------------------------------------------

class ClickArgs(BaseModel):
    selector: str = Field(..., description="CSS selector for the element to click")
    timeout_ms: int = Field(5000)


class BrowserClick(Tool):
    name = "browser_click"
    description = "Click an element on the current page identified by a CSS selector."
    Args = ClickArgs

    async def _run(self, args: ClickArgs, ctx: ToolContext) -> ToolResult:
        _, page = await _get_or_open_browser(ctx)
        await page.click(args.selector, timeout=args.timeout_ms)
        return ToolResult(True, f"clicked {args.selector}")


# --- browser_fill -----------------------------------------------------------

class FillArgs(BaseModel):
    selector: str = Field(..., description="CSS selector for the input field")
    value: str = Field(..., description="Text to type")
    submit: bool = Field(False, description="Press Enter after filling")


class BrowserFill(Tool):
    name = "browser_fill"
    description = "Type into an input/textarea. Optionally submits the form by pressing Enter."
    Args = FillArgs

    async def _run(self, args: FillArgs, ctx: ToolContext) -> ToolResult:
        _, page = await _get_or_open_browser(ctx)
        await page.fill(args.selector, args.value)
        if args.submit:
            await page.press(args.selector, "Enter")
        return ToolResult(True, f"filled {args.selector} ({'submitted' if args.submit else 'no submit'})")


# --- browser_screenshot -----------------------------------------------------

class ScreenshotArgs(BaseModel):
    path: str = Field("screenshot.png", description="File path inside the workspace (PNG)")
    full_page: bool = Field(False, description="Capture the full scrollable page, not just viewport")


class BrowserScreenshot(Tool):
    name = "browser_screenshot"
    description = "Save a PNG screenshot of the current page. Use read_image afterwards if the agent needs to see it."
    Args = ScreenshotArgs

    async def _run(self, args: ScreenshotArgs, ctx: ToolContext) -> ToolResult:
        out = resolve_in_workspace(args.path, ctx.workspace)
        out.parent.mkdir(parents=True, exist_ok=True)
        _, page = await _get_or_open_browser(ctx)
        await page.screenshot(path=str(out), full_page=args.full_page)
        return ToolResult(True, f"saved screenshot to {out}", data={"path": str(out)})
