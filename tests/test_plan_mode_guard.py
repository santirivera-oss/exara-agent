"""Plan mode must hard-block write tools, even if the model hallucinates them.

Regression for a real bug: stripping WRITE_TOOLS from the spec sent to the
model is not enough — DeepSeek (and others) will sometimes emit the tool
anyway. The guard in _execute_tool_call is the real enforcement.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ai_agent.config import (
    AgentConfig, ApiConfig, LoggingConfig, MemoryConfig, ModelConfig,
    MultimodalConfig, SafetyConfig, Settings,
)
from ai_agent.core.agent import Agent
from ai_agent.memory.store import MemoryStore
from ai_agent.models.base import ChatResponse, ModelProvider, ToolCall
from ai_agent.models.router import ModelRouter
from ai_agent.safety.validator import Validator
from ai_agent.tools.registry import build_default_registry


class _RebelliousProvider(ModelProvider):
    """Always tries to write_file regardless of plan mode."""
    name = "rebel"

    def __init__(self):
        self.turn = 0

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.turn += 1
        if self.turn == 1:
            # Model ignores plan mode instructions and tries to write
            return ChatResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="write_file",
                                     arguments={"path": "evil.txt", "content": "hacked"})],
                finish_reason="tool_calls",
            )
        # Second turn: after seeing BLOCKED, finalises
        return ChatResponse(
            content="I see, I cannot write in plan mode. Here is my plan: 1. read file 2. propose changes",
            tool_calls=[],
            finish_reason="stop",
        )

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return []


@pytest.fixture
async def agent_in_plan_mode(tmp_path: Path):
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
    router = ModelRouter(_RebelliousProvider())
    store = MemoryStore(settings.memory.db_path)
    await store.init()
    a = Agent(settings, router, build_default_registry(), store, Validator(settings.safety))
    await a.init()
    a.set_plan_mode(True)
    return a, tmp_path


async def test_plan_mode_blocks_write_file_even_if_model_emits_it(agent_in_plan_mode):
    a, tmp_path = agent_in_plan_mode
    target = tmp_path / "evil.txt"
    assert not target.exists()

    events = []
    async for evt in a.run("do something"):
        events.append(evt)

    # File MUST NOT have been written
    assert not target.exists(), "plan mode failed to block write_file"

    # We expect a "denied" event referencing plan mode
    denied = [e for e in events if e.type == "denied" and "plan mode" in e.content.lower()]
    assert denied, f"expected plan-mode denial, got events: {[(e.type, e.content[:60]) for e in events]}"


async def test_plan_mode_allows_read_only_tools(agent_in_plan_mode):
    """Sanity: read tools should still work in plan mode."""
    a, tmp_path = agent_in_plan_mode
    # Verify list_directory wouldn't be blocked
    from ai_agent.tools.registry import WRITE_TOOLS
    assert "list_directory" not in WRITE_TOOLS
    assert "read_file" not in WRITE_TOOLS
    assert "search_project" not in WRITE_TOOLS
