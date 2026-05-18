"""install_package refuses Ollama model tags."""
from __future__ import annotations

import pytest

from ai_agent.tools.base import ToolContext
from ai_agent.tools.package import InstallPackage, _looks_like_ollama_tag


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


@pytest.fixture
def ctx(tmp_path):
    return ToolContext(workspace=tmp_path, settings=None, logger=_DummyLogger())


def test_detects_ollama_tags():
    assert _looks_like_ollama_tag("llava:13b")
    assert _looks_like_ollama_tag("gemma4:latest")
    assert _looks_like_ollama_tag("qwen2.5-coder:7b")
    assert _looks_like_ollama_tag("deepseek-coder-v2:16b")


def test_does_not_flag_pip_pins():
    assert not _looks_like_ollama_tag("pydantic==2.7.0")
    assert not _looks_like_ollama_tag("requests")
    assert not _looks_like_ollama_tag("typer")


def test_does_not_flag_npm_scoped_packages():
    assert not _looks_like_ollama_tag("@types/node")
    assert not _looks_like_ollama_tag("@vercel/ai")


async def test_install_package_refuses_ollama_tag(ctx):
    r = await InstallPackage().run({"package": "llava:13b"}, ctx)
    assert not r.success
    assert "ollama" in (r.error or "").lower()
    assert "ollama pull" in (r.error or "")
