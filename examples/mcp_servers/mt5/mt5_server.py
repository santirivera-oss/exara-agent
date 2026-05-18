"""MetaTrader 5 MCP server.

Wraps the `MetaTrader5` Python package as an MCP stdio server. Lets the agent
inspect accounts, browse symbols, fetch price history, look at positions, and
(behind a confirm gate) place orders.

PREREQUISITES
- MetaTrader 5 installed and running on the same machine
- pip install MetaTrader5 mcp

REGISTER IN mcp.json:
    "mt5": {
      "command": "python",
      "args": ["examples/mcp_servers/mt5/mt5_server.py"],
      "env": {
        "MT5_LOGIN": "12345678",
        "MT5_PASSWORD": "secret",
        "MT5_SERVER": "MetaQuotes-Demo"
      }
    }

Then `exara chat` will pick up tools like `mcp__mt5__account_info`,
`mcp__mt5__symbol_info`, `mcp__mt5__copy_rates`, `mcp__mt5__positions_get`.

Place-order tool is **always disabled by default**. Set MT5_ALLOW_ORDERS=1 in
env to enable. Even then, the agent's safety layer will still require
confirmation in normal permission mode.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any

try:
    import MetaTrader5 as mt5  # type: ignore[import]
except ImportError:
    mt5 = None  # type: ignore[assignment]

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool


_ORDERS_ENABLED = os.getenv("MT5_ALLOW_ORDERS", "").lower() in ("1", "true", "yes")


def _require_mt5() -> None:
    if mt5 is None:
        raise RuntimeError(
            "MetaTrader5 package not installed. Run: pip install MetaTrader5  "
            "(Windows only; you also need the MT5 terminal installed)."
        )


def _ensure_initialized() -> None:
    _require_mt5()
    if mt5.terminal_info() is not None:
        return
    login = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")
    if login and password and server:
        ok = mt5.initialize(login=int(login), password=password, server=server)
    else:
        ok = mt5.initialize()
    if not ok:
        last = mt5.last_error()
        raise RuntimeError(f"mt5.initialize() failed: {last}")


def _json(obj: Any) -> str:
    """Serialise MT5 namedtuples / datetimes to JSON nicely."""
    def fallback(o):
        if isinstance(o, datetime):
            return o.isoformat()
        if hasattr(o, "_asdict"):
            return o._asdict()
        return str(o)
    return json.dumps(obj, default=fallback, indent=2, ensure_ascii=False)


def _build_tools() -> list[Tool]:
    tools = [
        Tool(
            name="account_info",
            description="Get the connected MT5 account (balance, equity, margin, leverage, etc.)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="terminal_info",
            description="Get MT5 terminal status (connected, build, path)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="symbols_total",
            description="Return the number of symbols available in the Market Watch",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="symbol_info",
            description="Get full info for a symbol (bid/ask, point, spread, volumes, trading sessions, etc.)",
            inputSchema={
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        ),
        Tool(
            name="copy_rates",
            description="Fetch historical OHLC bars for a symbol. Returns up to `count` most-recent bars.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "timeframe": {
                        "type": "string",
                        "enum": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
                        "default": "M5",
                    },
                    "count": {"type": "integer", "default": 100, "minimum": 1, "maximum": 5000},
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="positions_get",
            description="List currently open positions. Optionally filter by symbol.",
            inputSchema={
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
            },
        ),
        Tool(
            name="orders_get",
            description="List pending orders. Optionally filter by symbol.",
            inputSchema={
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
            },
        ),
        Tool(
            name="history_orders",
            description="Closed orders in the last N days.",
            inputSchema={
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 7, "minimum": 1, "maximum": 365}},
            },
        ),
    ]
    if _ORDERS_ENABLED:
        tools.append(Tool(
            name="order_send",
            description=(
                "Place a market order. ONLY enabled when MT5_ALLOW_ORDERS=1. "
                "Use with extreme care — this trades real money on a live account."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "type": {"type": "string", "enum": ["BUY", "SELL"]},
                    "volume": {"type": "number", "minimum": 0.01},
                    "sl": {"type": "number", "description": "Stop loss price; 0 for none"},
                    "tp": {"type": "number", "description": "Take profit price; 0 for none"},
                    "comment": {"type": "string", "default": "ai-agent"},
                },
                "required": ["symbol", "type", "volume"],
            },
        ))
    return tools


def _timeframe_to_mt5(tf: str) -> int:
    return {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
    }[tf]


async def _call(name: str, args: dict) -> str:
    _ensure_initialized()
    if name == "account_info":
        info = mt5.account_info()
        return _json(info._asdict() if info else None)
    if name == "terminal_info":
        info = mt5.terminal_info()
        return _json(info._asdict() if info else None)
    if name == "symbols_total":
        return _json({"total": mt5.symbols_total()})
    if name == "symbol_info":
        info = mt5.symbol_info(args["symbol"])
        if info is None:
            return _json({"error": f"symbol not found: {args['symbol']}"})
        return _json(info._asdict())
    if name == "copy_rates":
        tf = _timeframe_to_mt5(args.get("timeframe", "M5"))
        rates = mt5.copy_rates_from_pos(args["symbol"], tf, 0, args.get("count", 100))
        if rates is None:
            return _json({"error": "no data"})
        return _json([dict(zip(rates.dtype.names, row)) for row in rates])
    if name == "positions_get":
        sym = args.get("symbol")
        positions = mt5.positions_get(symbol=sym) if sym else mt5.positions_get()
        return _json([p._asdict() for p in (positions or ())])
    if name == "orders_get":
        sym = args.get("symbol")
        orders = mt5.orders_get(symbol=sym) if sym else mt5.orders_get()
        return _json([o._asdict() for o in (orders or ())])
    if name == "history_orders":
        days = args.get("days", 7)
        end = datetime.now()
        start = end - timedelta(days=days)
        rows = mt5.history_orders_get(start, end) or ()
        return _json([r._asdict() for r in rows])
    if name == "order_send":
        if not _ORDERS_ENABLED:
            return _json({"error": "Order placement disabled. Set MT5_ALLOW_ORDERS=1 to enable."})
        order_type = mt5.ORDER_TYPE_BUY if args["type"] == "BUY" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(args["symbol"])
        if tick is None:
            return _json({"error": f"no tick for {args['symbol']}"})
        price = tick.ask if args["type"] == "BUY" else tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": args["symbol"],
            "volume": float(args["volume"]),
            "type": order_type,
            "price": price,
            "sl": float(args.get("sl") or 0),
            "tp": float(args.get("tp") or 0),
            "comment": args.get("comment", "ai-agent"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        return _json(result._asdict() if result else {"error": "order_send returned None"})
    raise ValueError(f"unknown tool: {name}")


def make_server() -> Server:
    server = Server("mt5")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return _build_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            text = await _call(name, arguments)
        except Exception as e:
            text = json.dumps({"error": str(e)})
        return [TextContent(type="text", text=text)]

    return server


async def _main() -> None:
    server = make_server()
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(_main())
