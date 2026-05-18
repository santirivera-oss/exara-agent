"""Multi-provider profile store.

Each profile bundles the model-provider config you'd otherwise put in `.env`
(provider type, base URL, API key, default model). Profiles live in
`~/.ai-agent/profiles.json`, NOT in the repo, so the file never gets
accidentally committed.

Typical use:

    # one-time, interactive
    ai-agent profile add openai
    ai-agent profile use openai

    # later
    ai-agent profile list
    ai-agent profile use openrouter  # swap instantly, no .env edits

The active profile overlays the loaded settings — env vars and YAML still
work as before, the profile just substitutes the model section.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderKind = Literal["ollama", "openai_compat"]


class Profile(BaseModel):
    """One model provider config."""
    provider: ProviderKind = "openai_compat"
    base_url: str
    api_key: str | None = None  # null means "no auth needed", typical for local Ollama
    model: str
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ProfileFile(BaseModel):
    """Top-level shape of profiles.json."""
    active: str | None = None
    profiles: dict[str, Profile] = Field(default_factory=dict)


# --- Storage path -----------------------------------------------------------

def default_path() -> Path:
    """`~/.ai-agent/profiles.json`. Override via `AI_AGENT_PROFILES_PATH` for tests."""
    override = os.getenv("AI_AGENT_PROFILES_PATH")
    if override:
        return Path(override)
    return Path.home() / ".ai-agent" / "profiles.json"


# --- API --------------------------------------------------------------------

def load(path: Path | None = None) -> ProfileFile:
    """Return the persisted profiles, or an empty file if it doesn't exist yet."""
    p = path or default_path()
    if not p.exists():
        return ProfileFile()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return ProfileFile.model_validate(raw)
    except (json.JSONDecodeError, OSError, ValueError):
        return ProfileFile()


def save(data: ProfileFile, path: Path | None = None) -> Path:
    """Write atomically. Sets user-only file perms on POSIX (best effort on Windows)."""
    p = path or default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(p)
    try:  # restrict to user-only on POSIX
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return p


def get_active(file: ProfileFile | None = None) -> tuple[str, Profile] | None:
    """Return (name, Profile) of the active one, or None if no active is set
    or it points to a deleted profile."""
    f = file if file is not None else load()
    if f.active and f.active in f.profiles:
        return f.active, f.profiles[f.active]
    return None


def upsert(name: str, profile: Profile, *, activate: bool = False, path: Path | None = None) -> ProfileFile:
    f = load(path)
    f.profiles[name] = profile
    if activate or f.active is None:
        f.active = name
    save(f, path)
    return f


def remove(name: str, *, path: Path | None = None) -> ProfileFile:
    f = load(path)
    f.profiles.pop(name, None)
    if f.active == name:
        # Auto-activate any other profile if there are some left
        f.active = next(iter(f.profiles), None)
    save(f, path)
    return f


def activate(name: str, *, path: Path | None = None) -> ProfileFile:
    f = load(path)
    if name not in f.profiles:
        raise KeyError(f"profile {name!r} not found; have {list(f.profiles)}")
    f.active = name
    save(f, path)
    return f


# --- Built-in presets shown by `ai-agent profile presets` -------------------

PRESETS: dict[str, dict[str, Any]] = {
    "openrouter": {
        "provider": "openai_compat",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-chat",
        "hint": "OpenRouter unified API (Claude, GPT, DeepSeek, free models). Key: https://openrouter.ai/keys",
        "extra_headers": {
            "HTTP-Referer": "https://github.com/local/ai-agent",
            "X-Title": "ai-agent",
        },
    },
    "openai": {
        "provider": "openai_compat",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "hint": "OpenAI directly. Key: https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "provider": "openai_compat",
        "base_url": "https://api.anthropic.com/v1",
        "model": "claude-haiku-4-5",
        "hint": "Anthropic via their OpenAI-compatible endpoint. Key: https://console.anthropic.com/settings/keys",
    },
    "deepseek": {
        "provider": "openai_compat",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "hint": "DeepSeek directly. Key: https://platform.deepseek.com/api_keys",
    },
    "groq": {
        "provider": "openai_compat",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "hint": "Groq — fast inference. Key: https://console.groq.com/keys",
    },
    "ollama-local": {
        "provider": "ollama",
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b-instruct",
        "hint": "Local Ollama, no API key needed.",
    },
    "lm-studio": {
        "provider": "openai_compat",
        "base_url": "http://localhost:1234/v1",
        "model": "qwen2.5-coder-7b-instruct",
        "hint": "LM Studio local server. Start LM Studio's server first.",
    },
}
