# Architecture

The agent is a small set of cooperating components. Each layer has a single
responsibility and a stable interface so it can be replaced independently.

```
+--------------------------------------------------------------+
|                            CLI / API                         |
|        (typer + rich)             (FastAPI + SSE)            |
+----------+-----------------------------------+---------------+
           |                                   |
           v                                   v
+--------------------------------------------------------------+
|                         Agent (core)                         |
|   plan -> request tool calls -> validate -> execute -> obs   |
+----+-----------------------------+----------------+----------+
     |                             |                |
     v                             v                v
+----------+               +---------------+   +----------+
| Memory   |               | Safety        |   | Tools    |
| (SQLite) |               | Validator     |   | Registry |
+----------+               +---------------+   +----------+
                                                    |
                                                    v
                                          +-----------------+
                                          | Tool plugins:   |
                                          | file/shell/git  |
                                          | search/python/  |
                                          | package         |
                                          +-----------------+

+--------------------------------------------------------------+
|                       Model Router                           |
|   Ollama provider  |  OpenAI-compatible provider             |
+--------------------------------------------------------------+
```

## Components

### Core agent loop (`ai_agent/core/agent.py`)

A simple ReAct loop with **native tool calling** — no fragile regex parsing.
Each step:

1. Send the message history + tool specs to the provider.
2. If the assistant returns `tool_calls`, validate each one against the safety
   layer, optionally prompt for confirmation, dispatch the tool, and append the
   result as a `role=tool` message.
3. If the assistant returns plain content (no tool calls), emit a `final` event
   and stop.

Bounded by `agent.max_steps` (default 25). All events are streamed as
`AgentEvent` instances so the CLI and the SSE endpoint share one renderer.

### Tools (`ai_agent/tools/`)

Each tool is a `Tool` subclass with:

- a unique `name`
- a Pydantic `Args` model (becomes the JSON schema sent to the model)
- an async `_run(args, ctx)` that returns `ToolResult`

`Tool.to_openai_spec()` auto-generates the OpenAI/Ollama function spec from the
Pydantic schema — adding a tool is one class definition plus one line in
`build_default_registry()`.

Built-in tools:

| Name              | Read-only | Requires confirm | Notes                        |
|-------------------|-----------|------------------|------------------------------|
| `read_file`       | ✓         |                  | with optional line slice     |
| `write_file`      |           |                  | full overwrite               |
| `edit_file`       |           |                  | unique-match string replace  |
| `create_file`     |           |                  | fails if exists              |
| `delete_file`     |           | ✓                | files only, never directories |
| `list_directory`  | ✓         |                  | recursive + capped           |
| `search_project`  | ✓         |                  | regex content / glob names   |
| `execute_terminal`|           | ✓                | gated by denylist + patterns |
| `run_python`      |           | ✓                | subprocess isolation         |
| `git_status`      | ✓         |                  |                              |
| `git_diff`        | ✓         |                  |                              |
| `git_log`         | ✓         |                  |                              |
| `git_commit`      |           | ✓                |                              |
| `install_package` |           | ✓                | auto-detects pip/npm/pnpm/yarn |

### Safety (`ai_agent/safety/validator.py`)

Returns one of `allow / confirm / deny` for every tool call. The decision is
based on three things:

1. **Permission level** — `safe` denies all mutations; `normal` confirms
   high-risk ops; `full` is automation mode.
2. **Hard denylist** — substrings and regexes in `config/default.yaml` that are
   refused at every level (e.g. `rm -rf /`, `mkfs.*`, `format c:`).
3. **Tool category** — read-only tools always pass; high-risk tools always
   prompt in `normal` mode.

Path safety is enforced separately by `utils.paths.resolve_in_workspace`, which
refuses any path that escapes the workspace unless explicitly opted-in.

### Memory (`ai_agent/memory/store.py`)

SQLite via `aiosqlite`. Three tables:

- `sessions` — id, name, workspace, created_at
- `messages` — full ChatMessage round-trip (role, content, tool_calls, tool_call_id)
- `project_facts` — workspace-scoped k/v notes the agent can stash

The conversation window is unbounded in storage; the in-process message list is
what the model sees and is currently the full history (windowing comes in
Phase 2 once we add summarisation).

### Model providers (`ai_agent/models/`)

Two providers with a shared `ModelProvider` interface:

- `OllamaProvider` — uses `/api/chat` with `tools` parameter and `arguments` as
  objects (Ollama's native dialect).
- `OpenAICompatProvider` — standard `/v1/chat/completions` with `tools` and
  `tool_choice="auto"`. Works with vLLM, LM Studio, llama.cpp server, etc.

Both return a normalised `ChatResponse(content, tool_calls, finish_reason)`.
Adding a new backend (e.g. direct llama.cpp Python bindings) is one new class.

### CLI + API

The CLI is Typer + Rich; the API is FastAPI with a single `lifespan` that owns
the long-lived `router`, `memory`, `tools`, and `validator`. The chat endpoint
ships both a JSON-collected variant and a Server-Sent Events stream so a future
React/Next.js dashboard can render events in real time.

## Non-goals (deliberately deferred)

- **Real sandboxing.** `run_python` and `execute_terminal` are NOT isolated from
  the host. Docker / Firecracker / WASI come in Phase 3.
- **RAG over project files.** The model sees only what tools surface. ChromaDB
  + embeddings is wired into `pyproject.toml` as an optional dep, but the index
  is Phase 2.
- **Multi-agent orchestration.** One agent, one loop. The interfaces are clean
  enough to add a planner-as-agent later without rewriting the core.
- **Conversation summarisation.** History grows linearly. We rely on the
  provider's context window and model performance for now.
