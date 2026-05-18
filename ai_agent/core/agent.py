"""Core agent loop — plan/act/observe via native tool calling."""
from __future__ import annotations

import hashlib
import json
import re
import time
from asyncio import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

from ..config import Settings
from ..memory.store import MemoryStore
from ..models.base import ChatMessage, ToolCall
from ..models.router import ModelRouter
from ..safety.validator import SafetyDecision, SafetyVerdict, Validator
from ..mcp.manager import MCPManager
from ..tools.background import ProcessManager
from ..tools.base import ToolContext, ToolResult
from ..tools.mcp_tool import MCPTool
from ..tools.registry import WRITE_TOOLS, ToolRegistry
from ..utils.logging import get_logger
from .diff import preview_for_tool
from .hooks import run_hooks
from .prompts import build_system_prompt

logger = get_logger("agent")

ConfirmationHandler = Callable[[str, dict, SafetyDecision], Awaitable[bool]]


@dataclass
class AgentEvent:
    """Streaming event emitted by the agent loop."""
    type: Literal[
        "thought", "tool_call", "tool_result", "denied", "final", "error",
        "step", "preview", "plan_submitted", "content_delta", "confirm_request",
    ]
    content: str = ""
    tool: str | None = None
    args: dict | None = None
    success: bool | None = None
    step: int | None = None
    data: dict | None = None


async def _auto_allow(_name: str, _args: dict, _dec: SafetyDecision) -> bool:
    return True


