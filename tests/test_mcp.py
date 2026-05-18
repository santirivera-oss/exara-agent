"""MCP integration tests — spawn a real mock MCP server as subprocess."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ai_agent.mcp.client import MCPClient
from ai_agent.mcp.config import MCPServerConfig, load_mcp_config
from ai_agent.mcp.manager import MCPManager, qualify
from ai_agent.tools.base import ToolContext
from ai_agent.tools.mcp_tool import MCPTool

MOCK = str(Path(__file__).parent / "_mock_mcp_server.py")


class _DummyLogger:
    def __getattr__(self, _):
        def f(*_a, **_k): ...
        return f


# --- config loader ---------------------------------------------------------

def test_load_mcp_config_missing_returns_empty(tmp_path):
    assert load_mcp_config(tmp_path / "nope.json") == {}


def test_load_mcp_config_malformed_returns_empty(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{ not json", encoding="utf-8")
    assert load_mcp_config(p) == {}


def test_load_mcp_config_parses_and_skips_disabled(tmp_path):
    p = tmp_path / "mcp.json"
    p.write_text(json.dumps({
        "mcpServers": {
            "alpha": {"command": "echo", "args": ["hi"]},
            "beta": {"command": "echo", "args": ["nope"], "disabled": True},
        }
    }), encoding="utf-8")
    servers = load_mcp_config(p)
    assert "alpha" in servers
    assert "beta" not in servers


# --- qualify name safety ---------------------------------------------------

def test_qualify_replaces_invalid_chars():
    assert qualify("my-server", "do/it") == "mcp__my-server__do_it"
    assert qualify("ok", "ok") == "mcp__ok__ok"


# --- live client against mock server ---------------------------------------

async def test_client_lists_tools_from_mock():
    client = MCPClient(
        name="mock", command=sys.executable, args=[MOCK],
    )
    try:
        await client.start()
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "echo"
        assert "Return" in tools[0]["description"]
    finally:
        await client.shutdown()


async def test_client_calls_tool():
    client = MCPClient(name="mock", command=sys.executable, args=[MOCK])
    try:
        await client.start()
        result = await client.call_tool("echo", {"text": "hello mcp"})
        assert result["ok"]
        assert result["text"] == "hello mcp"
    finally:
        await client.shutdown()


# --- manager + MCPTool integration ----------------------------------------

async def test_manager_starts_servers_and_exposes_tools(tmp_path):
    mgr = MCPManager()
    status = await mgr.start_all({
        "mock": MCPServerConfig(command=sys.executable, args=[MOCK]),
    })
    try:
        assert status["mock"].startswith("ok")
        tools = mgr.list_tools()
        assert len(tools) == 1
        meta = tools[0]
        assert meta.qualified_name == "mcp__mock__echo"

        # Wrap it as a Tool and run it
        wrapper = MCPTool(meta)
        ctx = ToolContext(workspace=tmp_path, settings=None, logger=_DummyLogger())
        out = await wrapper.run({"text": "hi"}, ctx)
        assert out.success
        assert out.output == "hi"
    finally:
        await mgr.shutdown_all()


async def test_manager_failing_server_is_skipped():
    mgr = MCPManager()
    status = await mgr.start_all({
        "good": MCPServerConfig(command=sys.executable, args=[MOCK]),
        "bad": MCPServerConfig(command="this-binary-does-not-exist-anywhere-xyz", args=[]),
    })
    try:
        assert status["good"].startswith("ok")
        assert status["bad"].startswith("error")
        # The good one still works
        assert "good" in mgr.clients
        assert "bad" not in mgr.clients
    finally:
        await mgr.shutdown_all()


# --- MCPTool spec generation ----------------------------------------------

async def test_mcptool_to_openai_spec_uses_server_schema(tmp_path):
    mgr = MCPManager()
    await mgr.start_all({"mock": MCPServerConfig(command=sys.executable, args=[MOCK])})
    try:
        meta = mgr.list_tools()[0]
        wrapper = MCPTool(meta)
        spec = wrapper.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "mcp__mock__echo"
        assert spec["function"]["parameters"]["properties"]["text"]["type"] == "string"
        assert "MCP:mock" in spec["function"]["description"]
    finally:
        await mgr.shutdown_all()
