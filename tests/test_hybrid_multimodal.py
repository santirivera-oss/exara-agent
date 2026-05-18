"""Hybrid multimodal: vision/audio can target a different provider than the agent."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.config import MultimodalConfig
from ai_agent.models.base import ChatMessage, ChatResponse, ModelProvider
from ai_agent.models.factory import build_aux_provider
from ai_agent.models.router import ModelRouter
from ai_agent.tools.audio import ReadAudio
from ai_agent.tools.base import ToolContext
from ai_agent.tools.vision import ReadImage, _hybrid_provider_config


class _RouterProvider(ModelProvider):
    """Records what messages it saw. Used to verify it's NOT called when hybrid is on."""
    name = "router"

    def __init__(self):
        self.calls = 0

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.calls += 1
        return ChatResponse(content="router-said-this", tool_calls=[], finish_reason="stop")

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return []


class _HybridProvider(_RouterProvider):
    name = "hybrid"


class _SettingsStub:
    def __init__(self, **kwargs):
        self.multimodal = MultimodalConfig(**kwargs)


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


_PNG_1x1 = bytes.fromhex(
    "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
    "0000000D49444154789C6300010000000500010D0A2DB40000000049454E44AE426082"
)


def test_hybrid_provider_config_present(tmp_path):
    settings = _SettingsStub(
        vision_provider="ollama",
        vision_base_url="http://localhost:11434",
        vision_model="gemma4",
    )
    ctx = ToolContext(workspace=tmp_path, settings=settings, logger=_DummyLogger())
    cfg = _hybrid_provider_config(ctx, "vision")
    assert cfg is not None
    assert cfg["kind"] == "ollama"
    assert cfg["base_url"] == "http://localhost:11434"
    assert cfg["model"] == "gemma4"


def test_hybrid_provider_config_partial_returns_none(tmp_path):
    """If any required field is missing, hybrid is disabled (falls back to router)."""
    settings = _SettingsStub(vision_provider="ollama")  # no base_url, no model
    ctx = ToolContext(workspace=tmp_path, settings=settings, logger=_DummyLogger())
    assert _hybrid_provider_config(ctx, "vision") is None


def test_build_aux_provider_ollama():
    p = build_aux_provider("ollama", base_url="http://x:11434", model="gemma4")
    assert p.name == "ollama"
    assert p.model == "gemma4"


def test_build_aux_provider_openai_compat():
    p = build_aux_provider("openai_compat", base_url="https://api.example/v1",
                           model="gpt-4o-mini", api_key="sk-test")
    assert p.name == "openai_compat"
    assert p.model == "gpt-4o-mini"


def test_build_aux_provider_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown provider kind"):
        build_aux_provider("nope", base_url="x", model="y")


async def test_read_image_bypasses_router_when_hybrid_set(tmp_path, monkeypatch):
    """When hybrid is configured, read_image must NOT call the router's provider."""
    router_provider = _RouterProvider()
    hybrid_provider = _HybridProvider()

    # Patch the factory so it returns our hybrid stub instead of a real Ollama client.
    import ai_agent.models.factory as factory_mod
    def fake_build(kind, **_kw):
        return hybrid_provider
    monkeypatch.setattr(factory_mod, "build_aux_provider", fake_build)

    settings = _SettingsStub(
        vision_provider="ollama",
        vision_base_url="http://localhost:11434",
        vision_model="gemma4",
    )
    ctx = ToolContext(
        workspace=tmp_path,
        settings=settings,
        logger=_DummyLogger(),
        extra={"router": ModelRouter(router_provider)},
    )
    (tmp_path / "x.png").write_bytes(_PNG_1x1)

    r = await ReadImage().run({"path": "x.png"}, ctx)
    assert r.success, r.error
    assert hybrid_provider.calls == 1, "hybrid provider should have been called"
    assert router_provider.calls == 0, "router provider should NOT have been touched"


async def test_read_image_falls_back_to_router_without_hybrid(tmp_path):
    """When no hybrid config, read_image uses the router as before."""
    router_provider = _RouterProvider()
    settings = _SettingsStub(vision_model="some-model")  # only model set
    ctx = ToolContext(
        workspace=tmp_path,
        settings=settings,
        logger=_DummyLogger(),
        extra={"router": ModelRouter(router_provider)},
    )
    (tmp_path / "x.png").write_bytes(_PNG_1x1)

    r = await ReadImage().run({"path": "x.png"}, ctx)
    assert r.success
    assert router_provider.calls == 1
