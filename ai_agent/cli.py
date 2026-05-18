"""CLI entry point — `ai-agent` command with chat/run/models/doctor/serve."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Force UTF-8 on stdout/stderr so Rich glyphs (arrows, check marks) survive on
# Windows consoles that still default to cp1252.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table

from .config import load_settings
from .core.agent import Agent, AgentEvent
from .core.prompts import INIT_PROMPT
from .memory.store import MemoryStore
from .models.router import build_router
from .safety.validator import SafetyDecision, Validator
from .tools.registry import build_default_registry
from .utils.logging import configure_logging
from .utils.ui import render_banner

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Local autonomous AI agent.")
console = Console(legacy_windows=False)

mcp_app = typer.Typer(no_args_is_help=True, help="MCP (Model Context Protocol) servers.")
app.add_typer(mcp_app, name="mcp")

profile_app = typer.Typer(no_args_is_help=True, help="Model provider profiles (API keys, base URLs).")
app.add_typer(profile_app, name="profile")

skills_app = typer.Typer(no_args_is_help=True, help="Programming knowledge packs auto-loaded by stack.")
app.add_typer(skills_app, name="skills")

memory_app = typer.Typer(no_args_is_help=True, help="Project memory facts.")
app.add_typer(memory_app, name="memory")


def _bootstrap(workspace: str | None, permission: str | None, provider: str | None, model: str | None):
    settings = load_settings()
    if workspace:
        settings.workspace = Path(workspace).resolve()
    if permission:
        settings.safety.permission_level = permission  # type: ignore[assignment]
    if provider:
        settings.model.provider = provider  # type: ignore[assignment]
    if model:
        if settings.model.provider == "ollama":
            settings.model.ollama.model = model
        else:
            settings.model.openai_compat.model = model

    configure_logging(settings.logging.level, settings.logging.dir, settings.logging.json_output)
    return settings


async def _preflight_check_model(router, settings) -> None:
    """Warn (without crashing) if the configured model isn't visible to the provider."""
    want = _active_model(settings)
    try:
        available = await router.provider.list_models()
    except Exception as e:
        console.print(f"[yellow]could not reach provider:[/yellow] {e}")
        return
    if not available:
        console.print("[yellow]provider returned no models — is Ollama running?[/yellow]")
        return
    # Ollama implicitly appends :latest when no tag is given, so "gemma4" should
    # match "gemma4:latest". Build the set of names this request could resolve to.
    want_candidates = {want, f"{want}:latest"} if ":" not in want else {want}
    if not want_candidates.intersection(available):
        suggestions = "\n  ".join(f"/model {m}" for m in available[:5])
        console.print(Panel.fit(
            f"[yellow]Model[/yellow] [bold]{want}[/bold] [yellow]is not installed.[/yellow]\n\n"
            f"Install it:\n  [cyan]ollama pull {want}[/cyan]\n\n"
            f"or switch to one you already have:\n  [cyan]{suggestions}[/cyan]",
            border_style="yellow",
        ))


async def _make_agent(settings, session_id: str | None = None) -> Agent:
    router = build_router(settings.model)
    await _preflight_check_model(router, settings)
    tools = build_default_registry()
    memory = MemoryStore(settings.memory.db_path)
    await memory.init()
    validator = Validator(settings.safety)

    async def confirm_handler(name: str, args: dict, dec: SafetyDecision) -> bool:
        console.print(Panel.fit(
            f"[yellow]Confirm tool call:[/yellow] [bold]{name}[/bold]\n"
            f"args: {args}\n[dim]{dec.reason}[/dim]",
            border_style="yellow",
        ))
        return Confirm.ask("Allow this action?", default=False, console=console)

    agent = Agent(settings, router, tools, memory, validator,
                  session_id=session_id, confirm=confirm_handler)
    await agent.init()
    return agent


SLASH_HELP = """\
[bold]Slash commands[/bold]
  /help            show this help
  /clear           start a fresh session (keeps the agent running)
  /tools           list registered tools
  /sessions        list recent sessions
  /resume <id>     load a previous session
  /model <id>      switch model at runtime
  /plan            enter plan mode (read-only, requires you to approve a plan)
  /init            ask the agent to write CLAUDE.md for this repo
  /compact         force-summarise old history to free context window
  /stats           show in-memory message count and model
  /todos           show the current todo list
  /ps              list background processes
  /profile         list provider profiles; /profile use <name> to switch
  /exit            quit
"""


