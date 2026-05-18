"""Ollama provider — uses /api/chat with native tool calling."""
from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

import httpx

from .base import ChatMessage, ChatResponse, ContentCallback, ModelProvider, ToolCall


class ModelNotInstalledError(RuntimeError):
    """Raised when the configured Ollama model isn't pulled locally."""


class OllamaProvider(ModelProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, keep_alive: str = "10m", timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.keep_alive = keep_alive
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(self, messages: list[ChatMessage], tools: list[dict[str, Any]] | None, temperature: float, stream: bool, model_override: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model_override or self.model,
            "messages": [self._ollama_message(m) for m in messages],
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature},
        }
        if tools:
            payload["tools"] = tools
        return payload

    @staticmethod
    def _ollama_message(m: ChatMessage) -> dict[str, Any]:
        """Ollama's chat shape — close to OpenAI but with tool_calls.function.arguments
        as object, not string. Images go in an `images` array of base64 strings on
        user messages; audio goes in `audio` for models that advertise the capability.
        """
        if m.role == "tool":
            return {
                "role": "tool",
                "content": m.content,
                # Ollama tolerates these extra fields and uses them for stricter models
                "tool_call_id": m.tool_call_id or "",
                "name": m.name or "",
            }
        msg: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.images:
            msg["images"] = m.images
        if m.audio:
            msg["audio"] = m.audio
        if m.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in m.tool_calls
            ]
        return msg

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
        stream = on_content is not None
        payload = self._payload(messages, tools, temperature, stream=stream, model_override=model_override)
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        effective_model = model_override or self.model
        if not stream:
            resp = await self._client.post(f"{self.base_url}/api/chat", json=payload)
            self._raise_friendly(resp, effective_model)
            data = resp.json()
            return self._parse_response(data, data.get("message", {}))

        # Streaming path — accumulate content deltas and tool_calls from JSON lines.
        content_chunks: list[str] = []
        tool_calls: list[ToolCall] = []
        last_chunk: dict[str, Any] = {}
        async with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                self._raise_friendly_with_body(resp, body, effective_model)
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last_chunk = chunk
                msg = chunk.get("message") or {}
                piece = msg.get("content") or ""
                if piece:
                    content_chunks.append(piece)
                    await on_content(piece)
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function", {})
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"_raw": args}
                    tool_calls.append(ToolCall(
                        id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                        name=fn.get("name", ""),
                        arguments=args or {},
                    ))
                if chunk.get("done"):
                    break

        return ChatResponse(
            content="".join(content_chunks),
            tool_calls=tool_calls,
            finish_reason=last_chunk.get("done_reason"),
            raw=last_chunk,
        )

    def _raise_friendly(self, resp: httpx.Response, model_for_error: str | None = None) -> None:
        if resp.status_code < 400:
            return
        self._raise_friendly_with_body(resp, resp.content, model_for_error)

    def _raise_friendly_with_body(self, resp: httpx.Response, body: bytes, model_for_error: str | None = None) -> None:
        if resp.status_code < 400:
            return
        msg = ""
        try:
            msg = json.loads(body.decode("utf-8", errors="replace")).get("error", "")
        except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
            msg = body.decode("utf-8", errors="replace")[:300]

        # Ollama returns 404 with body like {"error": "model 'X' not found, try pulling it first"}
        if resp.status_code == 404 and "not found" in msg.lower():
            name = model_for_error or self.model
            raise ModelNotInstalledError(
                f"Ollama model '{name}' is not installed. "
                f"Pull it with:  ollama pull {name}"
            )
        raise httpx.HTTPStatusError(
            f"Ollama HTTP {resp.status_code}: {msg or '(no error message)'}",
            request=resp.request,
            response=resp,
        )

    def _parse_response(self, data: dict[str, Any], msg: dict[str, Any]) -> ChatResponse:
        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"_raw": args}
            tool_calls.append(ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=fn.get("name", ""),
                arguments=args or {},
            ))
        return ChatResponse(
            content=msg.get("content", "") or "",
            tool_calls=tool_calls,
            finish_reason=data.get("done_reason"),
            raw=data,
        )

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, tools=None, temperature=temperature, stream=True)
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        async with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                self._raise_friendly_with_body(resp, body, self.model)
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                piece = (chunk.get("message") or {}).get("content")
                if piece:
                    yield piece
                if chunk.get("done"):
                    break

    async def list_models(self) -> list[str]:
        try:
            r = await self._client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            return [m.get("name", "") for m in r.json().get("models", [])]
        except httpx.HTTPError:
            return []
