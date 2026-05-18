# Changelog

## [0.1.1] - 2026-05-18

### Added
- `exara doctor --fix` to create safe missing local directories and a starter global MCP config.
- `exara memory list/set/search/forget` for managing project memory facts from the CLI.

### Improved
- MCP catalogue now shows launchers and recommends global installs for portable setup.
- `exara mcp test` now sees merged global + workspace MCP configs.
- `exara skills show` can display bundled and user-wide skills, not only workspace skills.

## [0.1.0] — 2026-05-16

First public-ready snapshot. Functional MVP with **27 tools**, **93 tests**, web UI
and CLI both operational against local Ollama and remote OpenAI-compat providers.

### Agent core
- ReAct-style planner+executor loop with native tool calling
- Configurable model providers: Ollama, OpenAI-compatible (vLLM, LM Studio,
  OpenRouter, OpenAI directly)
- Three permission levels (`safe`, `normal`, `full`) with hard denylist for
  destructive commands
- Plan mode with `exit_plan_mode` tool and write-blocking guard
- Loop detection (repeated tool calls) with corrective feedback
- Placeholder detection (rejects `<placeholder>` args)
- Auto-context compaction when history exceeds threshold
- Per-session subprocess manager (background processes survive across turns)
- CLAUDE.md / AGENTS.md awareness — auto-loaded into the system prompt
- Token streaming with concurrent tool-call accumulation
- Diff preview before any file mutation

### Tools (27)
- File ops: `read_file`, `write_file`, `edit_file`, `multi_edit`, `create_file`, `delete_file`, `list_directory`, `search_project`
- Web: `web_fetch` (with `extract` for term-focused fetches)
- Multimodal: `read_image`, `read_audio` (with hybrid-provider routing)
- Shell: `execute_terminal`, `bash_background`, `monitor`, `kill_process`, `list_processes`
- Code: `run_python`
- Git: `git_status`, `git_diff`, `git_log`, `git_commit`
- Packages: `install_package` (pip / npm / pnpm / yarn auto-detect)
- Planning: `exit_plan_mode`, `delegate` (read-only subagent)
- Todos: `todo_write`, `todo_read`

### Safety
- Three-tier permission model
- Hard denylist for destructive shell commands
- Per-tool confirmation in normal mode (interactive in CLI, modal in web)
- Plan mode hard-blocks all mutations
- Placeholder + loop detection prevent small-model failure modes
- Friendly errors for HTTP 401 / 402 / 404 / 429 with auto-retry on 429

### Interfaces
- CLI: `chat`, `run`, `models`, `doctor`, `tools`, `serve` (Typer + Rich)
- Slash commands: `/help`, `/clear`, `/tools`, `/sessions`, `/resume`, `/model`,
  `/plan`, `/init`, `/compact`, `/stats`, `/todos`, `/ps`
- FastAPI server with SSE streaming and REST controls (plan, compact, stats, confirm)
- Web frontend (Next.js 16 + Tailwind + shadcn/ui):
  - Markdown rendering + syntax highlighting
  - Side panel (sessions, tools, slash actions)
  - Real confirmation modal with diff preview
  - Auto-confirm toggle

### Storage
- SQLite (via aiosqlite): sessions, messages, project facts, todos
- Hybrid multimodal: agent on remote API + vision on local Ollama (or vice versa)
