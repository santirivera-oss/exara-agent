"""Placeholder detection in tool call arguments."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.config import (
    AgentConfig, ApiConfig, LoggingConfig, MemoryConfig, ModelConfig,
    MultimodalConfig, SafetyConfig, Settings,
)
from ai_agent.core.agent import Agent, _placeholder_in_args
from ai_agent.memory.store import MemoryStore
from ai_agent.models.base import ChatResponse, ModelProvider, ToolCall
from ai_agent.models.router import ModelRouter
from ai_agent.safety.validator import Validator
from ai_agent.tools.registry import build_default_registry


def test_detects_angle_brackets():
    assert _placeholder_in_args({"id": "<process_id>"}) == "<process_id>"
    assert _placeholder_in_args({"x": "<YOUR_ID>"}) == "<YOUR_ID>"
    assert _placeholder_in_args({"x": "<id_here>"}) == "<id_here>"


def test_detects_double_braces():
    assert _placeholder_in_args({"k": "{{value}}"}) == "{{value}}"


def test_ignores_real_ids():
    assert _placeholder_in_args({"id": "c2bf4fe0"}) is None
    assert _placeholder_in_args({"id": "12345"}) is None
    assert _placeholder_in_args({"x": "some text containing < and > but not a placeholder"}) is None


def test_ignores_xml_like_content():
    # Real content that happens to contain angle brackets isn't a placeholder.
    assert _placeholder_in_args({"x": "<html><body>real</body></html>"}) is None


def test_detects_in_nested_dict():
    assert _placeholder_in_args({"opts": {"id": "<process_id>"}}) == "<process_id>"


def test_detects_keyword_placeholders():
    assert _placeholder_in_args({"id": "placeholder"}) == "placeholder"
    assert _placeholder_in_args({"id": "your_id"}) == "your_id"


class _DependentCallsProvider(ModelProvider):
    """First turn returns two parallel calls — second has a placeholder.
    Second turn returns the final answer (after seeing corrective feedback).
    """
    name = "deps"

    def __init__(self):
        self.turn = 0

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.turn += 1
        if self.turn == 1:
            return ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(id="c1", name="list_directory", arguments={"path": "."}),
                    # second call uses a placeholder for a value the first will produce
                    ToolCall(id="c2", name="read_file", arguments={"path": "<filename_from_listing>"}),
                ],
                finish_reason="tool_calls",
            )
        # After seeing PLACEHOLDER DETECTED, the model finalises.
        return ChatResponse(content="I see — I'll call them one at a time next time.", tool_calls=[], finish_reason="stop")

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return []


@pytest.fixture
async def agent(tmp_path: Path):
    settings = Settings(
        workspace=tmp_path,
        agent=AgentConfig(max_steps=5, stream=False),
        model=ModelConfig(),
        safety=SafetyConfig(permission_level="full", require_confirmation=False),
        memory=MemoryConfig(db_path=str(tmp_path / "a.db")),
        multimodal=MultimodalConfig(),
        api=ApiConfig(),
        logging=LoggingConfig(),
    )
    provider = _DependentCallsProvider()
    router = ModelRouter(provider)
    store = MemoryStore(settings.memory.db_path)
    await store.init()
    a = Agent(settings, router, build_default_registry(), store, Validator(settings.safety))
    await a.init()
    return a, provider


async def test_placeholder_injects_corrective_feedback(agent):
    a, provider = agent
    events = []
    async for evt in a.run("explore the workspace and read the first file"):
        events.append(evt)

    denied = [e for e in events if e.type == "denied" and "placeholder" in (e.content or "").lower()]
    assert denied, f"expected placeholder rejection, got: {[(e.type, e.content[:60]) for e in events]}"
    finals = [e for e in events if e.type == "final"]
    assert finals
