"""First-run setup wizard.

Walks a fresh user through:

1. Picking a model provider (Ollama local / OpenRouter / OpenAI / etc.)
2. Entering the API key (validated with a live ping when feasible)
3. Selecting MCP servers to enable (filesystem, github, memory, …)
4. Dropping a starter skill they can edit later

All artifacts land in `~/.ai-agent/`. Re-runnable: it never overwrites
existing files unless `--force` is passed; otherwise it merges/extends.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from . import profiles as _p

USER_DIR = Path.home() / ".ai-agent"

# Presets shown in the picker. Order is presentation order.
_PROVIDER_CHOICES: list[tuple[str, str, str]] = [
    ("ollama-local", "Ollama (local, no API key)", "Run models on your machine. Requires `ollama serve` running."),
    ("openrouter", "OpenRouter (unified API)", "Claude, GPT, DeepSeek, free models — single key, single bill."),
    ("openai", "OpenAI", "Direct OpenAI API."),
    ("anthropic", "Anthropic (Claude)", "Direct Anthropic API via their OpenAI-compatible endpoint."),
    ("deepseek", "DeepSeek", "Cheap, strong coding models, direct from DeepSeek."),
    ("groq", "Groq (fast inference)", "Llama-3.3-70B at extreme throughput."),
    ("lm-studio", "LM Studio (local)", "LM Studio's OpenAI-compatible local server."),
    ("custom", "Custom (any OpenAI-compatible endpoint)", "vLLM, llama.cpp, your own gateway, etc."),
]

_MCP_CHOICES: list[tuple[str, str, str, dict[str, Any]]] = [
    (
        "filesystem",
        "Filesystem access (read/write inside a path)",
        "Lets the agent read/write files via MCP. Path defaults to your home directory.",
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "{PATH}"]},
    ),
    (
        "memory",
        "Persistent knowledge graph",
        "Long-term memory the agent can write to across conversations.",
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"]},
    ),
    (
        "sequential-thinking",
        "Sequential reasoning tool",
        "A 'think harder' tool — useful for hard planning, slows everything down on easy tasks.",
        {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]},
    ),
    (
        "github",
        "GitHub (PR / issue / repo access)",
        "Requires a GitHub personal access token. Asks for it interactively.",
        {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "{TOKEN}"},
        },
    ),
]

_STARTER_SKILL = """\
---
name: my-preferences
description: Personal preferences that apply across every project
triggers:
  always: true
---

## Style
- Be direct and concrete. No filler ("I hope…", "Maybe…").
- For long tasks, use todo_write so I can see progress.

## Safety
- Don't read .env, files in .gitignore, or anything outside the workspace
  without telling me first.
- Confirm before any destructive action (rm, drop table, git push --force).

