"""Memory store round-trips."""
from __future__ import annotations

import pytest

from ai_agent.memory.store import MemoryStore
from ai_agent.models.base import ChatMessage, ToolCall


@pytest.fixture
async def store(tmp_path):
    s = MemoryStore(tmp_path / "agent.db")
    await s.init()
    return s


async def test_create_and_list_sessions(store):
    sid = await store.create_session("test", "/ws")
    sessions = await store.list_sessions("/ws")
    assert any(r["id"] == sid for r in sessions)


async def test_append_and_load_messages(store):
    sid = await store.create_session("t", "/ws")
    await store.append_message(sid, ChatMessage(role="user", content="hi"))
    await store.append_message(sid, ChatMessage(
        role="assistant", content="", tool_calls=[ToolCall(id="c1", name="read_file", arguments={"path": "a"})]
    ))
    await store.append_message(sid, ChatMessage(
        role="tool", tool_call_id="c1", name="read_file", content="ok"
    ))
    msgs = await store.load_messages(sid)
    assert len(msgs) == 3
    assert msgs[1].tool_calls[0].name == "read_file"
    assert msgs[2].tool_call_id == "c1"


async def test_project_facts(store):
    await store.set_fact("/ws", "stack", "next.js")
    await store.set_fact("/ws", "stack", "next.js + tailwind")  # upsert
    facts = await store.get_facts("/ws")
    assert facts["stack"] == "next.js + tailwind"
