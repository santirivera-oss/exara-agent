"""OpenAI-compatible provider — works with vLLM, LM Studio, llama.cpp server, etc."""
from __future__ import annotations

import asyncio
import json
import re
import uuid
from typing import Any, AsyncIterator

import httpx

from .base import ChatMessage, ChatResponse, ContentCallback, ModelProvider, ToolCall

# Retry policy for rate-limited responses. Free-tier endpoints (OpenRouter,
# Together's free models) hit these constantly; auto-retry hides the noise.
_MAX_RETRIES_429 = 3
_BACKOFF_BASE = 5.0  # seconds — first wait when Retry-After is absent
_BACKOFF_CAP = 60.0


async def _sleep_for_429(resp: httpx.Response, attempt: int) -> float:
    """Respect Retry-After if present (RFC 7231 §7.1.3), otherwise exponential
    backoff capped at _BACKOFF_CAP. Returns the seconds we slept."""
    header = resp.headers.get("retry-after")
    delay: float | None = None
    if header:
        try:
            delay = float(header)
        except ValueError:
            # HTTP-date form — ignore, we'll fall back to exponential.
            delay = None
    if delay is None:
        delay = min(_BACKOFF_BASE * (2 ** attempt), _BACKOFF_CAP)
    await asyncio.sleep(delay)
    return delay


class ProviderAuthError(RuntimeError):
    """Bad API key."""


class ProviderQuotaError(RuntimeError):
    """Out of credits / payment required."""


class ProviderRateLimitError(RuntimeError):
    """Too many requests."""


def _raise_openai_friendly(resp: httpx.Response, body: bytes | None = None) -> None:
    """Translate common HTTP failures into messages the user can act on."""
    if resp.status_code < 400:
        return
    if body is None:
        body = resp.content
    msg = ""
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace"))
        msg = (parsed.get("error") or {}).get("message", "") if isinstance(parsed.get("error"), dict) \
            else str(parsed.get("error", ""))
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        msg = body.decode("utf-8", errors="replace")[:300]

    if resp.status_code == 401:
        raise ProviderAuthError(
            f"API key rejected (HTTP 401). Check AI_AGENT_OPENAI_API_KEY in .env. {msg}"
        )
    if resp.status_code == 402:
        raise ProviderQuotaError(
            "HTTP 402 — out of credits. "
            "Either add credit at https://openrouter.ai/credits, or switch to a free model "
            "(those ending in ':free', e.g. /model deepseek/deepseek-v4-flash:free). "
            f"Provider said: {msg}"
        )
    if resp.status_code == 429:
        raise ProviderRateLimitError(
            f"HTTP 429 — rate limited. Wait a moment or switch model. {msg}"
        )
    raise httpx.HTTPStatusError(
        f"HTTP {resp.status_code}: {msg or '(no error message)'}",
        request=resp.request,
        response=resp,
    )


class OpenAICompatProvider(ModelProvider):
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout: float = 600.0,
        extra_headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None, temperature: float, stream: bool, max_tokens: int | None, model_override: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_override or self.model,
            "messages": [m.to_provider_dict() for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return payload

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        on_content: ContentCallback | None = None,
        model_override: str | None = None,
    ) -> ChatResponse:
        if on_content is None:
            payload = self._payload(messages, tools, temperature, stream=False, max_tokens=max_tokens, model_override=model_override)
            for attempt in range(_MAX_RETRIES_429 + 1):
                resp = await self._client.post(f"{self.base_url}/chat/completions", json=payload)
                if resp.status_code == 429 and attempt < _MAX_RETRIES_429:
                    await _sleep_for_429(resp, attempt)
                    continue
                _raise_openai_friendly(resp)
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                return self._build_response(choice.get("message", {}), choice.get("finish_reason"), data)

        # Streaming path: SSE with delta.content and incremental delta.tool_calls
        payload = self._payload(messages, tools, temperature, stream=True, max_tokens=max_tokens, model_override=model_override)
        content_chunks: list[str] = []
        # index → {id, name, arguments_buf}
        tc_acc: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        raw_last: dict[str, Any] = {}

        # Open the stream with 429 retry — exits inner block and retries on rate-limit.
        url = f"{self.base_url}/chat/completions"
        for attempt in range(_MAX_RETRIES_429 + 1):
            cm = self._client.stream("POST", url, json=payload)
            resp = await cm.__aenter__()
            if resp.status_code == 429 and attempt < _MAX_RETRIES_429:
                await cm.__aexit__(None, None, None)
                await _sleep_for_429(resp, attempt)
                continue
            break
        # `cm` and `resp` are bound from the loop above; on any non-429 outcome
        # we proceed to iterate the body.
        try:
            if resp.status_code >= 400:
                body = await resp.aread()
                _raise_openai_friendly(resp, body)
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload_str = line.removeprefix("data:").strip()
                if payload_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                raw_last = chunk
                choice = (chunk.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                if (piece := delta.get("content")):
                    content_chunks.append(piece)
                    await on_content(piece)
                for tc in delta.get("tool_calls") or []:
                    idx = tc.get("index", 0)
                    slot = tc_acc.setdefault(idx, {"id": None, "name": "", "args": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["args"] += fn["arguments"]
                if choice.get("finish_reason"):
                    finish_reason = choice["finish_reason"]
        finally:
            await cm.__aexit__(None, None, None)

        tool_calls: list[ToolCall] = []
        for idx in sorted(tc_acc):
            slot = tc_acc[idx]
            try:
                args = json.loads(slot["args"]) if slot["args"] else {}
            except json.JSONDecodeError:
                args = {"_raw": slot["args"]}
            tool_calls.append(ToolCall(
                id=slot["id"] or f"call_{uuid.uuid4().hex[:12]}",
                name=slot["name"],
                arguments=args,
            ))

        return ChatResponse(
            content="".join(content_chunks),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            raw=raw_last,
        )

    def _build_response(self, msg: dict[str, Any], finish: str | None, raw: dict[str, Any]) -> ChatResponse:
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            args_raw = fn.get("arguments", "")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
            except json.JSONDecodeError:
                args = {"_raw": args_raw}
            tool_calls.append(ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=fn.get("name", ""),
                arguments=args,
            ))
        return ChatResponse(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            finish_reason=finish,
            raw=raw,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, tools=None, temperature=temperature, stream=True, max_tokens=max_tokens)
        async with self._client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                _raise_openai_friendly(resp, body)
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload_str = line.removeprefix("data:").strip()
                if payload_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                piece = delta.get("content")
                if piece:
                    yield piece

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get(f"{self.base_url}/models")
            r.raise_for_status()
            data = r.json()
            return [m.get("id", "") for m in data.get("data", [])]
        except httpx.HTTPError:
            return []
