"""Provider-neutral chat types and abstract ModelProvider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

ContentCallback = Callable[[str], Awaitable[None]]

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None  # for role=tool: id of the call this is responding to
    name: str | None = None  # tool name for role=tool
    # Multimodal attachments (base64-encoded payloads). Only meaningful on user
    # messages, and only with providers/models that advertise vision/audio.
    images: list[str] = Field(default_factory=list)
    audio: list[str] = Field(default_factory=list)

    def to_provider_dict(self) -> dict[str, Any]:
        """Default OpenAI-compatible serialisation. Providers may override.

        Images are emitted using OpenAI's image_url / data URL convention so this
        also works against vLLM, LM Studio and llama.cpp's server. Audio is sent
        the same way but with the OpenAI 'input_audio' content part (supported by
        recent OpenAI-compat servers).
        """
        m: dict[str, Any] = {"role": self.role}
        if self.images or self.audio:
            parts: list[dict[str, Any]] = []
            if self.content:
                parts.append({"type": "text", "text": self.content})
            for b64 in self.images:
                parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })
            for b64 in self.audio:
                parts.append({
                    "type": "input_audio",
                    "input_audio": {"data": b64, "format": "wav"},
                })
            m["content"] = parts
        elif self.content:
            m["content"] = self.content
        if self.tool_calls:
            m["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": _json_args(tc.arguments)},
                }
                for tc in self.tool_calls
            ]
        if self.role == "tool":
            m["tool_call_id"] = self.tool_call_id or ""
            if self.name:
                m["name"] = self.name
        return m


def _json_args(args: dict[str, Any]) -> str:
    import json
    return json.dumps(args, ensure_ascii=False)


class ChatResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    raw: dict[str, Any] | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class ModelProvider(ABC):
    """Base class for chat providers with tool calling support."""

    name: str

    @abstractmethod
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
        """If on_content is provided, stream content tokens through the callback
        while still returning the fully-assembled ChatResponse at the end.
        Tool calls are accumulated and returned with the final response.

        model_override lets a single call target a different model than the
        provider's default (e.g. a vision model for one read_image sub-call).
        """
        ...

    @abstractmethod
    def stream_chat(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream a plain assistant response (no tool calling).

        Tool calling and streaming together is provider-dependent and we keep the
        agent loop simpler by only streaming final answers, not intermediate steps.
        """
        ...

    @abstractmethod
    async def list_models(self) -> list[str]: ...

    async def aclose(self) -> None:  # optional override
        return None