## Context about me
- Edit this file at ~/.ai-agent/skills/my-preferences.md
- It is loaded into every chat as part of the system prompt.
"""


def run(console: Console, *, force: bool = False, skip_provider: bool = False) -> int:
    """Run the wizard. Returns the conventional exit code (0 = ok)."""
    console.print(
        Panel.fit(
            "[bold cyan]exara init[/bold cyan]  ·  set up your global agent config\n"
            f"All artifacts go into [dim]{USER_DIR}[/dim] (created if missing).",
            border_style="cyan",
        )
    )

    USER_DIR.mkdir(exist_ok=True)
    (USER_DIR / "skills").mkdir(exist_ok=True)

    if not skip_provider:
        _setup_provider(console, force=force)

    _setup_mcp(console, force=force)
    _setup_starter_skill(console, force=force)

    console.print()
    console.print(
        Panel.fit(
            "[bold green]Done.[/bold green]\n\n"
            "Try it now:\n"
            "  [cyan]exara doctor[/cyan]   — verify the provider is reachable\n"
            "  [cyan]exara chat[/cyan]     — interactive session\n"
            "  [cyan]exara serve[/cyan]    — start the web UI backend on :8765\n\n"
            f"Edit your preferences:  [dim]{USER_DIR / 'skills' / 'my-preferences.md'}[/dim]\n"
            f"Add MCP servers:        [dim]{USER_DIR / 'mcp.json'}[/dim]\n"
            f"Switch providers:       [cyan]exara profile use <name>[/cyan]",
            border_style="green",
        )
    )
    return 0


# --- provider ---------------------------------------------------------------

def _setup_provider(console: Console, *, force: bool) -> None:
    existing = _p.load()
    if existing.profiles and not force:
        console.print(
            f"[dim]Found existing profiles:[/dim] {', '.join(existing.profiles)}  "
            f"[dim](active: {existing.active or 'none'})[/dim]"
        )
        if not Confirm.ask("Add another provider?", default=False, console=console):
            return

    console.print("\n[bold]1. Pick a model provider[/bold]")
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    for idx, (_, label, hint) in enumerate(_PROVIDER_CHOICES, start=1):
        table.add_row(f"  {idx}.", f"{label}\n    [dim]{hint}[/dim]")
    console.print(table)
    n = IntPrompt.ask(
        "Provider", default=1, choices=[str(i) for i in range(1, len(_PROVIDER_CHOICES) + 1)],
        console=console,
    )
    preset_key, label, _ = _PROVIDER_CHOICES[n - 1]

    if preset_key == "custom":
        provider_kind = Prompt.ask("Type", choices=["openai_compat", "ollama"], default="openai_compat", console=console)
        base_url = Prompt.ask("Base URL", default="http://localhost:8000/v1", console=console).strip()
        model = Prompt.ask("Default model", console=console).strip()
        api_key = ""
        if provider_kind != "ollama":
            api_key = Prompt.ask("API key (blank if none)", password=True, default="", console=console).strip()
        profile_name = Prompt.ask("Save as profile name", default="custom", console=console).strip() or "custom"
        extra_headers: dict[str, str] = {}
    else:
        preset = _p.PRESETS[preset_key]
        provider_kind = preset["provider"]
        base_url = preset["base_url"]
        model = Prompt.ask(f"Default model for {label}", default=preset["model"], console=console).strip()
        api_key = ""
        if provider_kind != "ollama":
            console.print(f"[dim]Get a key:[/dim] {preset.get('hint', '')}")
            api_key = Prompt.ask("API key", password=True, console=console).strip()
            if not api_key:
                console.print("[yellow]No key entered — saving profile without one. You can add it later via `exara profile add`.[/yellow]")
        profile_name = Prompt.ask("Save as profile name", default=preset_key, console=console).strip() or preset_key
        extra_headers = preset.get("extra_headers", {})

    profile = _p.Profile(
        provider=provider_kind,  # type: ignore[arg-type]
        base_url=base_url,
        api_key=api_key or None,
        model=model,
        extra_headers=extra_headers,
    )
    _p.upsert(profile_name, profile, activate=True)
    console.print(f"[green]✓[/green] saved active profile [cyan]{profile_name}[/cyan]  [dim]({provider_kind} / {model})[/dim]")

    if api_key or provider_kind == "ollama":
        _ping_provider(console, base_url, api_key, model, provider_kind)


def _ping_provider(console: Console, base_url: str, api_key: str, model: str, kind: str) -> None:
    """Best-effort health check so the user knows the key/URL works."""
    url = base_url.rstrip("/") + ("/api/tags" if kind == "ollama" else "/models")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        with httpx.Client(timeout=8.0) as c:
            r = c.get(url, headers=headers)
        if r.status_code == 200:
            console.print(f"[green]✓[/green] provider reachable at [dim]{base_url}[/dim]")
        else:
            console.print(f"[yellow]⚠[/yellow]  provider returned HTTP {r.status_code} at {url}. "
                          f"Check the key/URL with [cyan]exara doctor[/cyan].")
    except (httpx.HTTPError, OSError) as e:
        console.print(f"[yellow]⚠[/yellow]  could not reach provider ({type(e).__name__}). "
                      f"You can verify later with [cyan]exara doctor[/cyan].")


# --- MCP --------------------------------------------------------------------

def _setup_mcp(console: Console, *, force: bool) -> None:
    target = USER_DIR / "mcp.json"
    if target.exists() and not force:
        console.print(f"\n[bold]2. MCP servers[/bold]  [dim]({target} already exists, skipping. Use --force to overwrite.)[/dim]")
        return

    console.print("\n[bold]2. MCP servers (Model Context Protocol)[/bold]")
    console.print("[dim]These plug external tools into the agent (files, GitHub, memory, …).[/dim]")

    npx_available = shutil.which("npx") is not None
    if not npx_available:
        console.print("[yellow]⚠[/yellow]  `npx` not found on PATH. MCP servers need Node.js. "
                      "Install from https://nodejs.org or skip this step and add servers later.")
        if not Confirm.ask("Skip MCP setup for now?", default=True, console=console):
            return

    enabled: dict[str, dict[str, Any]] = {}
    for key, label, hint, template in _MCP_CHOICES:
        console.print(f"\n  [cyan]{key}[/cyan]  {label}")
        console.print(f"    [dim]{hint}[/dim]")
        if not Confirm.ask(f"  Enable {key}?", default=(key in {"filesystem", "memory"}), console=console):
            continue

        entry = json.loads(json.dumps(template))  # deep copy
        if key == "filesystem":
            default_path = str(Path.home())
            path = Prompt.ask("    Filesystem root", default=default_path, console=console).strip() or default_path
            entry["args"] = [a.replace("{PATH}", path) for a in entry["args"]]
        elif key == "github":
            token = Prompt.ask("    GitHub PAT", password=True, console=console).strip()
            if not token:
                console.print("    [yellow]No token entered — skipping github.[/yellow]")
                continue
            entry["env"] = {"GITHUB_PERSONAL_ACCESS_TOKEN": token}
        entry["disabled"] = False
        enabled[key] = entry

    if not enabled:
        console.print("[dim]No MCP servers enabled. Edit ~/.ai-agent/mcp.json later to add some.[/dim]")
        # Still write an empty stub so the user has a template to expand.
        enabled = {}

    target.write_text(json.dumps({"mcpServers": enabled}, indent=2), encoding="utf-8")
    console.print(f"[green]✓[/green] wrote {target}  ([dim]{len(enabled)} server(s)[/dim])")


# --- starter skill ----------------------------------------------------------

def _setup_starter_skill(console: Console, *, force: bool) -> None:
    target = USER_DIR / "skills" / "my-preferences.md"
    if target.exists() and not force:
        console.print(f"\n[bold]3. Starter skill[/bold]  [dim]({target.name} already exists, leaving it alone.)[/dim]")
        return
    console.print("\n[bold]3. Starter skill[/bold]")
    target.write_text(_STARTER_SKILL, encoding="utf-8")
    console.print(f"[green]✓[/green] wrote {target}")
    console.print("[dim]Skills load into every chat. Edit this one to teach the agent your preferences.[/dim]")
