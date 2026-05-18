# exara-agent

[![PyPI](https://img.shields.io/pypi/v/exara-agent.svg)](https://pypi.org/project/exara-agent/)
[![Python](https://img.shields.io/pypi/pyversions/exara-agent.svg)](https://pypi.org/project/exara-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Local-first autonomous AI agent for programming and system automation.**
Runs against **local models** (Ollama, vLLM, LM Studio, llama.cpp) or **any
OpenAI-compatible API** (OpenRouter, OpenAI, DeepSeek, Anthropic, Groq) using
native tool calling. Ships with a Rich CLI, a Next.js web UI, and
MCP (Model Context Protocol) support so you can plug in GitHub, filesystem,
Slack, Linear, Postgres, and the rest of the community catalog.

```bash
pip install exara-agent
exara init      # one-time interactive setup
exara chat      # talk to it from any folder
```

---

## What it does

- **ReAct loop with native tool calling** — no fragile JSON parsing, the model
  emits real function calls.
- **30+ built-in tools** — file ops, multi-edit, search, shell, background
  processes, Python execution, git, package install, web fetch, vision, audio,
  todos, plan mode, subagent delegation.
- **MCP client** — `~/.ai-agent/mcp.json` works the same as Claude Desktop /
  Cursor: drop in any server from the catalog and the tools appear in the
  agent. Multi-source merge: bundled defaults → user-global → per-workspace.
- **Skills system** — markdown knowledge packs with auto-activation by stack
  (Python, Next.js, FastAPI, …). 10 ship out of the box; add your own at
  `~/.ai-agent/skills/` (global) or `./skills/` (per-project).
- **Multi-provider profiles** — `exara profile use openrouter` to swap. Keys
  live in `~/.ai-agent/profiles.json`, never in the repo.
- **Three-tier permission model** — `safe` / `normal` / `full`, with a hard
  denylist for destructive commands (`rm -rf /`, `mkfs.*`, `format c:`, …)
  enforced at every level.
- **Streaming responses + per-tool diff previews** — Claude Code-style UX.
- **Auto-context compaction** — keeps long sessions inside the model's window
  without you noticing.
- **Hooks** — shell commands fired on `session_start`, `pre_tool_use`,
  `post_tool_use`, etc. Same model as Claude Code.
- **Docker sandbox** (optional) — route `run_python` and `execute_terminal`
  through a disposable container instead of your host shell.
- **Secret redaction** — `OPENAI_API_KEY=…`, GitHub PATs, AWS keys, Bearer
  tokens, and DB URLs are scrubbed from every tool output before they reach
  the model.

---

## Install

```bash
pip install exara-agent
```

Or with [pipx](https://pipx.pypa.io/) for global isolation (recommended):

```bash
pipx install exara-agent
```

One-liner installers (detect Python, install pipx if missing, run wizard):

```bash
# macOS / Linux
curl -sSL https://raw.githubusercontent.com/santirivera-oss/exara-agent/main/scripts/install.sh | bash
```

```powershell
# Windows (PowerShell)
iwr https://raw.githubusercontent.com/santirivera-oss/exara-agent/main/scripts/install.ps1 | iex
```

### First run

```bash
exara init
```

Interactive wizard. Picks a provider, asks for an API key, optionally enables
MCP servers (filesystem / github / memory / sequential-thinking) and writes
a starter skill at `~/.ai-agent/skills/my-preferences.md`.

### Sanity check

```bash
exara doctor       # provider reachable? tools loaded? memory writable?
exara skills list  # which skills are active in this cwd
exara mcp list     # which MCP servers + tools are wired up
```

---

## Use it

```bash
# One-shot task
exara run "summarise the structure of this project"

# Interactive REPL
exara chat

# Web UI (after `npm install` in frontend/)
exara serve   # http://127.0.0.1:8765
cd frontend && npm run dev   # http://localhost:3100
```

### Slash commands

```
/help     /tools    /sessions       /resume <id>
/model    /plan     /init           /compact
/stats    /todos    /ps             /clear
```

### Command reference

Full bilingual command list:

- [`docs/COMMANDS.md`](docs/COMMANDS.md) - every CLI command, MCP/profile/skills/memory command, and chat slash command in English and Spanish.

---

## Providers

Anything OpenAI-compatible works out of the box. Built-in presets:

| Preset         | Endpoint                              | Default model            |
|----------------|---------------------------------------|--------------------------|
| `ollama-local` | http://localhost:11434                | `qwen2.5:7b-instruct`    |
| `openrouter`   | https://openrouter.ai/api/v1          | `deepseek/deepseek-chat` |
| `openai`       | https://api.openai.com/v1             | `gpt-4o-mini`            |
| `anthropic`    | https://api.anthropic.com/v1          | `claude-haiku-4-5`       |
| `deepseek`     | https://api.deepseek.com/v1           | `deepseek-chat`          |
| `groq`         | https://api.groq.com/openai/v1        | `llama-3.3-70b-versatile`|
| `lm-studio`    | http://localhost:1234/v1              | (whatever you loaded)    |

```bash
exara profile presets       # show the catalog
exara profile add --from openrouter --use
exara profile use ollama-local
```

---

## Permission levels

| Level    | Reads | Writes / shell / python | Confirmation         |
|----------|-------|-------------------------|----------------------|
| `safe`   | yes   | denied                  | n/a                  |
| `normal` | yes   | allowed                 | required on high-risk|
| `full`   | yes   | allowed                 | skipped              |

Destructive command patterns (`rm -rf /`, `mkfs.*`, `format c:`, etc.) are
blocked at every level via the bundled `default_config.yaml`.

---

## Config layout

```
~/.ai-agent/
├── profiles.json        # provider keys (gitignored by design)
├── mcp.json             # global MCP servers
├── config.yaml          # optional global overrides
├── skills/              # global skills (always loaded)
│   └── my-preferences.md
├── data/agent.db        # conversation memory (SQLite)
└── logs/                # JSON logs

./                        # per-workspace overrides
├── .env                 # env vars (highest precedence)
├── config.yaml          # workspace-only overrides
├── mcp.json             # workspace MCP servers (merged on top of global)
└── skills/              # workspace skills (override globals by name)
```

Precedence (low → high): bundled defaults → `~/.ai-agent/config.yaml` →
workspace `config.yaml` → active profile → `AI_AGENT_*` env vars.

---

## Architecture & docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — internals, ReAct loop, tool registry
- [`docs/MCP.md`](docs/MCP.md) — how MCP integration works
- [`docs/COMMANDS.md`](docs/COMMANDS.md) - bilingual CLI command reference
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what's next
- [`CHANGELOG.md`](CHANGELOG.md) — release notes

---

## Develop

```bash
git clone https://github.com/santirivera-oss/exara-agent
cd exara-agent
python -m venv .venv
. .venv/Scripts/Activate.ps1     # PowerShell on Windows
# source .venv/bin/activate      # macOS / Linux
pip install -e ".[dev]"
pytest                           # backend tests

# Web UI
cd frontend
npm install
npm run dev                      # http://localhost:3100
```

---

## License

MIT — see [LICENSE](LICENSE).
