"""Web confirmation flow: agent emits confirm_request, awaits a future,
external caller resolves it."""
from __future__ import annotations

import asyncio
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


class _WriteThenStop(ModelProvider):
    """Turn 1: ask for run_python (a HIGH_RISK_TOOL that triggers CONFIRM in normal mode).
    Turn 2: finalise."""
    name = "ws"

    def __init__(self):
        self.turn = 0

    async def chat(self, messages, *, tools=None, temperature=0.2, max_tokens=None, on_content=None, model_override=None):
        self.turn += 1
        if self.turn == 1:
            return ChatResponse(
                content="",
                tool_calls=[ToolCall(id="c1", name="run_python",
                                     arguments={"code": "open('out.txt','w').write('data')"})],
                finish_reason="tool_calls",
            )
        return ChatResponse(content="done", tool_calls=[], finish_reason="stop")

    async def stream_chat(self, *_a, **_k):
        if False:
            yield ""

    async def list_models(self):
        return []


@pytest.fixture
async def agent_normal_mode(tmp_path: Path):
    settings = Settings(
        workspace=tmp_path,
        agent=AgentConfig(max_steps=5, stream=False),
        model=ModelConfig(),
        # normal mode → write_file triggers CONFIRM
        safety=SafetyConfig(permission_level="normal", require_confirmation=True),
        memory=MemoryConfig(db_path=str(tmp_path / "a.db")),
        multimodal=MultimodalConfig(),
        api=ApiConfig(),
        logging=LoggingConfig(),
    )
    router = ModelRouter(_WriteThenStop())
    store = MemoryStore(settings.memory.db_path)
    await store.init()
    a = Agent(settings, router, build_default_registry(), store, Validator(settings.safety))
    await a.init()
    return a, tmp_path


async def test_confirm_request_emitted_and_resolved_allow(agent_normal_mode):
    a, tmp_path = agent_normal_mode

    # Drive the agent.run() generator concurrently with a "user" resolving the confirm.
    async def resolver():
        # Wait until the agent has registered a pending confirmation
        for _ in range(50):
            if a.pending_confirms:
                cid = next(iter(a.pending_confirms))
                a.pending_confirms[cid].set_result(True)
                return
            await asyncio.sleep(0.05)
        raise AssertionError("confirm never appeared")

    events = []
    async def run_agent():
        async for evt in a.run("go"):
            events.append(evt)

    await asyncio.gather(run_agent(), resolver())

    types = [e.type for e in events]
    assert "confirm_request" in types
    # The write succeeded
    assert (tmp_path / "out.txt").exists()


async def test_confirm_request_resolved_deny_blocks_tool(agent_normal_mode):
    a, tmp_path = agent_normal_mode

    async def resolver():
        for _ in range(50):
            if a.pending_confirms:
                cid = next(iter(a.pending_confirms))
                a.pending_confirms[cid].set_result(False)
                return
            await asyncio.sleep(0.05)
        raise AssertionError("confirm never appeared")

    events = []
    async def run_agent():
        async for evt in a.run("go"):
            events.append(evt)

    await asyncio.gather(run_agent(), resolver())

    types = [e.type for e in events]
    assert "confirm_request" in types
    assert "denied" in types
    # The write must NOT have happened
    assert not (tmp_path / "out.txt").exists()
