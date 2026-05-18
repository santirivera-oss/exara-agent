"""Loop guard breaks repeated identical tool calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.config import (
    AgentConfig, ApiConfig, LoggingConfig, MemoryConfig, ModelConfig,
    SafetyConfig, Settings,
)
from ai_agent.core.agent import Agent
from ai_agent.memory.store import MemoryStore
from ai_agent.models.base import ChatResponse, ModelProvider, ToolCall
from ai_agent.models.router import ModelRouter
from ai_agent.safety.validator import Validator
from ai_agent.tools.registry import build_default_registry


class _LoopProvider(ModelProvider):
    """Always returns the same tool call — simulates a stuck model."""
    name = "loop"

    def __init__(self):
        self.calls = 0
        self.finalised = False

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.calls += 1
        # If we see the corrective message, switch to a final answer.
        last = messages[-1] if messages else None
        if last and last.role == "tool" and "LOOP DETECTED" in (last.content or ""):
            self.finalised = True
            return ChatResponse(content="ok, I'll stop. I cannot continue.", tool_calls=[], finish_reason="stop")
        return ChatResponse(
            content="",
            tool_calls=[ToolCall(id=f"c{self.calls}", name="list_directory", arguments={"path": ".", "recursive": True})],
            finish_reason="tool_calls",
        )

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return []


@pytest.fixture
async def agent(tmp_path: Path):
    settings = Settings(
        workspace=tmp_path,
        agent=AgentConfig(max_steps=10, stream=False),
        model=ModelConfig(),
        safety=SafetyConfig(permission_level="full", require_confirmation=False),
        memory=MemoryConfig(db_path=str(tmp_path / "a.db")),
        api=ApiConfig(),
        logging=LoggingConfig(),
    )
    provider = _LoopProvider()
    router = ModelRouter(provider)
    store = MemoryStore(settings.memory.db_path)
    await store.init()
    a = Agent(settings, router, build_default_registry(), store, Validator(settings.safety))
    await a.init()
    return a, provider


async def test_loop_guard_injects_corrective_feedback(agent):
    a, provider = agent
    events = []
    async for evt in a.run("list the directory"):
        events.append(evt)

    # Must have at least one "loop guard" denied event
    denied = [e for e in events if e.type == "denied" and "loop guard" in e.content]
    assert denied, f"expected loop-guard denied event, got: {[(e.type, e.content[:60]) for e in events]}"
    # The model received the corrective feedback and produced a final response.
    finals = [e for e in events if e.type == "final"]
    assert finals
    assert provider.finalised
