"""Router — pick a provider based on config or runtime override."""
from __future__ import annotations

from ..config import ModelConfig
from .base import ModelProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider


class ModelRouter:
    """Holds the active provider; supports runtime swap."""

    def __init__(self, provider: ModelProvider):
        self.provider = provider

    async def aclose(self) -> None:
        await self.provider.aclose()

    def swap(self, provider: ModelProvider) -> None:
        self.provider = provider


def build_router(cfg: ModelConfig) -> ModelRouter:
    if cfg.provider == "ollama":
        return ModelRouter(OllamaProvider(
            base_url=cfg.ollama.base_url,
            model=cfg.ollama.model,
            keep_alive=cfg.ollama.keep_alive,
        ))
    if cfg.provider == "openai_compat":
        return ModelRouter(OpenAICompatProvider(
            base_url=cfg.openai_compat.base_url,
            model=cfg.openai_compat.model,
            api_key=cfg.openai_compat.api_key,
            extra_headers=cfg.openai_compat.extra_headers,
        ))
    raise ValueError(f"unknown provider: {cfg.provider}")
