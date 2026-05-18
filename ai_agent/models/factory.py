"""Factory for building ModelProvider instances on demand.

Used by hybrid-multimodal tools (read_image / read_audio) so they can target a
provider distinct from the agent's main router — typically local Ollama for
vision while the agent itself runs on a remote OpenAI-compat endpoint.
"""
from __future__ import annotations

from .base import ModelProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider


def build_aux_provider(
    kind: str,
    *,
    base_url: str,
    model: str,
    api_key: str | None = None,
) -> ModelProvider:
    """Construct a one-off provider for a sub-call.

    Caller is responsible for closing it via `await provider.aclose()`.
    """
    if kind == "ollama":
        return OllamaProvider(base_url=base_url, model=model)
    if kind == "openai_compat":
        return OpenAICompatProvider(
            base_url=base_url,
            model=model,
            api_key=api_key or "not-needed",
        )
    raise ValueError(f"unknown provider kind: {kind!r} (expected 'ollama' or 'openai_compat')")
