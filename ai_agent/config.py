"""Centralised configuration loaded from YAML + environment variables."""
from __future__ import annotations

import importlib.resources as _resources
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

# User-level config dir — survives across `cd`s. Auto-created on first run.
USER_CONFIG_DIR = Path.home() / ".ai-agent"


def _bundled_default_config_text() -> str:
    """Read the default YAML shipped inside the wheel (ai_agent/_data/)."""
    try:
        return (_resources.files("ai_agent") / "_data" / "default_config.yaml").read_text(
            encoding="utf-8"
        )
    except (FileNotFoundError, ModuleNotFoundError):
        return ""

PermissionLevel = Literal["safe", "normal", "full"]


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:7b"
    keep_alive: str = "10m"


class OpenAICompatConfig(BaseModel):
    base_url: str = "http://localhost:1234/v1"
    api_key: str = "not-needed"
    model: str = "qwen2.5-coder-7b-instruct"
    # Extra HTTP headers — primarily for OpenRouter (HTTP-Referer + X-Title)
    # so your account dashboard can attribute requests to this client.
    extra_headers: dict[str, str] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    provider: Literal["ollama", "openai_compat"] = "ollama"
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openai_compat: OpenAICompatConfig = Field(default_factory=OpenAICompatConfig)


class AgentConfig(BaseModel):
    name: str = "ai-agent"
    max_steps: int = 25
    temperature: float = 0.2
    stream: bool = True
    # Cap on tokens per model response. Lower values reduce the credit OpenRouter
    # pre-authorises (it holds the worst-case cost upfront), so you don't get
    # "insufficient credit" errors near zero balance. 4000 is plenty for most turns.
    max_tokens: int = 4000


class SandboxConfig(BaseModel):
    """Optional Docker sandbox for run_python / execute_terminal.

    When enabled, those tools run inside an isolated container instead of
    your host shell. Requires a working `docker` CLI on PATH.
    """
    enabled: bool = False
    python_image: str = "python:3.13-slim"
    shell_image: str = "alpine:latest"
    allow_network: bool = False
    # If True, the workspace is mounted read-write inside the container.
    # If False (default), it's read-only.
    mount_workspace_writable: bool = False
    timeout_seconds: int = 120


class SafetyConfig(BaseModel):
    permission_level: PermissionLevel = "normal"
    require_confirmation: bool = True
    denied_commands: list[str] = Field(default_factory=list)
    denied_patterns: list[str] = Field(default_factory=list)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)


class MemoryConfig(BaseModel):
    # Defaults to ~/.ai-agent/data/agent.db so memory follows the user across
    # workspaces. Override via AI_AGENT_DB_PATH or per-project config.yaml.
    db_path: str = str(USER_CONFIG_DIR / "data" / "agent.db")
    conversation_window: int = 40
    project_index_enabled: bool = True
    # Auto-compaction: when in-memory history exceeds `summarise_after_messages`,
    # replace older turns with a model-generated summary, keeping the last
    # `keep_recent` messages verbatim. The full transcript is still persisted
    # to the SQLite store regardless.
    summarise_after_messages: int = 60
    keep_recent: int = 12


class HookSpec(BaseModel):
    """One hook entry inside HooksConfig.<event>.

    `command` is run via the platform shell. It receives a JSON payload on
    stdin describing the event. Optional `tools` matcher restricts the hook
    to a subset of tools (only meaningful for pre_tool_use / post_tool_use).
    """
    command: str
    tools: list[str] = Field(default_factory=list, description="Tool name allowlist for pre/post_tool_use; empty = any")
    timeout: int = Field(15, description="Seconds before the hook is killed")
    block_on_error: bool = Field(False, description="If true, a failed pre_tool_use hook blocks the tool from executing")


class HooksConfig(BaseModel):
    """Lifecycle hooks the user can configure to extend the agent.

    Each event holds a list of HookSpec. Events:

    - session_start:       once when a chat session boots
    - user_prompt_submit:  when a user message is received
    - pre_tool_use:        before a tool dispatches (can block in normal mode)
    - post_tool_use:       after a tool returns
    - stop:                when the chat session is ending
    """
    session_start: list[HookSpec] = Field(default_factory=list)
    user_prompt_submit: list[HookSpec] = Field(default_factory=list)
    pre_tool_use: list[HookSpec] = Field(default_factory=list)
    post_tool_use: list[HookSpec] = Field(default_factory=list)
    stop: list[HookSpec] = Field(default_factory=list)