class Agent:
    """Stateful agent — owns the message history for a session."""

    def __init__(
        self,
        settings: Settings,
        router: ModelRouter,
        tools: ToolRegistry,
        memory: MemoryStore,
        validator: Validator,
        *,
        session_id: str | None = None,
        confirm: ConfirmationHandler | None = None,
    ):
        self.settings = settings
        self.router = router
        self.tools = tools
        self.memory = memory
        self.validator = validator
        self.session_id = session_id
        self.confirm = confirm or _auto_allow
        self._messages: list[ChatMessage] = []
        self._system_initialised = False
        self.plan_mode: bool = False
        # Long-lived background subprocesses spawned via bash_background.
        self.processes = ProcessManager()
        # confirmation_id → Future[bool]. Populated by the web flow when a CONFIRM
        # decision is hit; resolved externally by POST /sessions/{sid}/confirm/{cid}.
        self.pending_confirms: dict[str, Future[bool]] = {}
        # MCP servers and the tools they expose are loaded in init() and live
        # until shutdown(). Failures in one server don't bring down others.
        self.mcp = MCPManager()
        # Tool extras persisted across run() calls — used by long-lived
        # resources like the Playwright browser that survive between turns.
        self._tool_extra: dict[str, Any] = {}

    async def init(self, *, session_name: str | None = None) -> str:
        """Create or load a memory session and seed the system prompt."""
        await self.memory.init()
        ws = str(self.settings.workspace.resolve())
        if self.session_id:
            self._messages = await self.memory.load_messages(self.session_id)
        else:
            self.session_id = await self.memory.create_session(session_name, ws)

        # Spawn MCP servers first — the system prompt will then list their
        # tools, and (if the memory server is installed) we auto-hydrate the
        # prompt with what we know about the user/project from previous sessions.
        await self._load_mcp_tools()
        if not any(m.role == "system" for m in self._messages):
            await self._install_system_prompt()
        # Fire session_start hooks
        hooks_cfg = getattr(self.settings, "hooks", None)
        if hooks_cfg and hooks_cfg.session_start:
            await run_hooks(hooks_cfg.session_start, {
                "session_id": self.session_id,
                "workspace": str(self.settings.workspace),
            })
        self._system_initialised = True
        return self.session_id

    async def _read_memory_graph(self) -> str:
        """If a `memory` MCP server is active, pull its knowledge graph as
        plain text to seed the system prompt. Returns empty string if no
        server is loaded or the call fails.
        """
        client = self.mcp.clients.get("memory")
        if client is None:
            return ""
        try:
            res = await client.call_tool("read_graph", {})
        except Exception:
            return ""
        if not res.get("ok"):
            return ""
        return (res.get("text") or "").strip()

    async def _load_mcp_tools(self) -> None:
        cfg = getattr(self.settings, "mcp", None)
        if cfg is None or not cfg.enabled:
            return
        from pathlib import Path
        from ..mcp.config import load_merged_mcp_config
        path = Path(cfg.config_path)
        if not path.is_absolute():
            path = self.settings.workspace / path
        # Merge ~/.ai-agent/mcp.json (user-wide, available from any cwd) with
        # the workspace-specific mcp.json. Workspace wins on name collisions.
        servers = load_merged_mcp_config(path)
        if not servers:
            return
        status = await self.mcp.start_all(servers)
        for name, msg in status.items():
            logger.info("mcp_server_started", server=name, status=msg)
        for meta in self.mcp.list_tools():
            try:
                self.tools.register(MCPTool(meta))
            except ValueError as e:
                # name collision with a built-in tool — skip and warn
                logger.warning("mcp_tool_skipped", tool=meta.qualified_name, error=str(e))

    def _build_system_message(self, memory_context: str = "", skills_block: str = "") -> ChatMessage:
        return ChatMessage(role="system", content=build_system_prompt(
            self.settings.workspace,
            self.tools.names(),
            self.validator.level,
            plan_mode=self.plan_mode,
            memory_context=memory_context,
            skills_block=skills_block,
        ))

    def _load_skills_block(self, user_text: str | None = None) -> str:
        """Pick auto-active skills based on the workspace stack and prompt keywords.

        Loads from THREE sources merged by name (later wins):
        1. Built-in skills shipped with the pip package (always available).
        2. ~/.ai-agent/skills/  — user-wide overrides you want everywhere.
        3. ./skills/  (or whatever settings.skills.dir points to) — project-specific.
        """
        cfg = getattr(self.settings, "skills", None)
        if cfg is None or not cfg.enabled:
            return ""
        from pathlib import Path as _P
        from ..skills import detect_stack, load_all_skills, render_skill_block, select_active
        skills_dir = _P(cfg.dir)
        if not skills_dir.is_absolute():
            skills_dir = self.settings.workspace / skills_dir
        skills = load_all_skills(skills_dir)
        if not skills:
            return ""
        tags, files = detect_stack(self.settings.workspace)
        active = select_active(skills, stack_tags=tags, files=files, user_text=user_text)
        block = render_skill_block(active)
        if len(block) > cfg.max_chars:
            block = block[: cfg.max_chars] + "\n... (skills truncated)"
        return block

    async def _install_system_prompt(self) -> None:
        graph = await self._read_memory_graph()
        skills = self._load_skills_block()
        msg = self._build_system_message(memory_context=graph, skills_block=skills)
        self._messages.insert(0, msg)
        if self.session_id:
            await self.memory.append_message(self.session_id, msg)

    def set_plan_mode(self, enabled: bool) -> None:
        """Toggle plan mode. Rebuilds the in-memory system prompt so the new instructions
        take effect on the next model call. We do NOT persist the rebuilt prompt — plan
        mode is an ephemeral runtime flag, not session state.
        """
        self.plan_mode = enabled
        if self._messages and self._messages[0].role == "system":
            self._messages[0] = self._build_system_message()
        else:
            self._messages.insert(0, self._build_system_message())

    @property
    def messages(self) -> list[ChatMessage]:
        return list(self._messages)

    async def _append(self, msg: ChatMessage) -> None:
        self._messages.append(msg)
        if self.session_id:
            await self.memory.append_message(self.session_id, msg)

    async def run(self, user_input: str) -> AsyncIterator[AgentEvent]:
        """Process one user turn — yields events until a final answer or error."""
        if not self._system_initialised:
            await self.init()

        user_msg = ChatMessage(role="user", content=user_input)
        await self._append(user_msg)

        # user_prompt_submit hooks (fire-and-forget, don't gate execution)
        hooks_cfg = getattr(self.settings, "hooks", None)
        if hooks_cfg and hooks_cfg.user_prompt_submit:
            await run_hooks(hooks_cfg.user_prompt_submit, {
                "session_id": self.session_id,
                "message": user_input,
            })

        ws = self.settings.workspace
        # Update the persistent extra dict in-place so long-lived resources
        # (browser, etc.) registered by previous calls survive.
        self._tool_extra.update({
            "router": self.router,
            "processes": self.processes,
            "memory": self.memory,
            "session_id": self.session_id,
            "pending_confirms": self.pending_confirms,
        })
        tool_ctx = ToolContext(
            workspace=ws,
            settings=self.settings,
            logger=logger,
            extra=self._tool_extra,
        )

        # Track consecutive identical tool calls so we can break out of a model
        # that gets stuck calling the same thing over and over (seen with smaller
        # models like Gemma 4 8B and some Llama variants).
        last_call_sig: str | None = None
        repeat_count = 0
        REPEAT_LIMIT = 2  # the 3rd identical call triggers a corrective response

        for step in range(1, self.settings.agent.max_steps + 1):
            # Recompute every iteration because plan_mode may flip mid-run.
            tools_spec = self._active_tool_specs()
            yield AgentEvent(type="step", step=step, content=f"step {step}")
            t0 = time.time()

            # We need an async generator to surface streaming deltas while the
            # provider call is still running. Bridge the provider's on_content
            # callback into an asyncio.Queue and drain it concurrently with the
            # provider request.
            import asyncio as _asyncio
            queue: _asyncio.Queue[str | None] = _asyncio.Queue()

            async def on_content(piece: str) -> None:
                await queue.put(piece)

            async def run_call():
                try:
                    return await self.router.provider.chat(
                        self._messages,
                        tools=tools_spec,
                        temperature=self.settings.agent.temperature,
                        max_tokens=self.settings.agent.max_tokens,
                        on_content=on_content if self.settings.agent.stream else None,
                    )
                finally:
                    await queue.put(None)  # sentinel: stream finished

            task = _asyncio.create_task(run_call())
            try:
                while True:
                    piece = await queue.get()
                    if piece is None:
                        break
                    yield AgentEvent(type="content_delta", content=piece)
                response = await task
            except Exception as e:
                task.cancel()
                # Several provider-side errors are self-explanatory and don't need stacks.
                from ..models.ollama import ModelNotInstalledError
                from ..models.openai_compat import (
                    ProviderAuthError, ProviderQuotaError, ProviderRateLimitError,
                )
                if isinstance(e, (ModelNotInstalledError, ProviderAuthError,
                                  ProviderQuotaError, ProviderRateLimitError)):
                    logger.warning("provider_error", error=str(e))
                    yield AgentEvent(type="error", content=str(e))
                else:
                    logger.exception("model_error", error=str(e))
                    yield AgentEvent(type="error", content=f"model call failed: {e}")
                return
            logger.debug("model_turn", step=step, latency_ms=int((time.time() - t0) * 1000),
                         tool_calls=len(response.tool_calls), has_content=bool(response.content))

            assistant_msg = ChatMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            )
            await self._append(assistant_msg)

            if not response.tool_calls:
                # Final answer.
                if response.content:
                    yield AgentEvent(type="final", content=response.content)
                else:
                    yield AgentEvent(type="final", content="(no response)")
                # Opportunistic compaction — silent unless something was actually collapsed.
                collapsed = await self.maybe_compact()
                if collapsed:
                    yield AgentEvent(
                        type="step",
                        content=f"context compacted ({collapsed} messages → 1 summary)",
                    )
                return

            # Loop guard: if the model repeats the same tool call back-to-back, it's
            # stuck. Inject corrective feedback as a tool result and break the loop.
            sig = _signature(response.tool_calls)
            if sig and sig == last_call_sig:
                repeat_count += 1
            else:
                repeat_count = 0
            last_call_sig = sig

            if repeat_count >= REPEAT_LIMIT:
                # Replace each tool call's "execution" with a synthesised error message,
                # so the model sees from its own protocol that repetition won't help.
                for tc in response.tool_calls:
                    await self._append(ChatMessage(
                        role="tool", tool_call_id=tc.id, name=tc.name,
                        content=(
                            f"LOOP DETECTED: you have called {tc.name} with identical "
                            f"arguments {repeat_count + 1} times in a row, receiving the same "
                            "result each time. Stop repeating. Either: (a) call a different "
                            "tool, (b) call this tool with different arguments, or (c) finalise "
                            "your answer using the information already gathered. If you do not "
                            "have enough information, say so plainly instead of looping."
                        ),
                    ))
                    yield AgentEvent(
                        type="denied", tool=tc.name,
                        content=f"loop guard: same call {repeat_count + 1}× — corrective feedback injected",
                    )
                repeat_count = 0
                last_call_sig = None
                continue

            # Execute each tool call.
            for tc in response.tool_calls:
                async for evt in self._execute_tool_call(tc, tool_ctx):
                    yield evt

        yield AgentEvent(
            type="error",
            content=f"max_steps={self.settings.agent.max_steps} exceeded without final answer",
        )

    async def shutdown(self) -> None:
        """Tear down resources owned by this agent (MCP servers, processes, browser)."""
        # Fire stop hooks first so users can do bookkeeping (notifications,
        # state dumps) before resources go away.
        hooks_cfg = getattr(self.settings, "hooks", None)
        if hooks_cfg and hooks_cfg.stop:
            try:
                await run_hooks(hooks_cfg.stop, {"session_id": self.session_id})
            except Exception as e:
                logger.warning("hook_stop_failed", error=str(e))
        # Close any long-lived browser context registered by the playwright tools.
        try:
            from ..tools.browser import close_browser_if_open
            await close_browser_if_open(self._tool_extra)
        except Exception:
            pass
        try:
            await self.mcp.shutdown_all()
        finally:
            await self.processes.kill_all()

    async def maybe_compact(self) -> int:
        """Auto-compact: replace older messages with a model-generated summary.

        Triggered automatically after each turn, or manually via /compact.
        Returns the number of messages that were collapsed (0 if no-op).

        Important: only the in-memory list passed to the model is mutated.
        The SQLite-persisted transcript is left untouched so history is recoverable.
        """
        mem_cfg = self.settings.memory
        threshold = mem_cfg.summarise_after_messages
        keep = mem_cfg.keep_recent
        # +1 for the system message that we always preserve.
        if len(self._messages) <= threshold:
            return 0

        # Always keep system message + last `keep` messages.
        sys_idx = 0 if self._messages and self._messages[0].role == "system" else -1
        head = self._messages[0:sys_idx + 1] if sys_idx >= 0 else []
        recent = self._messages[-keep:] if keep > 0 else []
        # Avoid summarising things that are already in the kept-recent slice.
        to_summarise = self._messages[len(head):-keep] if keep > 0 else self._messages[len(head):]
        if not to_summarise:
            return 0

        # Build a compact transcript for the summariser.
        lines: list[str] = []
        for m in to_summarise:
            if m.role == "tool":
                snippet = (m.content or "")[:400]
                lines.append(f"[tool:{m.name}] {snippet}")
            elif m.tool_calls:
                names = ", ".join(f"{tc.name}({_short(tc.arguments, 60)})" for tc in m.tool_calls)
                lines.append(f"[assistant→tools] {names}")
                if m.content:
                    lines.append(f"[assistant] {m.content[:400]}")
            else:
                lines.append(f"[{m.role}] {(m.content or '')[:600]}")
        transcript = "\n".join(lines)

        summariser_messages = [
            ChatMessage(role="system", content=(
                "You compact agent conversation history into a brief structured summary. "
                "Preserve: user goals, decisions made, files touched, key facts learned, "
                "open problems. Drop chitchat and intermediate tool noise. "
                "Output plain markdown, under 400 words."
            )),
            ChatMessage(role="user", content=(
                f"Summarise the following agent conversation. Keep all load-bearing facts.\n\n{transcript}"
            )),
        ]
        try:
            resp = await self.router.provider.chat(
                summariser_messages, tools=None, temperature=0.0,
            )
        except Exception as e:
            logger.warning("compact_failed", error=str(e))
            return 0

        summary = resp.content.strip() or "(no summary produced)"
        summary_msg = ChatMessage(
            role="system",
            content=(
                "# Compacted earlier history\n"
                f"The following replaces {len(to_summarise)} earlier messages "
                "to keep the context window manageable. The full transcript is "
                "preserved on disk.\n\n"
                f"{summary}"
            ),
        )
        self._messages = head + [summary_msg] + recent
        logger.info("compacted", collapsed=len(to_summarise),
                    remaining=len(self._messages))
        return len(to_summarise)

    def _active_tool_specs(self) -> list[dict]:
        """Tool specs visible to the model — write tools are stripped in plan mode."""
        specs = self.tools.openai_specs()
        if self.plan_mode:
            specs = [s for s in specs if s["function"]["name"] not in WRITE_TOOLS]
        return specs

    async def _execute_tool_call(
        self, tc: ToolCall, ctx: ToolContext
    ) -> AsyncIterator[AgentEvent]:
        # Plan-mode enforcement: even if the model hallucinates a write tool that
        # was stripped from its spec, refuse to dispatch it. The spec filter is
        # advisory; this is the real guard.
        if self.plan_mode and tc.name in WRITE_TOOLS:
            await self._append(ChatMessage(
                role="tool", tool_call_id=tc.id, name=tc.name,
                content=(
                    f"BLOCKED: '{tc.name}' is a write tool. You are in plan mode and "
                    "write tools are not allowed. Use read-only tools to investigate, "
                    "then call exit_plan_mode with your plan. The user will approve or "
                    "reject the plan before any writes happen."
                ),
            ))
            yield AgentEvent(
                type="denied", tool=tc.name,
                content=f"blocked in plan mode: {tc.name}",
            )
            return

        # Catch placeholder args — common failure mode of smaller models that emit
        # dependent tool calls in parallel without waiting for the first to complete.
        placeholder = _placeholder_in_args(tc.arguments)
        if placeholder:
            await self._append(ChatMessage(
                role="tool", tool_call_id=tc.id, name=tc.name,
                content=(
                    f"PLACEHOLDER DETECTED: argument value {placeholder!r} looks like a "
                    "placeholder, not a real value. Tool calls cannot reference future "
                    "outputs. If you need the result of another tool call, emit this call "
                    "in the NEXT turn (after you see the result), not in parallel with the "
                    "tool that produces the value. Re-emit with the actual value."
                ),
            ))
            yield AgentEvent(
                type="denied", tool=tc.name,
                content=f"placeholder in args: {placeholder} — corrective feedback injected",
            )
            return

        # Plan mode special case: intercept exit_plan_mode → submit plan and wait
        # for user approval. The CLI/API toggles plan_mode off when the user OKs.
        if tc.name == "exit_plan_mode" and self.plan_mode:
            plan_text = (tc.arguments or {}).get("plan", "")
            await self._append(ChatMessage(
                role="tool", tool_call_id=tc.id, name=tc.name,
                content="plan submitted for user review",
            ))
            yield AgentEvent(
                type="plan_submitted", tool=tc.name, content=plan_text,
                data={"plan": plan_text},
            )
            return

        decision = self.validator.check_tool(tc.name, tc.arguments)

        yield AgentEvent(type="tool_call", tool=tc.name, args=tc.arguments,
                         content=f"→ {tc.name}({_short(tc.arguments)})")

        # Show a unified-diff preview for any tool that mutates a file.
        preview = preview_for_tool(tc.name, tc.arguments, self.settings.workspace)
        if preview:
            yield AgentEvent(type="preview", tool=tc.name, content=preview)

        if decision.verdict == SafetyVerdict.DENY:
            await self._append(ChatMessage(
                role="tool",
                tool_call_id=tc.id,
                name=tc.name,
                content=f"DENIED: {decision.reason}",
            ))
            yield AgentEvent(type="denied", tool=tc.name, content=decision.reason)
            return

        if decision.verdict == SafetyVerdict.CONFIRM:
            # Two flows here:
            #
            # 1. **Web flow** (frontend / API): we emit a `confirm_request` event
            #    bearing a confirmation_id and block on a Future that the frontend
            #    resolves via POST /sessions/{sid}/confirm/{cid}.
            #
            # 2. **CLI flow**: fall back to the configured callback (Rich prompt).
            #
            # The web flow is selected when self.confirm is the default auto-allow
            # AND there's a pending_confirms registry available — i.e. the server
            # set up a place to land the user's response.
            import asyncio as _asyncio
            import uuid as _uuid

            pending = self.pending_confirms
            use_web_flow = self.confirm is _auto_allow and pending is not None

            if use_web_flow:
                cid = _uuid.uuid4().hex[:12]
                fut: _asyncio.Future[bool] = _asyncio.get_event_loop().create_future()
                pending[cid] = fut
                yield AgentEvent(
                    type="confirm_request",
                    tool=tc.name,
                    args=tc.arguments,
                    content=decision.reason,
                    data={
                        "confirmation_id": cid,
                        "tool_call_id": tc.id,
                        "preview": preview,
                    },
                )
                try:
                    ok = await _asyncio.wait_for(fut, timeout=600)
                except _asyncio.TimeoutError:
                    ok = False
                finally:
                    pending.pop(cid, None)
            else:
                ok = await self.confirm(tc.name, tc.arguments, decision)

            if not ok:
                await self._append(ChatMessage(
                    role="tool",
                    tool_call_id=tc.id,
                    name=tc.name,
                    content="user declined to confirm this action",
                ))
                yield AgentEvent(type="denied", tool=tc.name, content="user declined")
                return

        # pre_tool_use hooks — may block execution
        hooks_cfg = getattr(self.settings, "hooks", None)
        if hooks_cfg and hooks_cfg.pre_tool_use:
            pre_results = await run_hooks(
                hooks_cfg.pre_tool_use,
                {"tool": tc.name, "args": tc.arguments, "session_id": self.session_id},
                tool_name=tc.name, blocking=True,
            )
            for hr in pre_results:
                if hr.blocked:
                    reason = (hr.stderr or hr.stdout or "blocked by pre_tool_use hook").strip()
                    await self._append(ChatMessage(
                        role="tool", tool_call_id=tc.id, name=tc.name,
                        content=f"BLOCKED by hook: {reason}",
                    ))
                    yield AgentEvent(type="denied", tool=tc.name, content=f"hook blocked: {reason}")
                    return

        result: ToolResult = await self.tools.dispatch(tc.name, tc.arguments, ctx)
        await self._append(ChatMessage(
            role="tool",
            tool_call_id=tc.id,
            name=tc.name,
            content=result.to_model_message(),
        ))
        yield AgentEvent(
            type="tool_result",
            tool=tc.name,
            success=result.success,
            content=_truncate(result.output if result.success else (result.error or "")),
        )

        # post_tool_use hooks — fire-and-forget
        if hooks_cfg and hooks_cfg.post_tool_use:
            await run_hooks(
                hooks_cfg.post_tool_use,
                {
                    "tool": tc.name,
                    "args": tc.arguments,
                    "success": result.success,
                    "output": result.output[:5000],  # truncate for hook performance
                },
                tool_name=tc.name,
            )