async def _handle_slash(line: str, agent: Agent, settings) -> tuple[bool, Agent]:
    """Return (should_continue_repl, possibly_new_agent)."""
    parts = line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in {"/exit", "/quit", "/q"}:
        return False, agent
    if cmd == "/help":
        console.print(Panel(SLASH_HELP, border_style="blue"))
        return True, agent
    if cmd == "/tools":
        t = Table(title="Tools")
        t.add_column("name", style="cyan")
        t.add_column("description")
        for tool in agent.tools.all():
            t.add_row(tool.name, tool.description)
        console.print(t)
        return True, agent
    if cmd == "/sessions":
        ws = str(settings.workspace.resolve())
        rows = await agent.memory.list_sessions(ws, limit=20)
        t = Table(title="Recent sessions")
        t.add_column("id")
        t.add_column("name")
        for r in rows:
            t.add_row(r["id"], r.get("name") or "")
        console.print(t)
        return True, agent
    if cmd == "/resume":
        if not arg:
            console.print("[yellow]usage: /resume <session_id>[/yellow]")
            return True, agent
        await agent.router.aclose()
        new_agent = await _make_agent(settings, session_id=arg)
        console.print(f"[green]resumed session[/green] {arg}")
        return True, new_agent
    if cmd == "/model":
        if not arg:
            console.print("[yellow]usage: /model <id>[/yellow]")
            return True, agent
        if settings.model.provider == "ollama":
            settings.model.ollama.model = arg
        else:
            settings.model.openai_compat.model = arg
        await agent.router.aclose()
        new_agent = await _make_agent(settings, session_id=agent.session_id)
        console.print(f"[green]model →[/green] {arg}")
        return True, new_agent
    if cmd == "/plan":
        agent.set_plan_mode(not agent.plan_mode)
        state = "ON" if agent.plan_mode else "OFF"
        color = "yellow" if agent.plan_mode else "green"
        console.print(f"[{color}]plan mode {state}[/{color}]")
        return True, agent
    if cmd == "/clear":
        await agent.router.aclose()
        new_agent = await _make_agent(settings)
        console.print(f"[green]new session[/green] {new_agent.session_id}")
        return True, new_agent
    if cmd == "/init":
        console.print("[cyan]asking the agent to write CLAUDE.md...[/cyan]")
        async for evt in agent.run(INIT_PROMPT):
            _render_event(evt)
        return True, agent
    if cmd == "/compact":
        console.print("[cyan]summarising older history...[/cyan]")
        collapsed = await agent.maybe_compact()
        if collapsed:
            console.print(f"[green]compacted[/green] {collapsed} messages "
                          f"(in-memory: {len(agent.messages)} now)")
        else:
            console.print("[dim]nothing to compact yet[/dim]")
        return True, agent
    if cmd == "/todos":
        items = await agent.memory.get_todos(agent.session_id)
        if not items:
            console.print("[dim]no todos yet[/dim]")
        else:
            glyphs = {"pending": "( )", "in_progress": "(~)", "completed": "(x)"}
            lines = "\n".join(f"  {glyphs.get(i['status'], '[?]')} {i['content']}" for i in items)
            console.print(Panel(lines, title="todos", border_style="yellow"))
        return True, agent
    if cmd == "/ps":
        procs = agent.processes.list_all()
        if not procs:
            console.print("[dim]no background processes[/dim]")
        else:
            import time as _t
            t = Table(title="background processes")
            t.add_column("id"); t.add_column("alive"); t.add_column("exit"); t.add_column("runtime"); t.add_column("command")
            now = _t.time()
            for bp in procs:
                t.add_row(bp.id, str(bp.alive), str(bp.exit_code), f"{now - bp.started_at:.1f}s", bp.command[:60])
            console.print(t)
        return True, agent
    if cmd == "/profile":
        from . import profiles as _p
        sub_parts = arg.split(maxsplit=1)
        sub_cmd = sub_parts[0] if sub_parts else "list"
        sub_arg = sub_parts[1] if len(sub_parts) > 1 else ""
        if sub_cmd == "use" and sub_arg:
            try:
                _p.activate(sub_arg)
            except KeyError as e:
                console.print(f"[red]{e}[/red]")
                return True, agent
            console.print(f"[green]●[/green] active profile: [cyan]{sub_arg}[/cyan]\n"
                          "[dim]restart the chat to apply: type [yellow]exit[/yellow] then [yellow]exara chat[/yellow][/dim]")
            return True, agent
        # default: list
        f = _p.load()
        if not f.profiles:
            console.print("[dim]no profiles. create one with[/dim] [cyan]exara profile add[/cyan]")
            return True, agent
        lines = []
        for name, p in f.profiles.items():
            marker = "[green]●[/green]" if name == f.active else " "
            lines.append(f"{marker} [cyan]{name}[/cyan]  [dim]{p.provider} · {p.model}[/dim]")
        lines.append("\n[dim]switch with[/dim]  [cyan]/profile use <name>[/cyan]")
        console.print(Panel.fit("\n".join(lines), title="profiles", border_style="cyan"))
        return True, agent
    if cmd == "/stats":
        ms = agent.messages
        by_role: dict[str, int] = {}
        for m in ms:
            by_role[m.role] = by_role.get(m.role, 0) + 1
        console.print(Panel.fit(
            f"messages in context: [bold]{len(ms)}[/bold]\n"
            f"by role: {by_role}\n"
            f"model: {_active_model(settings)}  "
            f"provider: {settings.model.provider}\n"
            f"plan_mode: {agent.plan_mode}",
            title="stats",
        ))
        return True, agent

    console.print(f"[red]unknown command:[/red] {cmd}  ([dim]/help[/dim])")
    return True, agent