class MCPConfig(BaseModel):
    """Where to find the MCP server registry, and whether to enable it.

    The registry itself lives in `mcp.json` (Claude Desktop / Cursor format).
    """
    enabled: bool = True
    config_path: str = "./mcp.json"


class SkillsConfig(BaseModel):
    """Auto-loaded markdown knowledge packs that match the workspace stack."""
    enabled: bool = True
    dir: str = "./skills"
    max_chars: int = 12_000  # cap on total skill text injected into the system prompt


class MultimodalConfig(BaseModel):
    """Per-capability model overrides.

    Two levels of override:

    1. **Same-provider override** (just set the model fields). Used when the
       active provider has a vision/audio capable model — e.g. agent runs on
       Ollama qwen2.5:7b-instruct, vision goes to Ollama gemma4.

    2. **Hybrid provider** (set the *_provider + *_base_url + *_model). Used
       when the agent talks to one provider but multimodal lives on another —
       e.g. agent on OpenRouter (DeepSeek), vision on local Ollama (Gemma 4).
       Saves cents per image and keeps your data local.
    """
    # Model id. With same-provider, must be valid for the active router.
    # With hybrid, must be valid for the override provider.
    vision_model: str | None = None
    audio_model: str | None = None

    # Hybrid provider — when set, read_image/read_audio build their own client
    # instead of reusing the agent's router.
    vision_provider: Literal["ollama", "openai_compat"] | None = None
    vision_base_url: str | None = None
    vision_api_key: str | None = None

    audio_provider: Literal["ollama", "openai_compat"] | None = None
    audio_base_url: str | None = None
    audio_api_key: str | None = None


class UiConfig(BaseModel):
    """Cosmetic preferences for the CLI."""
    name: str = "ai agent"  # shown as ASCII art on chat start
    tagline: str = "local-first autonomous coding agent"
    banner: bool = True
    banner_font: str = "ansi_shadow"  # any pyfiglet font; 'ansi_shadow' is bold block letters
    banner_color: str = "cyan"  # rich color name
    spinner: bool = True  # show thinking spinner while waiting for the model


class ApiConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class LoggingConfig(BaseModel):
    level: str = "INFO"
    dir: str = str(USER_CONFIG_DIR / "logs")
    json_output: bool = Field(True, alias="json")
    model_config = {"populate_by_name": True}