# Things that look like placeholders the model dropped in instead of a real value:
#   <process_id>  <your_id>  {{id}}  <YOUR_TOKEN>  <id_here>
_PLACEHOLDER_RE = re.compile(r"^(<[A-Za-z_][\w\s_]*>|\{\{[A-Za-z_][\w\s_]*\}\})$")
_PLACEHOLDER_WORDS = {"placeholder", "your_id", "your_value", "id_here", "your_token"}


def _placeholder_in_args(args: dict) -> str | None:
    """Return the first arg value that looks like a placeholder, or None."""
    for v in (args or {}).values():
        if isinstance(v, str):
            stripped = v.strip()
            if _PLACEHOLDER_RE.match(stripped):
                return stripped
            if stripped.lower() in _PLACEHOLDER_WORDS:
                return stripped
        elif isinstance(v, dict):
            found = _placeholder_in_args(v)
            if found:
                return found
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, (dict, list)):
                    found = _placeholder_in_args({"_": item})
                    if found:
                        return found
                elif isinstance(item, str) and _PLACEHOLDER_RE.match(item.strip()):
                    return item.strip()
    return None


def _signature(calls) -> str | None:
    """Stable hash of a set of tool calls — used by the loop guard."""
    if not calls:
        return None
    payload = sorted(
        (tc.name, json.dumps(tc.arguments or {}, sort_keys=True, ensure_ascii=False))
        for tc in calls
    )
    return hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def _short(args: dict, limit: int = 120) -> str:
    s = ", ".join(f"{k}={_short_val(v)}" for k, v in (args or {}).items())
    return s if len(s) <= limit else s[:limit] + "..."


def _short_val(v) -> str:
    s = str(v)
    return s if len(s) <= 60 else s[:60] + "..."


def _truncate(s: str, limit: int = 600) -> str:
    return s if len(s) <= limit else s[:limit] + f"\n... (+{len(s) - limit} chars)"