def _format_tool_args(args: dict | None, limit: int = 90) -> str:
    """Compact, readable arg summary for a tool call header."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        if isinstance(v, str):
            sv = v if len(v) <= 50 else v[:47] + "…"
            parts.append(f'{k}="{sv}"')
        elif isinstance(v, (list, tuple)):
            parts.append(f"{k}=[{len(v)} items]")
        elif isinstance(v, dict):
            parts.append(f"{k}={{…}}")
        else:
            parts.append(f"{k}={v}")
    s = ", ".join(parts)
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _render_event(evt: AgentEvent) -> None:
    if evt.type == "step":
        # Subtle step marker — no rule, just a thin dim line
        console.print(f"  [dim]· step {evt.step}[/dim]")

    elif evt.type == "tool_call":
        tool_name = evt.tool or "?"
        args_str = _format_tool_args(evt.args)
        head = f"[cyan]⏺[/cyan] [bold cyan]{tool_name}[/bold cyan]"
        if args_str:
            head += f"  [dim]{args_str}[/dim]"
        console.print(head)

    elif evt.type == "tool_result":
        body = (evt.content or "").rstrip()
        # Special render for todo updates — show the current list in a yellow panel.
        if evt.tool in ("todo_write", "todo_read") and evt.success and body:
            console.print(Panel(body, title=f"todos · {evt.tool}", border_style="yellow", padding=(0, 1)))
            return
        if not body:
            arrow = "[green]↳[/green]" if evt.success else "[red]↳[/red]"
            console.print(f"  {arrow} [dim]ok[/dim]" if evt.success else f"  {arrow} [red]failed[/red]")
            return

        # Multiline → indented preview block; single-line → inline
        if "\n" in body or len(body) > 90:
            arrow_color = "green" if evt.success else "red"
            console.print(f"  [{arrow_color}]↳[/{arrow_color}]")
            # cap at 24 lines so a giant output doesn't drown the chat
            lines = body.splitlines()
            if len(lines) > 24:
                body = "\n".join(lines[:24]) + f"\n… (+{len(lines) - 24} more lines)"
            console.print(_indent(body, "    "), highlight=False, style="dim")
        else:
            arrow = "[green]↳[/green]" if evt.success else "[red]↳[/red]"
            console.print(f"  {arrow} [dim]{body}[/dim]")

    elif evt.type == "denied":
        console.print(f"  [yellow]✗[/yellow] [yellow]denied[/yellow] [dim]{evt.tool}: {evt.content}[/dim]")

    elif evt.type == "final":
        console.print()
        console.print(Panel(evt.content, border_style="green", padding=(0, 1)))

    elif evt.type == "error":
        console.print(Panel(evt.content, title="error", border_style="red", padding=(0, 1)))

    elif evt.type == "preview":
        console.print(Panel(
            Syntax(evt.content, "diff", theme="ansi_dark", word_wrap=False),
            title=f"diff · {evt.tool}", border_style="cyan", padding=(0, 1),
        ))

    elif evt.type == "plan_submitted":
        console.print(Panel(evt.content, title="plan", border_style="yellow", padding=(0, 1)))

    elif evt.type == "content_delta":
        console.print(evt.content, end="", soft_wrap=True, highlight=False)


# --- commands ----------------------------------------------------------------

@app.command()
def chat(
    workspace: str | None = typer.Option(None, "-w", "--workspace", help="Workspace path"),
    permission: str | None = typer.Option(None, "-p", "--permission", help="safe|normal|full"),
    provider: str | None = typer.Option(None, help="ollama|openai_compat"),
    model: str | None = typer.Option(None, help="Model id"),
    session: str | None = typer.Option(None, "-s", "--session", help="Resume an existing session id"),
) -> None:
    """Interactive REPL."""
    settings = _bootstrap(workspace, permission, provider, model)

    async def main() -> None:
        agent = await _make_agent(settings, session_id=session)
        if settings.ui.banner:
            render_banner(
                console,
                settings.ui.name,
                settings.ui.tagline,
                font=settings.ui.banner_font,
                color=settings.ui.banner_color,
            )

        # Lines for the status panel
        lines = [
            f"workspace [cyan]{settings.workspace}[/cyan]",
            f"provider  [cyan]{settings.model.provider}[/cyan]    "
            f"model [cyan]{_active_model(settings)}[/cyan]",
            f"perm      [yellow]{settings.safety.permission_level}[/yellow]    "
            f"session [dim]{agent.session_id[:12]}…[/dim]",
        ]
        # If MCP servers loaded, summarise them on a line
        mcp_clients = getattr(agent.mcp, "clients", {})
        if mcp_clients:
            mcp_names = ", ".join(f"[green]{n}[/green]" for n in mcp_clients)
            n_tools = len(agent.mcp.tools)
            lines.append(f"mcp       {mcp_names}  [dim]({n_tools} tools total)[/dim]")
        lines.append("[dim]/help for commands · type 'exit' to quit[/dim]")
        console.print(Panel.fit("\n".join(lines), border_style="cyan", padding=(0, 1)))
        try:
            while True:
                try:
                    suffix = " [yellow](plan)[/yellow]" if agent.plan_mode else ""
                    line = Prompt.ask(f"[bold green]you[/bold green]{suffix}")
                except (EOFError, KeyboardInterrupt):
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.lower() in {"exit", "quit", ":q"}:
                    break
                if stripped.startswith("/"):
                    keep, agent = await _handle_slash(stripped, agent, settings)
                    if not keep:
                        break
                    continue

                plan_submitted_text: str | None = None
                streamed_any = False
                thinking = None
                if settings.ui.spinner:
                    thinking = console.status("[dim]thinking…[/dim]", spinner="dots")
                    thinking.start()

                def stop_thinking():
                    nonlocal thinking
                    if thinking is not None:
                        thinking.stop()
                        thinking = None

                try:
                    async for evt in agent.run(stripped):
                        # First sign of model activity → kill the spinner
                        if evt.type in ("content_delta", "tool_call", "step"):
                            stop_thinking()
                        if evt.type == "content_delta":
                            streamed_any = True
                            _render_event(evt)
                            continue
                        if evt.type == "step" and streamed_any:
                            console.print()
                            streamed_any = False
                        if evt.type == "final" and streamed_any:
                            console.print()
                            streamed_any = False
                            continue
                        _render_event(evt)
                        if evt.type == "plan_submitted":
                            plan_submitted_text = evt.content
                finally:
                    stop_thinking()

                # If the model asked to leave plan mode, ask the user.
                if plan_submitted_text and agent.plan_mode:
                    if Confirm.ask("Approve plan and exit plan mode?", default=True, console=console):
                        agent.set_plan_mode(False)
                        console.print("[green]plan approved · plan mode OFF[/green] — "
                                      "send your next message to start executing.")
                    else:
                        console.print("[yellow]plan rejected · still in plan mode[/yellow]")
        finally:
            # Close MCP subprocesses + background tasks BEFORE the router.
            # Must run in the same task that started them — otherwise anyio's
            # cancel scope raises "exit from different task". Wrap in try/except
            # because a cleanup error here is not actionable; we just want the
            # exit to be quiet.
            try:
                await agent.shutdown()
            except Exception:
                pass
            try:
                await agent.router.aclose()
            except Exception:
                pass

    asyncio.run(main())


@app.command()
def run(
    prompt: str = typer.Argument(..., help="Single-shot task description"),
    workspace: str | None = typer.Option(None, "-w", "--workspace"),
    permission: str | None = typer.Option(None, "-p", "--permission"),
    provider: str | None = typer.Option(None),
    model: str | None = typer.Option(None),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm all gated actions"),
) -> None:
    """Run a single task non-interactively."""
    settings = _bootstrap(workspace, permission, provider, model)
    if yes:
        settings.safety.require_confirmation = False

    async def main() -> None:
        agent = await _make_agent(settings)
        try:
            streamed_any = False
            async for evt in agent.run(prompt):
                if evt.type == "content_delta":
                    streamed_any = True
                    _render_event(evt)
                    continue
                if evt.type == "step" and streamed_any:
                    console.print()
                    streamed_any = False
                if evt.type == "final" and streamed_any:
                    console.print()
                    streamed_any = False
                    continue
                _render_event(evt)
        finally:
            # Close MCP subprocesses + background tasks BEFORE the router.
            # Must run in the same task that started them — otherwise anyio's
            # cancel scope raises "exit from different task". Wrap in try/except
            # because a cleanup error here is not actionable; we just want the
            # exit to be quiet.
            try:
                await agent.shutdown()
            except Exception:
                pass
            try:
                await agent.router.aclose()
            except Exception:
                pass

    asyncio.run(main())


@app.command()
def models(
    provider: str | None = typer.Option(None, help="Override provider for the check"),
) -> None:
    """List models available from the configured provider."""
    settings = _bootstrap(None, None, provider, None)

    async def main() -> None:
        router = build_router(settings.model)
        try:
            models = await router.provider.list_models()
        finally:
            await router.aclose()
        t = Table(title=f"Models — {settings.model.provider}")
        t.add_column("name")
        for m in models or ["(none — provider unreachable?)"]:
            t.add_row(m)
        console.print(t)

    asyncio.run(main())


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Create safe missing local dirs/config files."),
) -> None:
    """Quick environment + connectivity check. Use --fix for safe local setup."""
    settings = _bootstrap(None, None, None, None)

    async def main() -> None:
        import json as _json
        import shutil

        from . import profiles as _profiles
        from .mcp.config import load_merged_mcp_config

        checks: list[tuple[str, str, str]] = []

        def row(name: str, ok: bool, detail: str) -> None:
            status = "[green]ok[/green]" if ok else "[yellow]check[/yellow]"
            checks.append((name, status, detail))

        def ensure_dir(name: str, path: Path) -> None:
            if path.is_dir():
                row(name, True, str(path))
                return
            if fix:
                path.mkdir(parents=True, exist_ok=True)
                row(name, True, f"created {path}")
                return
            row(name, False, f"missing {path} (run exara doctor --fix)")

        user_dir = Path.home() / ".ai-agent"
        ensure_dir("user config dir", user_dir)
        ensure_dir("user skills dir", user_dir / "skills")
        ensure_dir("memory db dir", Path(settings.memory.db_path).parent)
        ensure_dir("logs dir", Path(settings.logging.dir))

        user_mcp = user_dir / "mcp.json"
        if user_mcp.is_file():
            row("global MCP config", True, str(user_mcp))
        elif fix:
            user_mcp.parent.mkdir(parents=True, exist_ok=True)
            user_mcp.write_text(_json.dumps({"mcpServers": {}}, indent=2), encoding="utf-8")
            row("global MCP config", True, f"created {user_mcp}")
        else:
            row("global MCP config", False, f"missing {user_mcp} (optional)")

        profile_file = _profiles.default_path()
        profiles_file = _profiles.load()
        if profiles_file.active and profiles_file.active in profiles_file.profiles:
            p = profiles_file.profiles[profiles_file.active]
            row("active profile", True, f"{profiles_file.active} / {p.provider} / {p.model}")
        elif profiles_file.profiles:
            row("active profile", False, "profiles exist, but none active; run exara profile use <name>")
        else:
            row("active profile", False, f"none in {profile_file}; run exara init")

        for launcher in ("npx", "uvx", "docker", "ollama"):
            found = shutil.which(launcher)
            row(f"launcher: {launcher}", found is not None, found or "not on PATH")

        router = build_router(settings.model)
        try:
            models = await router.provider.list_models()
            row("provider", bool(models), f"{settings.model.provider}: {len(models)} model(s)")
        except Exception as e:
            row("provider", False, f"{settings.model.provider}: {e}")
        finally:
            await router.aclose()

        store = MemoryStore(settings.memory.db_path)
        await store.init()
        row("memory store", True, str(settings.memory.db_path))

        tools = build_default_registry()
        row("built-in tools", True, f"{len(tools.all())} loaded")

        mcp_path = Path(settings.mcp.config_path)
        if not mcp_path.is_absolute():
            mcp_path = settings.workspace / mcp_path
        servers = load_merged_mcp_config(mcp_path)
        row("mcp servers", True, f"{len(servers)} visible")

        console.print(Panel.fit(
            f"workspace = {settings.workspace}\n"
            f"db        = {settings.memory.db_path}\n"
            f"provider  = {settings.model.provider}\n"
            f"model     = {_active_model(settings)}\n"
            f"perm      = {settings.safety.permission_level}",
            title="config",
        ))
        table = Table(title="doctor")
        table.add_column("check", style="cyan")
        table.add_column("status")
        table.add_column("detail", style="dim")
        for item in checks:
            table.add_row(*item)
        console.print(table)

    asyncio.run(main())


@app.command()
def init(
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing files (mcp.json, starter skill)."),
    skip_provider: bool = typer.Option(False, "--skip-provider", help="Don't prompt for a new provider profile."),
) -> int:
    """Interactive setup wizard.

    First-run users should run this once. Creates `~/.ai-agent/` with a profile,
    mcp.json, and a starter skill. Re-runnable: never overwrites files unless
    `--force` is passed.
    """
    from . import init_wizard
    return init_wizard.run(console, force=force, skip_provider=skip_provider)


@app.command()
def tools() -> None:
    """List registered tools."""
    reg = build_default_registry()
    t = Table(title="Tools")
    t.add_column("name", style="cyan")
    t.add_column("description")
    for tool in reg.all():
        t.add_row(tool.name, tool.description)
    console.print(t)


@app.command()
def serve(
    host: str | None = typer.Option(None),
    port: int | None = typer.Option(None),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the FastAPI server."""
    import uvicorn
    settings = _bootstrap(None, None, None, None)
    h = host or settings.api.host
    p = port or settings.api.port
    console.print(f"[bold]serving[/bold] http://{h}:{p}")
    uvicorn.run("ai_agent.api.server:app", host=h, port=p, reload=reload, log_level=settings.logging.level.lower())