class Settings(BaseModel):
    workspace: Path = Field(default_factory=lambda: Path.cwd())
    agent: AgentConfig = Field(default_factory=AgentConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    multimodal: MultimodalConfig = Field(default_factory=MultimodalConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _env_overrides() -> dict[str, Any]:
    """Selected env vars override YAML config — useful for ops without editing files."""
    o: dict[str, Any] = {}
    if v := os.getenv("AI_AGENT_PROVIDER"):
        o.setdefault("model", {})["provider"] = v
    if v := os.getenv("AI_AGENT_OLLAMA_BASE_URL"):
        o.setdefault("model", {}).setdefault("ollama", {})["base_url"] = v
    if v := os.getenv("AI_AGENT_OLLAMA_MODEL"):
        o.setdefault("model", {}).setdefault("ollama", {})["model"] = v
    if v := os.getenv("AI_AGENT_OPENAI_BASE_URL"):
        o.setdefault("model", {}).setdefault("openai_compat", {})["base_url"] = v
    if v := os.getenv("AI_AGENT_OPENAI_API_KEY"):
        o.setdefault("model", {}).setdefault("openai_compat", {})["api_key"] = v
    if v := os.getenv("AI_AGENT_OPENAI_MODEL"):
        o.setdefault("model", {}).setdefault("openai_compat", {})["model"] = v
    # OpenRouter best practice — attribute requests so your dashboard shows them
    referer = os.getenv("AI_AGENT_HTTP_REFERER")
    title = os.getenv("AI_AGENT_X_TITLE")
    if referer or title:
        headers = o.setdefault("model", {}).setdefault("openai_compat", {}).setdefault("extra_headers", {})
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

    # Hybrid multimodal — vision in a separate provider
    for cap in ("vision", "audio"):
        for key in ("provider", "base_url", "api_key", "model"):
            env = f"AI_AGENT_{cap.upper()}_{key.upper()}"
            if v := os.getenv(env):
                o.setdefault("multimodal", {})[f"{cap}_{key}"] = v

    # MCP
    if v := os.getenv("AI_AGENT_MCP_CONFIG"):
        o.setdefault("mcp", {})["config_path"] = v
    if v := os.getenv("AI_AGENT_MCP_ENABLED"):
        o.setdefault("mcp", {})["enabled"] = v.lower() in ("1", "true", "yes")

    # UI / branding
    if v := os.getenv("AI_AGENT_UI_NAME"):
        o.setdefault("ui", {})["name"] = v
    if v := os.getenv("AI_AGENT_UI_TAGLINE"):
        o.setdefault("ui", {})["tagline"] = v
    if v := os.getenv("AI_AGENT_UI_BANNER_COLOR"):
        o.setdefault("ui", {})["banner_color"] = v
    if v := os.getenv("AI_AGENT_UI_BANNER_FONT"):
        o.setdefault("ui", {})["banner_font"] = v
    if v := os.getenv("AI_AGENT_MAX_STEPS"):
        o.setdefault("agent", {})["max_steps"] = int(v)
    if v := os.getenv("AI_AGENT_TEMPERATURE"):
        o.setdefault("agent", {})["temperature"] = float(v)
    if v := os.getenv("AI_AGENT_PERMISSION_LEVEL"):
        o.setdefault("safety", {})["permission_level"] = v
    if v := os.getenv("AI_AGENT_REQUIRE_CONFIRMATION"):
        o.setdefault("safety", {})["require_confirmation"] = v.lower() in ("1", "true", "yes")
    if v := os.getenv("AI_AGENT_DB_PATH"):
        o.setdefault("memory", {})["db_path"] = v
    if v := os.getenv("AI_AGENT_LOG_DIR"):
        o.setdefault("logging", {})["dir"] = v
    if v := os.getenv("AI_AGENT_WORKSPACE"):
        o["workspace"] = v
    return o


def load_settings(config_path: Path | str | None = None) -> Settings:
    """Build Settings by merging (low → high precedence):

    1. Bundled `default_config.yaml` (ships in the wheel)
    2. `~/.ai-agent/config.yaml` if present (user-wide)
    3. `./config.yaml` in cwd if present (workspace)
    4. Explicit `config_path` argument if provided
    5. Active profile from ~/.ai-agent/profiles.json
    6. AI_AGENT_* env vars (and .env file in cwd)
    """
    raw: dict[str, Any] = {}
    bundled = _bundled_default_config_text()
    if bundled:
        raw = yaml.safe_load(bundled) or {}

    user_yaml = USER_CONFIG_DIR / "config.yaml"
    if user_yaml.is_file():
        raw = _deep_merge(raw, yaml.safe_load(user_yaml.read_text(encoding="utf-8")) or {})

    workspace_yaml = Path.cwd() / "config.yaml"
    if workspace_yaml.is_file() and workspace_yaml.resolve() != user_yaml.resolve():
        raw = _deep_merge(raw, yaml.safe_load(workspace_yaml.read_text(encoding="utf-8")) or {})

    if config_path is not None:
        path = Path(config_path)
        if path.is_file():
            raw = _deep_merge(raw, yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    raw = _deep_merge(raw, _profile_overrides())
    raw = _deep_merge(raw, _env_overrides())
    settings = Settings.model_validate(raw)
    # Ensure paths exist
    Path(settings.memory.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(settings.logging.dir).mkdir(parents=True, exist_ok=True)
    return settings


def _profile_overrides() -> dict[str, Any]:
    """If a profile is active in ~/.ai-agent/profiles.json, build the model
    section from it. Env vars later override this for ad-hoc tweaks.
    """
    try:
        from . import profiles
    except ImportError:  # pragma: no cover
        return {}
    active = profiles.get_active()
    if active is None:
        return {}
    _, p = active
    model_block: dict[str, Any] = {"provider": p.provider}
    if p.provider == "ollama":
        model_block["ollama"] = {
            "base_url": p.base_url,
            "model": p.model,
        }
    else:
        model_block["openai_compat"] = {
            "base_url": p.base_url,
            "api_key": p.api_key or "not-needed",
            "model": p.model,
            "extra_headers": p.extra_headers,
        }
    return {"model": model_block}
