"""SQLite-backed conversation + project memory.

Schema:
  sessions(id, name, created_at, workspace)
  messages(id, session_id, role, content, tool_calls_json, tool_call_id, name, created_at)
  project_facts(id, workspace, key, value, updated_at)   -- arbitrary k/v notes about a project
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import aiosqlite

from ..models.base import ChatMessage, ToolCall

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT,
    workspace TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    tool_calls_json TEXT,
    tool_call_id TEXT,
    name TEXT,
    created_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
CREATE TABLE IF NOT EXISTS project_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(workspace, key)
);
CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    updated_at REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_todos_session ON todos(session_id, position);
"""


class MemoryStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # ---- sessions -----------------------------------------------------------

    async def create_session(self, name: str | None, workspace: str) -> str:
        sid = uuid.uuid4().hex
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, name, workspace, created_at) VALUES (?,?,?,?)",
                (sid, name, workspace, time.time()),
            )
            await db.commit()
        return sid

    async def list_sessions(self, workspace: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if workspace:
                rows = await db.execute_fetchall(
                    "SELECT id, name, workspace, created_at FROM sessions WHERE workspace=? ORDER BY created_at DESC LIMIT ?",
                    (workspace, limit),
                )
            else:
                rows = await db.execute_fetchall(
                    "SELECT id, name, workspace, created_at FROM sessions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
            return [dict(r) for r in rows]

    # ---- messages -----------------------------------------------------------

    async def append_message(self, session_id: str, message: ChatMessage) -> None:
        tool_calls_json = (
            json.dumps([tc.model_dump() for tc in message.tool_calls])
            if message.tool_calls else None
        )
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO messages
                   (id, session_id, role, content, tool_calls_json, tool_call_id, name, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    uuid.uuid4().hex,
                    session_id,
                    message.role,
                    message.content,
                    tool_calls_json,
                    message.tool_call_id,
                    message.name,
                    time.time(),
                ),
            )
            await db.commit()

    async def load_messages(self, session_id: str, limit: int | None = None) -> list[ChatMessage]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            q = "SELECT role, content, tool_calls_json, tool_call_id, name FROM messages WHERE session_id=? ORDER BY created_at ASC"
            params: tuple = (session_id,)
            if limit:
                q += " LIMIT ?"
                params = (session_id, limit)
            rows = await db.execute_fetchall(q, params)
        out: list[ChatMessage] = []
        for r in rows:
            tcs: list[ToolCall] = []
            if r["tool_calls_json"]:
                for raw in json.loads(r["tool_calls_json"]):
                    tcs.append(ToolCall(**raw))
            out.append(ChatMessage(
                role=r["role"],
                content=r["content"] or "",
                tool_calls=tcs,
                tool_call_id=r["tool_call_id"],
                name=r["name"],
            ))
        return out

    # ---- project facts ------------------------------------------------------

    async def set_fact(self, workspace: str, key: str, value: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO project_facts (workspace, key, value, updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(workspace, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
                (workspace, key, value, time.time()),
            )
            await db.commit()

    async def get_facts(self, workspace: str) -> dict[str, str]:
        async with aiosqlite.connect(self.db_path) as db:
            rows = await db.execute_fetchall(
                "SELECT key, value FROM project_facts WHERE workspace=?", (workspace,),
            )
        return {k: v for (k, v) in rows}

    async def list_facts(self, workspace: str | None = None) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if workspace is None:
                rows = await db.execute_fetchall(
                    "SELECT workspace, key, value, updated_at FROM project_facts "
                    "ORDER BY updated_at DESC"
                )
            else:
                rows = await db.execute_fetchall(
                    "SELECT workspace, key, value, updated_at FROM project_facts "
                    "WHERE workspace=? ORDER BY key",
                    (workspace,),
                )
        return [dict(r) for r in rows]

    async def search_facts(
        self,
        query: str,
        workspace: str | None = None,
    ) -> list[dict[str, Any]]:
        needle = f"%{query.lower()}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if workspace is None:
                rows = await db.execute_fetchall(
                    "SELECT workspace, key, value, updated_at FROM project_facts "
                    "WHERE lower(workspace) LIKE ? OR lower(key) LIKE ? OR lower(value) LIKE ? "
                    "ORDER BY updated_at DESC",
                    (needle, needle, needle),
                )
            else:
                rows = await db.execute_fetchall(
                    "SELECT workspace, key, value, updated_at FROM project_facts "
                    "WHERE workspace=? AND (lower(key) LIKE ? OR lower(value) LIKE ?) "
                    "ORDER BY key",
                    (workspace, needle, needle),
                )
        return [dict(r) for r in rows]

    async def delete_fact(self, workspace: str, key: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM project_facts WHERE workspace=? AND key=?",
                (workspace, key),
            )
            await db.commit()
            return cursor.rowcount > 0

    # ---- todos --------------------------------------------------------------

    async def set_todos(self, session_id: str, items: list[dict[str, Any]]) -> None:
        """Replace the entire todo list for this session."""
        now = time.time()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM todos WHERE session_id=?", (session_id,))
            for i, item in enumerate(items):
                await db.execute(
                    "INSERT INTO todos (session_id, position, content, status, updated_at) "
                    "VALUES (?,?,?,?,?)",
                    (session_id, i, item["content"], item.get("status", "pending"), now),
                )
            await db.commit()

    async def get_todos(self, session_id: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT content, status, position FROM todos WHERE session_id=? ORDER BY position",
                (session_id,),
            )
        return [{"content": r["content"], "status": r["status"], "position": r["position"]}
                for r in rows]
