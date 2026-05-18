"""FastAPI server — minimal surface for a future frontend.

Endpoints:
  GET  /health
  GET  /tools
  GET  /models
  GET  /sessions
  POST /sessions
  POST /chat            -- one user message, agent runs to completion, returns events
  POST /chat/stream     -- same but streams events as Server-Sent Events
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import load_settings
from ..core.agent import Agent
from ..memory.store import MemoryStore
from ..models.router import build_router
from ..safety.validator import Validator
from ..tools.registry import build_default_registry
from ..utils.logging import configure_logging

# Per-session Agent cache. Without it, plan_mode and background processes
# would reset between requests because each /chat call would build a fresh Agent.
_AGENTS: dict[str, Agent] = {}

_STATE: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = load_settings()
    configure_logging(settings.logging.level, settings.logging.dir, settings.logging.json_output)
    router = build_router(settings.model)
    memory = MemoryStore(settings.memory.db_path)
    await memory.init()
    tools = build_default_registry()
    validator = Validator(settings.safety)
    _STATE.update({
        "settings": settings, "router": router, "memory": memory,
        "tools": tools, "validator": validator,
    })
    try:
        yield
    finally:
        await router.aclose()


app = FastAPI(title="exara-agent", version="0.1.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    auto_confirm: bool = True


class CreateSessionRequest(BaseModel):
    name: str | None = None


class ConfirmRequest(BaseModel):
    allow: bool


@app.get("/health")
async def health() -> dict[str, Any]:
    settings = _STATE["settings"]
    return {
        "status": "ok",
        "provider": settings.model.provider,
        "workspace": str(settings.workspace),
    }


@app.get("/tools")
async def list_tools() -> list[dict[str, str]]:
    return [{"name": t.name, "description": t.description} for t in _STATE["tools"].all()]


@app.get("/models")
async def list_models() -> dict[str, list[str]]:
    return {"models": await _STATE["router"].provider.list_models()}


@app.get("/sessions")
async def list_sessions(workspace: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return await _STATE["memory"].list_sessions(workspace, limit)


@app.post("/sessions")
async def create_session(req: CreateSessionRequest) -> dict[str, str]:
    ws = str(_STATE["settings"].workspace.resolve())
    sid = await _STATE["memory"].create_session(req.name, ws)
    return {"session_id": sid}


async def _build_agent(session_id: str | None, auto_confirm: bool) -> Agent:
    """Return a cached Agent for this session, or build one and cache it.

    Always (re)applies the per-request `auto_confirm` to the shared SafetyConfig,
    so that toggling it in the frontend takes effect even on cached agents.
    The Validator holds a reference to the same SafetyConfig, so mutating it
    here is visible everywhere.
    """
    settings = _STATE["settings"]
    settings.safety.require_confirmation = not auto_confirm

    if session_id and session_id in _AGENTS:
        return _AGENTS[session_id]
    agent = Agent(
        settings, _STATE["router"], _STATE["tools"], _STATE["memory"], _STATE["validator"],
        session_id=session_id,
    )
    await agent.init()
    _AGENTS[agent.session_id] = agent  # type: ignore[index]
    return agent


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    try:
        agent = await _build_agent(req.session_id, req.auto_confirm)
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    events: list[dict[str, Any]] = []
    async for evt in agent.run(req.message):
        events.append(asdict(evt))
    return {"session_id": agent.session_id, "events": events}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    agent = await _build_agent(req.session_id, req.auto_confirm)

    async def gen():
        yield f"data: {json.dumps({'type': 'session', 'session_id': agent.session_id})}\n\n"
        async for evt in agent.run(req.message):
            yield f"data: {json.dumps(asdict(evt))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# --- session-scoped controls (mirror of CLI slash commands) ----------------

async def _get_or_load_agent(session_id: str) -> Agent:
    """Return cached Agent, or lazily build one from DB if the session exists.

    Solves the case where a session was persisted to SQLite but the in-memory
    cache was lost (server restart). Raises 404 if the session is unknown.
    """
    if session_id in _AGENTS:
        return _AGENTS[session_id]

    memory: MemoryStore = _STATE["memory"]
    known = await memory.list_sessions(limit=10_000)
    if not any(s["id"] == session_id for s in known):
        raise HTTPException(404, f"session {session_id!r} not found")

    settings = _STATE["settings"]
    agent = Agent(
        settings, _STATE["router"], _STATE["tools"], memory, _STATE["validator"],
        session_id=session_id,
    )
    await agent.init()
    _AGENTS[session_id] = agent
    return agent


@app.post("/sessions/{session_id}/plan")
async def toggle_plan(session_id: str) -> dict[str, Any]:
    agent = await _get_or_load_agent(session_id)
    agent.set_plan_mode(not agent.plan_mode)
    return {"plan_mode": agent.plan_mode}


@app.post("/sessions/{session_id}/compact")
async def compact_session(session_id: str) -> dict[str, Any]:
    agent = await _get_or_load_agent(session_id)
    collapsed = await agent.maybe_compact()
    return {"collapsed": collapsed, "messages": len(agent.messages)}


@app.post("/sessions/{session_id}/confirm/{confirmation_id}")
async def resolve_confirm(session_id: str, confirmation_id: str, req: ConfirmRequest) -> dict[str, Any]:
    """Resolve a pending tool confirmation. The future was created by the agent
    when it emitted a `confirm_request` event; this endpoint fulfils it so the
    agent loop can continue."""
    agent = await _get_or_load_agent(session_id)
    fut = agent.pending_confirms.get(confirmation_id)
    if fut is None:
        raise HTTPException(404, f"unknown confirmation id {confirmation_id!r}")
    if fut.done():
        raise HTTPException(409, "this confirmation was already resolved")
    fut.set_result(req.allow)
    return {"ok": True, "allow": req.allow}


@app.get("/sessions/{session_id}/stats")
async def session_stats(session_id: str) -> dict[str, Any]:
    agent = await _get_or_load_agent(session_id)
    by_role: dict[str, int] = {}
    for m in agent.messages:
        by_role[m.role] = by_role.get(m.role, 0) + 1
    return {
        "messages": len(agent.messages),
        "by_role": by_role,
        "plan_mode": agent.plan_mode,
        "model": agent.router.provider.model if hasattr(agent.router.provider, "model") else None,
    }
