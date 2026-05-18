"""Audio tools — read_audio uses the active model's audio capability.

Pattern matches read_image: load file, base64, single-shot sub-call. Works with
models that advertise the `audio` capability (Gemma 4, Qwen2.5-Omni, GPT-4o
audio). On models without audio, the provider will refuse and we surface that.
"""
from __future__ import annotations

import base64

import anyio
from pydantic import BaseModel, Field

from ..models.base import ChatMessage
from ..utils.paths import resolve_in_workspace
from .base import Tool, ToolContext, ToolResult

_AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".m4a", ".flac"}
_MAX_AUDIO_BYTES = 20_000_000  # 20MB cap — audio embeddings get expensive past this


def _config_model(ctx: ToolContext, field: str) -> str | None:
    settings = ctx.settings
    if settings is None:
        return None
    mm = getattr(settings, "multimodal", None)
    return getattr(mm, field, None) if mm is not None else None


def _hybrid_provider_config(ctx: ToolContext, capability: str) -> dict | None:
    settings = ctx.settings
    if settings is None:
        return None
    mm = getattr(settings, "multimodal", None)
    if mm is None:
        return None
    kind = getattr(mm, f"{capability}_provider", None)
    base_url = getattr(mm, f"{capability}_base_url", None)
    model = getattr(mm, f"{capability}_model", None)
    if not kind or not base_url or not model:
        return None
    return {
        "kind": kind,
        "base_url": base_url,
        "model": model,
        "api_key": getattr(mm, f"{capability}_api_key", None),
    }


class ReadAudioArgs(BaseModel):
    path: str = Field(..., description="Path to audio file (wav/mp3/ogg/m4a/flac) in the workspace")
    prompt: str = Field(
        "Transcribe the speech in this audio. If there's no speech, describe the sound briefly.",
        description="What to ask the audio model. Defaults to transcription.",
    )
    model: str | None = Field(
        None,
        description=(
            "LEAVE EMPTY by default. The system already picks the correct audio "
            "model from configuration. Only set this if the user explicitly asked "
            "you to use a specific model by name. Never guess a model name."
        ),
    )


class ReadAudio(Tool):
    name = "read_audio"
    description = (
        "Listen to an audio file and return a transcription or description. The active "
        "model must support audio (Gemma 4, Qwen2.5-Omni, GPT-4o audio). Pass `prompt` "
        "to ask specific questions: 'transcribe verbatim', 'identify the speakers', "
        "'what music genre is this'."
    )
    Args = ReadAudioArgs
    read_only = True

    async def _run(self, args: ReadAudioArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"audio not found: {p}")
        if not p.is_file():
            return ToolResult(False, "", error=f"not a file: {p}")
        if p.suffix.lower() not in _AUDIO_EXTS:
            return ToolResult(
                False, "",
                error=f"unsupported audio format {p.suffix!r}; expected one of {sorted(_AUDIO_EXTS)}",
            )
        data = await anyio.Path(p).read_bytes()
        if len(data) > _MAX_AUDIO_BYTES:
            return ToolResult(
                False, "",
                error=f"audio too large ({len(data)} bytes); max {_MAX_AUDIO_BYTES}. Trim first.",
            )

        b64 = base64.b64encode(data).decode("ascii")
        prompt = args.prompt.strip() if args.prompt and args.prompt.strip() else ReadAudioArgs.model_fields["prompt"].default
        hybrid = _hybrid_provider_config(ctx, "audio")
        router = ctx.extra.get("router")
        if hybrid is None and router is None:
            return ToolResult(False, "", error="read_audio: no router in tool context and no hybrid provider configured")

        config_default = _config_model(ctx, "audio_model")
        model_override = args.model or config_default

        aux_provider = None
        try:
            if hybrid is not None:
                from ..models.factory import build_aux_provider
                aux_provider = build_aux_provider(
                    hybrid["kind"],
                    base_url=hybrid["base_url"],
                    model=hybrid["model"],
                    api_key=hybrid["api_key"],
                )
                resp = await aux_provider.chat(
                    messages=[ChatMessage(role="user", content=prompt, audio=[b64])],
                    tools=None,
                    temperature=0.2,
                )
            else:
                resp = await router.provider.chat(
                    messages=[ChatMessage(role="user", content=prompt, audio=[b64])],
                    tools=None,
                    temperature=0.2,
                    model_override=model_override,
                )
        except Exception as e:
            hint = ""
            if args.model and config_default and args.model != config_default:
                hint = (
                    f" Drop the `model` argument to fall back to '{config_default}' "
                    "from settings.multimodal.audio_model."
                )
            return ToolResult(False, "", error=f"audio call failed: {e}{hint}")
        finally:
            if aux_provider is not None:
                await aux_provider.aclose()

        text = (resp.content or "").strip()
        if not text:
            return ToolResult(
                False, "",
                error="audio model returned empty content — model may not support audio",
            )
        return ToolResult(
            True,
            text,
            data={"path": str(p), "bytes": len(data), "chars": len(text)},
        )