def _active_model(settings) -> str:
    return (settings.model.ollama.model if settings.model.provider == "ollama"
            else settings.model.openai_compat.model)


def _memory_workspace(settings, workspace: str | None) -> str:
    return str((Path(workspace).resolve() if workspace else settings.workspace.resolve()))


def _shorten_cell(value: object, limit: int = 90) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _format_timestamp(ts: float | int | str | None) -> str:
    if ts is None:
        return ""
    import time as _time

    try:
        return _time.strftime("%Y-%m-%d %H:%M", _time.localtime(float(ts)))
    except (TypeError, ValueError):
        return str(ts)


def _render_memory_rows(rows: list[dict], *, include_workspace: bool, title: str) -> None:
    if not rows:
        console.print("[dim]no memory facts found[/dim]")
        return
    table = Table(title=title)
    if include_workspace:
        table.add_column("workspace", style="dim")
    table.add_column("key", style="cyan")
    table.add_column("value")
    table.add_column("updated", style="dim")
    for r in rows:
        cells = []
        if include_workspace:
            cells.append(_shorten_cell(r.get("workspace", ""), 46))
        cells.extend([
            _shorten_cell(r.get("key", ""), 36),
            _shorten_cell(r.get("value", ""), 90),
            _format_timestamp(r.get("updated_at")),
        ])
        table.add_row(*cells)
    console.print(table)


