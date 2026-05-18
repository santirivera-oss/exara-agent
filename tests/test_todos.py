"""todo_write / todo_read round-trip."""
from __future__ import annotations

import pytest

from ai_agent.memory.store import MemoryStore
from ai_agent.tools.base import ToolContext
from ai_agent.tools.todos import TodoRead, TodoWrite


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


@pytest.fixture
async def store_and_session(tmp_path):
    s = MemoryStore(tmp_path / "agent.db")
    await s.init()
    sid = await s.create_session("test", str(tmp_path))
    return s, sid


@pytest.fixture
def ctx_factory(tmp_path):
    def _make(memory, session_id):
        return ToolContext(
            workspace=tmp_path, settings=None, logger=_DummyLogger(),
            extra={"memory": memory, "session_id": session_id},
        )
    return _make


async def test_todo_write_then_read(store_and_session, ctx_factory):
    store, sid = store_and_session
    ctx = ctx_factory(store, sid)

    items = [
        {"content": "Plan migration", "status": "completed"},
        {"content": "Write tests", "status": "in_progress"},
        {"content": "Deploy", "status": "pending"},
    ]
    w = await TodoWrite().run({"items": items}, ctx)
    assert w.success
    assert "(x) Plan migration" in w.output
    assert "(~) Write tests" in w.output
    assert "( ) Deploy" in w.output

    r = await TodoRead().run({}, ctx)
    assert r.success
    assert "Plan migration" in r.output


async def test_todo_write_replaces_existing(store_and_session, ctx_factory):
    store, sid = store_and_session
    ctx = ctx_factory(store, sid)

    await TodoWrite().run({"items": [{"content": "old item"}]}, ctx)
    await TodoWrite().run({"items": [{"content": "new item one"}, {"content": "new item two"}]}, ctx)

    items = await store.get_todos(sid)
    assert len(items) == 2
    assert items[0]["content"] == "new item one"
    assert items[1]["content"] == "new item two"


async def test_todo_read_empty(store_and_session, ctx_factory):
    store, sid = store_and_session
    ctx = ctx_factory(store, sid)
    r = await TodoRead().run({}, ctx)
    assert r.success
    assert "no todos yet" in r.output


async def test_todo_write_requires_session(tmp_path):
    ctx = ToolContext(
        workspace=tmp_path, settings=None, logger=_DummyLogger(),
        extra={},  # no memory, no session
    )
    r = await TodoWrite().run({"items": [{"content": "x"}]}, ctx)
    assert not r.success
    assert "session" in (r.error or "").lower()
