"""Command and tool-call validation.

Three-tier permission model:
- safe:   only side-effect-free tools (read, list, search). Mutations denied.
- normal: mutations allowed; high-risk commands require human confirmation.
- full:   no confirmation prompts. Hard-denylist still applies.

The validator returns a SafetyDecision (allow / confirm / deny) — the caller
(executor or CLI) decides how to interpret confirm (prompt user, auto-allow, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from ..config import SafetyConfig

PermissionLevel = Literal["safe", "normal", "full"]


class SafetyVerdict(str, Enum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class SafetyDecision:
    verdict: SafetyVerdict
    reason: str
    matched_rule: str | None = None


# Tools that never mutate state — always safe.
READ_ONLY_TOOLS = frozenset({
    "read_file",
    "list_directory",
    "search_project",
    "git_status",
    "git_diff",
    "git_log",
})

# Tools that always require confirmation in `normal` mode (regardless of payload).
HIGH_RISK_TOOLS = frozenset({
    "execute_terminal",
    "bash_background",
    "kill_process",
    "delete_file",
    "install_package",
    "run_python",
    "git_commit",
})


class Validator:
    def __init__(self, config: SafetyConfig):
        self.config = config
        self._denied_command_substrings = [c.lower().strip() for c in config.denied_commands]
        self._denied_regexes = [re.compile(p, re.IGNORECASE) for p in config.denied_patterns]

    @property
    def level(self) -> PermissionLevel:
        return self.config.permission_level

    def check_tool(self, tool_name: str, args: dict) -> SafetyDecision:
        """Evaluate a tool call before execution."""
        level = self.level

        # Hard deny: shell command matches a destructive pattern (any level).
        # Applies to any tool whose primary arg is a shell command.
        if tool_name in ("execute_terminal", "bash_background"):
            cmd = (args.get("command") or "").strip()
            denial = self._check_dangerous_command(cmd)
            if denial:
                return denial

        # Safe mode: only read-only tools
        if level == "safe" and tool_name not in READ_ONLY_TOOLS:
            return SafetyDecision(
                SafetyVerdict.DENY,
                f"Tool '{tool_name}' is not allowed in 'safe' permission mode.",
                matched_rule="permission_level=safe",
            )

        # Read-only tools always pass
        if tool_name in READ_ONLY_TOOLS:
            return SafetyDecision(SafetyVerdict.ALLOW, "read-only tool")

        # Full mode: skip confirmation gating
        if level == "full":
            return SafetyDecision(SafetyVerdict.ALLOW, "permission_level=full")

        # Normal mode: high-risk tools require confirmation
        if tool_name in HIGH_RISK_TOOLS and self.config.require_confirmation:
            preview = self._preview(tool_name, args)
            return SafetyDecision(
                SafetyVerdict.CONFIRM,
                f"High-risk tool '{tool_name}' requires confirmation. {preview}",
                matched_rule="high_risk_tool",
            )

        return SafetyDecision(SafetyVerdict.ALLOW, "default allow")

    def _check_dangerous_command(self, command: str) -> SafetyDecision | None:
        lc = command.lower()
        for sub in self._denied_command_substrings:
            if sub and sub in lc:
                return SafetyDecision(
                    SafetyVerdict.DENY,
                    f"Command contains denied substring: {sub!r}",
                    matched_rule=f"denylist:{sub}",
                )
        for rx in self._denied_regexes:
            if rx.search(command):
                return SafetyDecision(
                    SafetyVerdict.DENY,
                    f"Command matches denied pattern: {rx.pattern!r}",
                    matched_rule=f"regex:{rx.pattern}",
                )
        return None

    @staticmethod
    def _preview(tool_name: str, args: dict) -> str:
        if tool_name == "execute_terminal":
            return f"$ {args.get('command', '')}"
        if tool_name == "bash_background":
            return f"$ {args.get('command', '')} (background)"
        if tool_name == "kill_process":
            return f"kill {args.get('id')!r}"
        if tool_name == "delete_file":
            return f"path={args.get('path')!r}"
        if tool_name == "install_package":
            return f"package={args.get('package')!r}"
        if tool_name == "run_python":
            code = args.get("code", "")
            return "code=" + (code[:120] + "..." if len(code) > 120 else code)
        if tool_name == "git_commit":
            return f"message={args.get('message')!r}"
        return ""