@memory_app.command("list")
def memory_list(
    all_: bool = typer.Option(False, "--all", help="Show memory facts from every workspace."),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace path (default: current)."),
) -> None:
    """List project memory facts."""
    settings = _bootstrap(workspace, None, None, None)
    ws = None if all_ else _memory_workspace(settings, workspace)

    async def main() -> None:
        store = MemoryStore(settings.memory.db_path)
        await store.init()
        rows = await store.list_facts(ws)
        _render_memory_rows(rows, include_workspace=all_, title="memory facts")

    asyncio.run(main())


@memory_app.command("set")
def memory_set(
    key: str = typer.Argument(..., help="Fact key."),
    value: str = typer.Argument(..., help="Fact value."),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace path (default: current)."),
) -> None:
    """Create or update a project memory fact."""
    settings = _bootstrap(workspace, None, None, None)
    ws = _memory_workspace(settings, workspace)

    async def main() -> None:
        store = MemoryStore(settings.memory.db_path)
        await store.init()
        await store.set_fact(ws, key, value)
        console.print(f"[green]saved[/green] [cyan]{key}[/cyan] for [dim]{ws}[/dim]")

    asyncio.run(main())


@memory_app.command("search")
def memory_search(
    query: str = typer.Argument(..., help="Case-insensitive text to search."),
    all_: bool = typer.Option(False, "--all", help="Search every workspace."),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace path (default: current)."),
) -> None:
    """Search memory facts by workspace, key, or value."""
    settings = _bootstrap(workspace, None, None, None)
    ws = None if all_ else _memory_workspace(settings, workspace)

    async def main() -> None:
        store = MemoryStore(settings.memory.db_path)
        await store.init()
        rows = await store.search_facts(query, ws)
        _render_memory_rows(rows, include_workspace=all_, title=f"memory search: {query}")

    asyncio.run(main())


