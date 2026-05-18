"""web_fetch tests — mocked HTTP, no real network."""
from __future__ import annotations

import httpx
import pytest

from ai_agent.tools.base import ToolContext
from ai_agent.tools.web import WebFetch, _extract_around, _strip_html


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(workspace=tmp_path, settings=None, logger=_DummyLogger())


def test_strip_html_basic():
    html = "<html><head><title>x</title><script>alert(1)</script></head><body><h1>Title</h1><p>Hello <b>world</b>.</p></body></html>"
    text = _strip_html(html)
    assert "Title" in text
    assert "Hello world." in text
    assert "alert(1)" not in text


def test_strip_html_removes_styles():
    html = "<html><style>body{color:red}</style><p>visible</p></html>"
    text = _strip_html(html)
    assert "visible" in text
    assert "color:red" not in text


async def test_web_fetch_rejects_non_http(ctx):
    r = await WebFetch().run({"url": "file:///etc/passwd"}, ctx)
    assert not r.success
    assert "http" in (r.error or "").lower()


async def test_web_fetch_handles_404(ctx, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler)
    # Patch the AsyncClient constructor inside the tool module
    import ai_agent.tools.web as web_mod

    real = web_mod.httpx.AsyncClient

    def fake_client(*_a, **kw):
        kw["transport"] = transport
        return real(*_a, **kw)

    monkeypatch.setattr(web_mod.httpx, "AsyncClient", fake_client)

    r = await WebFetch().run({"url": "https://example.com/missing"}, ctx)
    assert not r.success
    assert "404" in (r.error or "")


def test_extract_around_basic():
    text = "intro line\nblah\nthe TARGET method does X\nmore detail\nunrelated tail\nanother section"
    out, n = _extract_around(text, "target", context_lines=1)
    assert n == 1
    assert "TARGET" in out
    assert "blah" in out  # context above
    assert "more detail" in out  # context below
    assert "unrelated tail" not in out


def test_extract_around_merges_adjacent_matches():
    text = "\n".join(["line a", "target one", "line b", "line c", "target two", "line d"])
    out, n = _extract_around(text, "target", context_lines=2)
    assert n == 2
    # adjacent windows should merge into one chunk
    assert "--- match ---" not in out
    assert "line a" in out and "line d" in out


def test_extract_around_no_match():
    out, n = _extract_around("foo bar baz", "xyz", context_lines=2)
    assert n == 0
    assert out == ""


async def test_web_fetch_with_extract(ctx, monkeypatch):
    big_html = (
        "<html><body>"
        + "<p>filler paragraph one</p>" * 20
        + "<p>The get_nowait method removes an item immediately.</p>"
        + "<p>filler paragraph two</p>" * 20
        + "</body></html>"
    )

    def handler(request):
        return httpx.Response(200, text=big_html, headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    import ai_agent.tools.web as web_mod
    real = web_mod.httpx.AsyncClient

    def fake_client(*_a, **kw):
        kw["transport"] = transport
        return real(*_a, **kw)

    monkeypatch.setattr(web_mod.httpx, "AsyncClient", fake_client)

    r = await WebFetch().run(
        {"url": "https://example.com/", "extract": "get_nowait", "context_lines": 1},
        ctx,
    )
    assert r.success
    assert "Extracted 1 match" in r.output
    assert "get_nowait method removes an item" in r.output
    # Filler must not be present — extraction must have narrowed the output.
    assert r.output.count("filler paragraph one") <= 1
    assert r.output.count("filler paragraph two") <= 1


async def test_web_fetch_extract_no_match(ctx, monkeypatch):
    def handler(request):
        return httpx.Response(200, text="<html><body><p>nothing to see</p></body></html>",
                              headers={"content-type": "text/html"})

    transport = httpx.MockTransport(handler)
    import ai_agent.tools.web as web_mod
    real = web_mod.httpx.AsyncClient

    def fake_client(*_a, **kw):
        kw["transport"] = transport
        return real(*_a, **kw)

    monkeypatch.setattr(web_mod.httpx, "AsyncClient", fake_client)

    r = await WebFetch().run(
        {"url": "https://example.com/", "extract": "missing-term"}, ctx,
    )
    assert r.success
    assert "No matches" in r.output


async def test_web_fetch_html_stripped(ctx, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><body><h1>Docs</h1><script>x</script><p>Body text.</p></body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    transport = httpx.MockTransport(handler)
    import ai_agent.tools.web as web_mod
    real = web_mod.httpx.AsyncClient

    def fake_client(*_a, **kw):
        kw["transport"] = transport
        return real(*_a, **kw)

    monkeypatch.setattr(web_mod.httpx, "AsyncClient", fake_client)

    r = await WebFetch().run({"url": "https://example.com/"}, ctx)
    assert r.success
    assert "Docs" in r.output
    assert "Body text." in r.output
    assert "<script>" not in r.output
