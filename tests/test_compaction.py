"""Auto-context-compaction with a fake provider."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.config import (
    AgentConfig, ApiConfig, LoggingConfig, MemoryConfig, ModelConfig,
    SafetyConfig, Settings,
)
from ai_agent.core.agent import Agent
from ai_agent.memory.store import MemoryStore
from ai_agent.models.base import ChatMessage, ChatResponse, ModelProvider
from ai_agent.models.router import ModelRouter
from ai_agent.safety.validator import Validator
from ai_agent.tools.registry import build_default_registry


class _FakeProvider(ModelProvider):
    name = "fake"

    def __init__(self, summary: str = "compacted summary text"):
        self.summary = summary
        self.calls = 0

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.calls += 1
        return ChatResponse(content=self.summary, tool_calls=[], finish_reason="stop")

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return ["fake-1"]


@pytest.fixture
async def agent(tmp_path: Path):
    settings = Settings(
        workspace=tmp_path,
        agent=AgentConfig(max_steps=5, stream=False),
        model=ModelConfig(),
        safety=SafetyConfig(permission_level="full", require_confirmation=False),
        memory=MemoryConfig(
            db_path=str(tmp_path / "agent.db"),
            summarise_after_messages=10,
            keep_recent=3,
        ),
        api=ApiConfig(),
        logging=LoggingConfig(),
    )
    router = ModelRouter(_FakeProvider())
    store = MemoryStore(settings.memory.db_path)
    await store.init()
    a = Agent(settings, router, build_default_registry(), store, Validator(settings.safety))
    await a.init()
    return a


async def test_no_compact_below_threshold(agent):
    # 1 system msg + 5 fake user msgs = 6 < threshold(10)
    for i in range(5):
        agent._messages.append(ChatMessage(role="user", content=f"msg {i}"))
    collapsed = await agent.maybe_compact()
    assert collapsed == 0


async def test_compact_above_threshold_collapses_middle(agent):
    # Build: [system] + 15 turns. threshold=10, keep_recent=3
    # Expected: head(1 system) + 1 summary + last 3 = 5 messages
    for i in range(15):
        agent._messages.append(ChatMessage(role="user", content=f"long message number {i}"))
    n_before = len(agent._messages)
    collapsed = await agent.maybe_compact()
    assert collapsed > 0
    assert len(agent._messages) < n_before
    # Structure check
    assert agent._messages[0].role == "system"  # original system stays
    assert "Compacted earlier history" in agent._messages[1].content
    # last 3 user msgs preserved verbatim
    assert agent._messages[-1].content == "long message number 14"
    assert agent._messages[-3].content == "long message number 12"


async def test_compact_is_idempotent_when_nothing_to_do(agent):
    # Even with many recent msgs, if everything is in keep_recent window we don't collapse.
    for i in range(3):
        agent._messages.append(ChatMessage(role="user", content=f"x{i}"))
    # threshold=10, currently 1+3=4, no compaction
    assert await agent.maybe_compact() == 0