@memory_app.command("forget")
def memory_forget(
    key: str = typer.Argument(..., help="Fact key to delete."),
    workspace: str | None = typer.Option(None, "--workspace", "-w", help="Workspace path (default: current)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Delete without interactive confirmation."),
) -> None:
    """Delete one memory fact from a workspace."""
    settings = _bootstrap(workspace, None, None, None)
    ws = _memory_workspace(settings, workspace)
    if not yes and not Confirm.ask(
        f"Forget memory fact [cyan]{key}[/cyan] for [dim]{ws}[/dim]?",
        default=False,
        console=console,
    ):
        console.print("[dim]cancelled[/dim]")
        return

    async def main() -> None:
        store = MemoryStore(settings.memory.db_path)
        await store.init()
        deleted = await store.delete_fact(ws, key)
        if deleted:
            console.print(f"[green]forgot[/green] [cyan]{key}[/cyan]")
        else:
            console.print(f"[yellow]not found:[/yellow] {key}")

    asyncio.run(main())


# --- MCP subcommands --------------------------------------------------------

@mcp_app.command("list")
def mcp_list(
    config: str | None = typer.Option(None, "--config", "-c", help="Path to mcp.json"),
) -> None:
    """Show configured MCP servers and the tools each one exposes."""
    settings = _bootstrap(None, None, None, None)
    if config:
        settings.mcp.config_path = config

    from pathlib import Path
    from .mcp.config import load_merged_mcp_config
    from .mcp.manager import MCPManager

    path = Path(settings.mcp.config_path)
    if not path.is_absolute():
        path = settings.workspace / path
    user_path = Path.home() / ".ai-agent" / "mcp.json"

    servers = load_merged_mcp_config(path)
    if not servers:
        console.print(Panel.fit(
            f"No MCP servers found.\n\n"
            f"Looked in:\n"
            f"  workspace [cyan]{path}[/cyan]\n"
            f"  user     [cyan]{user_path}[/cyan]\n\n"
            "Create one with the Claude Desktop / Cursor format:\n"
            '[dim]{ "mcpServers": { "filesystem": { "command": "npx", "args": ["-y", '
            '"@modelcontextprotocol/server-filesystem", "/some/path"] } } }[/dim]',
            border_style="yellow", title="mcp",
        ))
        return

    console.print(
        f"[dim]sources:[/dim] workspace [cyan]{path}[/cyan]"
        + (f"  ·  user [cyan]{user_path}[/cyan]" if user_path.is_file() else "")
        + "\n"
    )

    async def main() -> None:
        mgr = MCPManager()
        status = await mgr.start_all(servers)
        try:
            for name, st in status.items():
                color = "green" if st.startswith("ok") else "red"
                console.print(f"[{color}]●[/{color}] [bold]{name}[/bold]  {st}")
                for meta in mgr.list_tools():
                    if meta.server == name:
                        console.print(
                            f"    [cyan]{meta.tool}[/cyan]  "
                            f"[dim]{(meta.description or '').splitlines()[0][:80]}[/dim]"
                        )
        finally:
            await mgr.shutdown_all()

    asyncio.run(main())


@mcp_app.command("catalog")
def mcp_catalog() -> None:
    """List curated MCP servers you can install with one command."""
    from .mcp.config import CATALOG
    t = Table(title="MCP catalogue")
    t.add_column("name", style="cyan")
    t.add_column("launcher")
    t.add_column("requires")
    t.add_column("description", style="dim")
    for name, entry in CATALOG.items():
        req = ", ".join(entry.env_required) if entry.env_required else "-"
        t.add_row(name, entry.command, req, entry.description)
    console.print(t)
    console.print("\n[dim]Install globally with:[/dim]  [cyan]exara mcp install <name> --global[/cyan]")


