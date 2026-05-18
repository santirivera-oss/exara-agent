# Custom MCP servers

Local MCP servers you can spawn from your own machine. Drop a script here,
register it in `mcp.json` (or via `exara mcp install <name>` if it's in
the catalogue), and the agent picks up its tools automatically.

## mt5_server.py — MetaTrader 5

Trading + market data via the MetaTrader5 Python package.

```bash
pip install MetaTrader5
```

You also need the MT5 terminal installed and (typically) running on the
same machine.

Quick install:

```powershell
exara mcp install mt5
# you'll be asked for: MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
```

Tools exposed (prefix `mcp__mt5__`):
- `account_info` — balance / equity / margin / leverage
- `terminal_info` — connection state, build
- `symbols_total` — count of symbols in Market Watch
- `symbol_info` — full info for one symbol
- `copy_rates` — last N OHLC bars (M1/M5/M15/M30/H1/H4/D1/W1/MN1)
- `positions_get` — currently open positions
- `orders_get` — pending orders
- `history_orders` — closed orders in the last N days
- `order_send` — **disabled by default**. Set `MT5_ALLOW_ORDERS=1` in the
  server's env block to enable. Even then, the agent's safety layer asks
  for confirmation in `normal` permission mode.

## Writing your own

An MCP stdio server is ~30 lines of Python. Template:

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("my-name")

@server.list_tools()
async def list_tools(): ...

@server.call_tool()
async def call_tool(name: str, args: dict): ...

async def main():
    async with stdio_server() as (r, w):
        await server.run(r, w, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

Then add to `mcp.json`:

```json
{
  "mcpServers": {
    "my-name": {
      "command": "python",
      "args": ["mcp_servers/my_server.py"]
    }
  }
}
```
