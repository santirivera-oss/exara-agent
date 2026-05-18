# Roadmap

## Phase 1 — MVP (done)

- [x] Tool plugin system with auto-generated JSON schema
- [x] File / shell / search / python / git / package tools
- [x] Safety validator (3 levels + denylist)
- [x] Ollama + OpenAI-compatible providers
- [x] SQLite memory store (sessions, messages, project facts)
- [x] CLI: chat, run, models, doctor, tools, serve
- [x] FastAPI server with SSE chat stream
- [x] Unit tests for safety, tools, memory

## Phase 2 — Quality + UX

- [ ] **Streaming tool calls.** Today only final answers stream. Surface
      partial `tool_call` deltas as the model writes them.
- [ ] **Conversation summarisation.** Compact old turns when approaching the
      model's context window. Use a fast cheap model for the summary.
- [ ] **Project indexer.** Optional ChromaDB-backed RAG over the workspace,
      exposed as a `find_relevant_code` tool. Already a `[embeddings]` extra in
      `pyproject.toml`.
- [ ] **Better diff editing.** A `patch_file` tool that takes a unified diff
      and applies it atomically (less prone to context-mismatch failures than
      `edit_file`).
- [ ] **Web dashboard.** Next.js + shadcn/ui app talking to `/chat/stream`.
      Live event log, file tree, diff view, confirmation prompts in UI.
- [ ] **Tool permission overrides.** Per-tool allowlist / blocklist in config
      (today permission is global by level).
- [ ] **Cost / latency telemetry.** Per-step timing already logged; surface in
      a `/stats` endpoint and CLI command.

## Phase 3 — Capability expansion

- [ ] **Sandboxed execution.** Docker-based shell + Python runner. Optional
      Firecracker microVM for higher isolation.
- [ ] **Browser tool.** Headless Chromium via Playwright — read pages, fill
      forms, scrape data.
- [ ] **OCR + vision.** Tesseract for screenshots; multimodal model for
      vision-language tasks.
- [ ] **Desktop automation.** Win32/AppleScript/xdotool wrappers.
- [ ] **Specialised sub-agents.** Planner / coder / reviewer / tester running
      concurrently with shared memory. Reuse the same tool registry.
- [ ] **GitHub integration.** `gh` CLI wrapper + PR review tool.
- [ ] **Discord / Slack adapter.** Run the agent as a bot.

## Phase 4 — Productisation

- [ ] **Auth + multi-user.** Session ownership, per-user permission scopes.
- [ ] **Hosted control plane.** Optional managed server with workspaces and
      teams. Local execution stays local.
- [ ] **Plugin marketplace.** Third-party tools as installable Python
      packages discovered via entry points.
- [ ] **Observability stack.** Structured-log shipping (OpenTelemetry).
- [ ] **Crash-safe long-running tasks.** Pause/resume across restarts (a
      lightweight workflow engine on top of the memory store).

## Non-goals

- Replacing IDE features that are well solved by Cursor / Continue / Aider.
- Becoming a generic chat UI. The product is the *agentic loop with tools*.
- Cloud-only deployment. Local-first is the differentiator; remote is opt-in.