@mcp_app.command("install")
def mcp_install(
    name: str = typer.Argument(..., help="Server name from the catalogue"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to mcp.json (defaults depend on --global)"),
    global_: bool = typer.Option(False, "--global", "-g", help="Install to ~/.ai-agent/mcp.json so it's available from any folder"),
    disabled: bool = typer.Option(False, "--disabled", help="Add as disabled (won't auto-load)"),
) -> None:
    """Add a server from the curated catalogue. Use --global to install once
    and have it available from any cwd; otherwise it's project-specific.
    """
    import shutil
    from .mcp.config import CATALOG, MCPServerConfig, add_server_to_config
    settings = _bootstrap(None, None, None, None)
    if config:
        path = Path(config)
    elif global_:
        path = Path.home() / ".ai-agent" / "mcp.json"
    else:
        path = settings.workspace / settings.mcp.config_path

    entry = CATALOG.get(name)
    if entry is None:
        console.print(f"[red]unknown server:[/red] {name}. Run [cyan]exara mcp catalog[/cyan].")
        raise typer.Exit(2)

    # 1. Verify the launcher (npx / uvx / docker / etc.) is installed
    cmd_path = shutil.which(entry.command)
    if cmd_path is None:
        hint = ""
        if entry.command == "uvx":
            hint = ("\n[yellow]Install uv (Python project manager):[/yellow]\n"
                    "  Windows: [cyan]powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"[/cyan]\n"
                    "  macOS/Linux: [cyan]curl -LsSf https://astral.sh/uv/install.sh | sh[/cyan]")
        elif entry.command == "npx":
            hint = ("\n[yellow]Install Node.js (includes npx):[/yellow]\n"
                    "  https://nodejs.org/")
        console.print(Panel.fit(
            f"[red]The launcher [bold]{entry.command}[/bold] is not on your PATH.[/red]\n"
            f"This MCP server needs it to run.{hint}\n\n"
            f"[dim]You can still install it as disabled:[/dim]\n"
            f"  [cyan]exara mcp install {name} --disabled[/cyan]",
            border_style="red", title="missing dependency",
        ))
        if not disabled:
            raise typer.Exit(2)

    # 2. Resolve {PLACEHOLDERS} in args. Use rich prompts with descriptions.
    args = []
    for a in entry.args:
        if a.startswith("{") and a.endswith("}"):
            placeholder = a[1:-1]
            label, hint = entry.arg_prompts.get(placeholder, (placeholder, ""))
            default = ""
            if placeholder == "PATH":
                default = str(settings.workspace)
            if hint:
                console.print(f"[dim]{hint}[/dim]")
            value = Prompt.ask(f"[cyan]{label}[/cyan]", default=default).strip()
            # Defensive: if the user accepted an empty value for a required slot,
            # bail rather than silently storing nonsense.
            if not value:
                console.print(f"[red]{label} is required and was empty.[/red] Aborting.")
                raise typer.Exit(2)
            args.append(value)
        else:
            args.append(a)

    # 3. Prompt for required env vars (masked, in case they're tokens)
    env: dict[str, str] = {}
    for var in entry.env_required:
        value = Prompt.ask(f"[cyan]{var}[/cyan] [dim](hidden)[/dim]", password=True).strip()
        if not value:
            console.print(f"[red]{var} is required and was empty.[/red] Aborting.")
            raise typer.Exit(2)
        env[var] = value

    cfg = MCPServerConfig(command=entry.command, args=args, env=env, disabled=disabled)
    add_server_to_config(path, name, cfg)
    status = "[yellow]●[/yellow] installed (disabled)" if disabled else "[green]●[/green] installed"
    console.print(f"{status} [cyan]{name}[/cyan] -> {path}")
    if entry.docs:
        console.print(f"[dim]docs: {entry.docs}[/dim]")
    console.print(f"\n[dim]Test it:[/dim]  [cyan]exara mcp list[/cyan]")


@mcp_app.command("test")
def mcp_test(
    server: str = typer.Argument(..., help="Server name from mcp.json"),
    tool: str = typer.Argument(..., help="Tool name (unqualified)"),
    args_json: str = typer.Option("{}", "--args", help="JSON object with tool arguments"),
) -> None:
    """Invoke a single MCP tool to verify the server works."""
    import json as _json
    from pathlib import Path
    from .mcp.config import load_merged_mcp_config
    from .mcp.manager import MCPManager

    settings = _bootstrap(None, None, None, None)
    path = Path(settings.mcp.config_path)
    if not path.is_absolute():
        path = settings.workspace / path
    servers = load_merged_mcp_config(path)
    if server not in servers:
        console.print(f"[red]Unknown server[/red] {server!r}. Configured: {list(servers)}")
        raise typer.Exit(2)
    try:
        args = _json.loads(args_json)
    except _json.JSONDecodeError as e:
        console.print(f"[red]--args is not valid JSON:[/red] {e}")
        raise typer.Exit(2)

    async def main() -> None:
        mgr = MCPManager()
        await mgr.start_all({server: servers[server]})
        try:
            client = mgr.clients.get(server)
            if client is None:
                console.print(f"[red]Server {server!r} failed to start[/red]")
                return
            result = await client.call_tool(tool, args)
            icon = "[green]✓[/green]" if result["ok"] else "[red]✗[/red]"
            console.print(f"{icon} {server}.{tool}")
            console.print(Panel(result["text"] or "(empty)", border_style="cyan"))
        finally:
            await mgr.shutdown_all()

    asyncio.run(main())


# --- Profile subcommands ---------------------------------------------------

@profile_app.command("list")
def profile_list() -> None:
    """Show configured profiles. Marks the active one with ●."""
    from . import profiles as _p
    f = _p.load()
    if not f.profiles:
        console.print(Panel.fit(
            "No profiles yet.\n\n"
            "Create one with:\n  [cyan]exara profile add[/cyan]\n\n"
            "Or pick from presets:\n  [cyan]exara profile presets[/cyan]",
            border_style="yellow", title="profiles",
        ))
        return
    t = Table(title=f"profiles  [dim](stored in {_p.default_path()})[/dim]")
    t.add_column("", width=2)
    t.add_column("name", style="cyan")
    t.add_column("provider")
    t.add_column("model")
    t.add_column("base_url", style="dim")
    for name, p in f.profiles.items():
        marker = "[green]●[/green]" if name == f.active else " "
        t.add_row(marker, name, p.provider, p.model, p.base_url)
    console.print(t)


@profile_app.command("presets")
def profile_presets() -> None:
    """Show built-in preset templates you can quickly add."""
    from . import profiles as _p
    t = Table(title="presets")
    t.add_column("name", style="cyan")
    t.add_column("provider")
    t.add_column("default model")
    t.add_column("notes", style="dim")
    for name, info in _p.PRESETS.items():
        t.add_row(name, info["provider"], info["model"], info["hint"])
    console.print(t)
    console.print("\n[dim]Add one with:[/dim]  [cyan]exara profile add --from <preset>[/cyan]")


@profile_app.command("add")
def profile_add(
    name: str | None = typer.Argument(None, help="Profile name (e.g. 'openai', 'work-openrouter')"),
    from_preset: str | None = typer.Option(None, "--from", help="Start from a preset (see `profile presets`)"),
    use: bool = typer.Option(False, "--use", help="Also activate this profile after creating"),
) -> None:
    """Add or update a profile. Interactive if --from is not used."""
    from . import profiles as _p
    if name is None:
        name = Prompt.ask("[cyan]profile name[/cyan]").strip()
        if not name:
            console.print("[red]name required[/red]")
            raise typer.Exit(2)

    if from_preset is not None:
        if from_preset not in _p.PRESETS:
            console.print(f"[red]unknown preset[/red] {from_preset!r}. Run [cyan]exara profile presets[/cyan].")
            raise typer.Exit(2)
        preset = _p.PRESETS[from_preset]
        provider = preset["provider"]
        base_url = preset["base_url"]
        model = preset["model"]
        extra_headers = preset.get("extra_headers", {})
        api_key = ""
        if provider != "ollama":
            api_key = Prompt.ask(f"[cyan]API key for {from_preset}[/cyan]", password=True).strip()
    else:
        provider = Prompt.ask("provider", choices=["openai_compat", "ollama"], default="openai_compat")
        default_base = "http://localhost:11434" if provider == "ollama" else "https://openrouter.ai/api/v1"
        base_url = Prompt.ask("base URL", default=default_base).strip()
        api_key = ""
        if provider != "ollama":
            api_key = Prompt.ask("API key", password=True).strip()
        model = Prompt.ask("default model").strip()
        extra_headers = {}

    profile = _p.Profile(
        provider=provider,
        base_url=base_url,
        api_key=api_key or None,
        model=model,
        extra_headers=extra_headers,
    )
    _p.upsert(name, profile, activate=use)
    icon = "[green]●[/green]" if use else " "
    console.print(f"{icon} saved profile [cyan]{name}[/cyan]  ([dim]{provider} / {model}[/dim])")
    if not use:
        console.print(f"[dim]Activate with:[/dim]  [cyan]exara profile use {name}[/cyan]")


@profile_app.command("use")
def profile_use(name: str) -> None:
    """Switch the active profile."""
    from . import profiles as _p
    try:
        _p.activate(name)
    except KeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(2)
    console.print(f"[green]●[/green] active profile: [cyan]{name}[/cyan]")


@profile_app.command("remove")
def profile_remove(name: str) -> None:
    """Delete a profile."""
    from . import profiles as _p
    _p.remove(name)
    console.print(f"[dim]removed[/dim] {name}")


@profile_app.command("show")
def profile_show(name: str | None = typer.Argument(None, help="Profile name (default: active)")) -> None:
    """Print a profile's details. API key is masked unless --reveal is set."""
    from . import profiles as _p
    f = _p.load()
    if name is None:
        if f.active is None:
            console.print("[yellow]no active profile[/yellow]")
            return
        name = f.active
    p = f.profiles.get(name)
    if p is None:
        console.print(f"[red]no such profile:[/red] {name}")
        raise typer.Exit(2)
    masked = (p.api_key[:4] + "…" + p.api_key[-4:]) if (p.api_key and len(p.api_key) > 8) else "(none)"
    body = (
        f"provider     {p.provider}\n"
        f"base_url     {p.base_url}\n"
        f"model        {p.model}\n"
        f"api_key      {masked}\n"
    )
    if p.extra_headers:
        body += f"headers      {p.extra_headers}\n"
    console.print(Panel.fit(body, title=f"profile · {name}", border_style="cyan"))


# --- Skills subcommands ----------------------------------------------------

@skills_app.command("list")
def skills_list() -> None:
    """Show all skills found and which are currently active for this workspace.

    Skills are merged from THREE sources (later overrides earlier):
    bundled (with the pip package) < ~/.ai-agent/skills < ./skills.
    """
    from .skills import detect_stack, load_all_skills, select_active

    settings = _bootstrap(None, None, None, None)
    skills_dir = Path(settings.skills.dir)
    if not skills_dir.is_absolute():
        skills_dir = settings.workspace / skills_dir
    skills = load_all_skills(skills_dir)
    if not skills:
        console.print("[yellow]no skills found anywhere[/yellow]")
        return

    tags, files = detect_stack(settings.workspace)
    active = {s.name for s in select_active(skills, stack_tags=tags, files=files)}

    user_dir = Path.home() / ".ai-agent" / "skills"

    t = Table(title="skills")
    t.add_column("", width=2)
    t.add_column("name", style="cyan")
    t.add_column("description")
    t.add_column("trigger")
    t.add_column("source", style="dim")
    for s in sorted(skills, key=lambda x: x.name):
        marker = "[green]●[/green]" if s.name in active else " "
        tr = "always" if s.triggers.always else (
            ", ".join(s.triggers.dependencies) or
            ", ".join(s.triggers.files_present) or
            ("keyword: " + ", ".join(s.triggers.keywords[:3])) if s.triggers.keywords else "—"
        )
        if s.path is None:
            source = "bundled"
        elif user_dir in s.path.parents:
            source = "user"
        else:
            source = "workspace"
        t.add_row(marker, s.name, s.description, tr, source)
    console.print(t)
    console.print(f"\n[dim]Detected stack:[/dim] {', '.join(sorted(tags)) or '(none)'}")
    console.print(
        "[dim]Sources (later wins):[/dim] bundled  ·  "
        f"user [cyan]{user_dir}[/cyan]  ·  workspace [cyan]{skills_dir}[/cyan]"
    )


@skills_app.command("show")
def skills_show(name: str) -> None:
    """Print the body of a single skill."""
    from .skills import load_all_skills
    settings = _bootstrap(None, None, None, None)
    skills_dir = Path(settings.skills.dir)
    if not skills_dir.is_absolute():
        skills_dir = settings.workspace / skills_dir
    skills = load_all_skills(skills_dir)
    match = next((s for s in skills if s.name == name), None)
    if match is None:
        console.print(f"[red]no such skill:[/red] {name}")
        raise typer.Exit(2)
    console.print(Panel.fit(
        f"[cyan]{match.name}[/cyan] — {match.description}\n"
        f"[dim]source: {match.path or 'bundled'}[/dim]\n\n{match.body}",
        title=f"skill · {name}", border_style="cyan",
    ))


if __name__ == "__main__":
    app()
