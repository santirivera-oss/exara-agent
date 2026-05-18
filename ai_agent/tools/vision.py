"""Vision tools — read_image leverages the active model's vision capability.

The tool delegates to the same provider/model the agent is using. It makes a
self-contained sub-call (no agent state, no tools), so the returned text is a
clean description we can show the parent agent without polluting its history.

Works with any provider/model that supports image input — e.g. Gemma 3/4 on
Ollama, Llama 3.2 Vision, Qwen2.5-VL, GPT-4o-class models via OpenAI-compat,
etc. If the model has no vision capability, the provider will usually return
an error which we surface as a clear ToolResult.error.
"""
from __future__ import annotations

import base64

import anyio
from pydantic import BaseModel, Field

from ..models.base import ChatMessage
from ..utils.paths import resolve_in_workspace
from .base import Tool, ToolContext, ToolResult

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
_MAX_IMAGE_BYTES = 8_000_000  # 8MB — anything larger we refuse, model probably can't handle it


def _config_model(ctx: ToolContext, field: str) -> str | None:
    """Look up settings.multimodal.<field> defensively (settings may be None in tests)."""
    settings = ctx.settings
    if settings is None:
        return None
    mm = getattr(settings, "multimodal", None)
    return getattr(mm, field, None) if mm is not None else None


def _hybrid_provider_config(ctx: ToolContext, capability: str) -> dict | None:
    """Return {kind, base_url, model, api_key} if hybrid provider is configured
    for this capability (vision/audio), or None to reuse the router's provider.
    """
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


class ReadImageArgs(BaseModel):
    path: str = Field(..., description="Path to image file (jpg/png/gif/webp/bmp) in the workspace")
    prompt: str = Field(
        "Describe this image in detail. Focus on text, UI elements, "
        "code, diagrams, or anything actionable for a software engineer.",
        description="Question to ask the vision model about the image. Make it specific.",
    )
    model: str | None = Field(
        None,
        description=(
            "LEAVE EMPTY by default. The system already picks the correct vision "
            "model from configuration. Only set this if the user explicitly asked "
            "you to use a specific model by name. Never guess a model name."
        ),
    )


class ReadImage(Tool):
    name = "read_image"
    description = (
        "Look at an image (screenshot, photo, diagram, chart) and return a textual "
        "description. The active model must support vision (Gemma 3/4, Llama 3.2 Vision, "
        "Qwen-VL, GPT-4o-class, etc). Pass a focused `prompt` to extract specifics: "
        "'transcribe all text', 'describe the UI layout', 'what error is shown'."
    )
    Args = ReadImageArgs
    read_only = True

    async def _run(self, args: ReadImageArgs, ctx: ToolContext) -> ToolResult:
        p = resolve_in_workspace(args.path, ctx.workspace)
        if not p.exists():
            return ToolResult(False, "", error=f"image not found: {p}")
        if not p.is_file():
            return ToolResult(False, "", error=f"not a file: {p}")
        if p.suffix.lower() not in _IMAGE_EXTS:
            return ToolResult(
                False, "",
                error=f"unsupported image format {p.suffix!r}; expected one of {sorted(_IMAGE_EXTS)}",
            )
        data = await anyio.Path(p).read_bytes()
        if len(data) > _MAX_IMAGE_BYTES:
            return ToolResult(
                False, "",
                error=f"image too large ({len(data)} bytes); max {_MAX_IMAGE_BYTES}. Resize first.",
            )

        b64 = base64.b64encode(data).decode("ascii")
        prompt = args.prompt.strip() if args.prompt and args.prompt.strip() else ReadImageArgs.model_fields["prompt"].default
        hybrid = _hybrid_provider_config(ctx, "vision")
        router = ctx.extra.get("router")
        if hybrid is None and router is None:
            return ToolResult(False, "", error="read_image: no router in tool context and no hybrid provider configured")

        # Resolve which model to use: explicit arg > settings.multimodal.vision_model > active model.
        config_default = _config_model(ctx, "vision_model")
        model_override = args.model or config_default

        # Single-shot vision call. No tools, no history — we want a description, not a loop.
        # When hybrid provider is configured, build an ad-hoc client that talks
        # to that endpoint (e.g. local Ollama) instead of the agent's router.
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
                    messages=[ChatMessage(role="user", content=prompt, images=[b64])],
                    tools=None,
                    temperature=0.2,
                    # No override needed — the aux provider is already configured for this model.
                )
            else:
                resp = await router.provider.chat(
                    messages=[ChatMessage(role="user", content=prompt, images=[b64])],
                    tools=None,
                    temperature=0.2,
                    model_override=model_override,
                )
        except Exception as e:
            hint = ""
            if args.model and config_default and args.model != config_default:
                hint = (
                    f" Drop the `model` argument to fall back to '{config_default}' "
                    "from settings.multimodal.vision_model."
                )
            return ToolResult(False, "", error=f"vision call failed: {e}{hint}")
        finally:
            if aux_provider is not None:
                await aux_provider.aclose()

        text = (resp.content or "").strip()
        if not text:
            return ToolResult(
                False, "",
                error="vision model returned empty content — model may not support images",
            )
        return ToolResult(
            True,
            text,
            data={"path": str(p), "bytes": len(data), "chars": len(text)},
        )
