# MCP — Model Context Protocol integration

The agent ships with an MCP client. Any MCP server you list in `mcp.json` is
spawned at session start and its tools are merged into the registry next to
the built-ins. No code changes required to plug in GitHub, Slack, Linear,
filesystem, Postgres, Brave Search, or any of the dozens of community servers.

## Quick start

1. **Copy the template**:
   ```powershell
   copy mcp.example.json mcp.json
   ```

2. **Edit `mcp.json`** — un-disable the servers you want, set any env vars.

3. **Inspect**:
   ```powershell
   exara mcp list
   ```

4. **Verify a tool**:
   ```powershell
   exara mcp test filesystem list_directory --args '{"path":"."}'
   ```

5. **Use it** — start a normal `exara chat` and the model will see the MCP
   tools listed under the `mcp__<server>__<tool>` prefix.

## File format

The shape matches Claude Desktop / Cursor so existing configs work as-is:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/some/path"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_..." },
      "disabled": false
    }
  }
}
```

- `command` + `args` — how to launch the server (subprocess, stdio transport).
- `env` — extra env vars passed to the child process. The current `os.environ`
  is inherited; these override individual keys.
- `disabled: true` — skip this server at startup. Useful for keeping configs
  around without actually launching them.

## Tool naming

Each MCP tool is registered as `mcp__<server>__<tool>`. Example:

```
mcp__filesystem__read_file
mcp__github__create_issue
mcp__brave-search__brave_web_search
```

The prefix prevents collisions between servers that publish the same tool
name. The model sees these names in its tool list with the description
prefixed by `[MCP:<server>]`.

## Lifecycle

- **Startup**: when `Agent.init()` runs, all MCP servers boot in parallel.
  Failures are logged but never crash the agent — a missing or broken server
  is simply skipped.
- **Shutdown**: call `await agent.shutdown()` to terminate every MCP subprocess.
  The CLI and FastAPI server do this automatically.
- **Per session**: each Agent instance owns its own MCP subprocesses. If you
  spawn multiple sessions in parallel (e.g. several `/chat/stream` requests),
  each one boots its own.

## Safety

MCP tools go through the same `Validator` as built-in tools:
- In `safe` permission mode they are **denied** (unless we later add a way to
  mark specific MCP tools as read-only).
- In `normal` mode they execute without confirmation by default — they aren't
  in the `HIGH_RISK_TOOLS` list yet. Treat MCP servers as trusted.
- In `full` mode anything goes.

If you wire a powerful MCP server (e.g. GitHub with write scopes), consider
running the agent in `normal` mode with the confirmation modal enabled in the
web UI so you approve each tool call.

## Configuration

Override the config path via env:

```bash
AI_AGENT_MCP_CONFIG=./path/to/custom-mcp.json
AI_AGENT_MCP_ENABLED=true
```

Or in `config/default.yaml`:

```yaml
mcp:
  enabled: true
  config_path: ./mcp.json
```

## Caveats

- Only stdio transport is supported for now. HTTP / streamable-HTTP servers
  will be added when needed.
- `resources` and `prompts` MCP features are out of scope for v1 — only
  `tools` are exposed.
- The agent does not yet differentiate MCP tools in the safety layer. If you
  install a server with a destructive tool (e.g. `delete_repo`), it will run
  in `normal` mode without prompting.
