"""Friendly error mapping in OllamaProvider + provider construction checks."""
from __future__ import annotations

import httpx
import pytest

from ai_agent.models.ollama import ModelNotInstalledError, OllamaProvider
from ai_agent.models.openai_compat import OpenAICompatProvider


async def test_openai_compat_retries_on_429(monkeypatch):
    """Provider should retry up to MAX times when the server returns 429."""
    # Patch the sleep so the test is fast.
    import ai_agent.models.openai_compat as mod
    monkeypatch.setattr(mod, "_sleep_for_429", _no_sleep)

    call_count = {"n": 0}

    def handler(request):
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        })

    p = OpenAICompatProvider(base_url="https://x/v1", model="m", api_key="k")
    p._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    try:
        resp = await p.chat([])
        assert resp.content == "ok"
        assert call_count["n"] == 3
    finally:
        await p.aclose()


async def test_openai_compat_429_eventually_raises(monkeypatch):
    """If the server never recovers, the friendly rate-limit error surfaces."""
    import ai_agent.models.openai_compat as mod
    monkeypatch.setattr(mod, "_sleep_for_429", _no_sleep)

    def handler(request):
        return httpx.Response(429, json={"error": "rate limited"})

    p = OpenAICompatProvider(base_url="https://x/v1", model="m", api_key="k")
    p._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    try:
        from ai_agent.models.openai_compat import ProviderRateLimitError
        with pytest.raises(ProviderRateLimitError):
            await p.chat([])
    finally:
        await p.aclose()


async def _no_sleep(_resp, _attempt):
    """Drop-in replacement for _sleep_for_429 that doesn't actually sleep."""
    return 0.0


async def test_openai_compat_402_friendly():
    from ai_agent.models.openai_compat import ProviderQuotaError

    def handler(request):
        return httpx.Response(402, json={"error": {"message": "Insufficient credit"}})

    p = OpenAICompatProvider(base_url="https://x/v1", model="m", api_key="k")
    p._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    try:
        with pytest.raises(ProviderQuotaError) as exc:
            await p.chat([])
        assert "credit" in str(exc.value).lower()
        assert ":free" in str(exc.value)
    finally:
        await p.aclose()


async def test_openai_compat_401_friendly():
    from ai_agent.models.openai_compat import ProviderAuthError

    def handler(request):
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    p = OpenAICompatProvider(base_url="https://x/v1", model="m", api_key="k")
    p._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)
    try:
        with pytest.raises(ProviderAuthError) as exc:
            await p.chat([])
        assert "AI_AGENT_OPENAI_API_KEY" in str(exc.value)
    finally:
        await p.aclose()


def test_openai_compat_extra_headers_attached():
    p = OpenAICompatProvider(
        base_url="https://example.com/v1",
        model="m1",
        api_key="k",
        extra_headers={"HTTP-Referer": "https://my.app", "X-Title": "ai-agent"},
    )
    h = dict(p._client.headers)
    assert h.get("authorization") == "Bearer k"
    assert h.get("http-referer") == "https://my.app"
    assert h.get("x-title") == "ai-agent"


def test_openai_compat_without_extra_headers_still_authorizes():
    p = OpenAICompatProvider(base_url="https://example.com/v1", model="m1", api_key="k")
    h = dict(p._client.headers)
    assert h.get("authorization") == "Bearer k"
    # No leakage of unexpected headers
    assert "http-referer" not in h
    assert "x-title" not in h


@pytest.fixture
async def provider(monkeypatch):
    p = OllamaProvider(base_url="http://localhost:11434", model="ghost-model:7b")
    yield p
    await p.aclose()


async def test_chat_404_model_not_found_raises_friendly(provider, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'ghost-model:7b' not found, try pulling it first"})

    transport = httpx.MockTransport(handler)
    provider._client = httpx.AsyncClient(transport=transport, timeout=5)

    with pytest.raises(ModelNotInstalledError) as exc:
        await provider.chat([])
    assert "ghost-model:7b" in str(exc.value)
    assert "ollama pull" in str(exc.value)


async def test_chat_other_4xx_raises_generic(provider):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)

    with pytest.raises(httpx.HTTPStatusError) as exc:
        await provider.chat([])
    assert "400" in str(exc.value)


async def test_stream_404_also_friendly(provider):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'ghost-model:7b' not found"})

    provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5)

    async def cb(_):
        pass

    with pytest.raises(ModelNotInstalledError):
        await provider.chat([], on_content=cb)
