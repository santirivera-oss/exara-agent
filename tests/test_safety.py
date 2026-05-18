"""Safety layer regressions."""
from __future__ import annotations

from ai_agent.config import SafetyConfig
from ai_agent.safety.validator import SafetyVerdict, Validator


def _validator(level: str = "normal", confirm: bool = True) -> Validator:
    cfg = SafetyConfig(
        permission_level=level,  # type: ignore[arg-type]
        require_confirmation=confirm,
        denied_commands=["rm -rf /", "shutdown"],
        denied_patterns=[r"rm\s+-rf\s+[/\\]", r"mkfs\."],
    )
    return Validator(cfg)


def test_destructive_command_denied():
    v = _validator()
    d = v.check_tool("execute_terminal", {"command": "rm -rf /"})
    assert d.verdict is SafetyVerdict.DENY


def test_destructive_pattern_denied():
    v = _validator()
    d = v.check_tool("execute_terminal", {"command": "sudo mkfs.ext4 /dev/sda1"})
    assert d.verdict is SafetyVerdict.DENY


def test_safe_mode_blocks_writes():
    v = _validator(level="safe")
    assert v.check_tool("write_file", {"path": "x", "content": "y"}).verdict is SafetyVerdict.DENY
    assert v.check_tool("read_file", {"path": "x"}).verdict is SafetyVerdict.ALLOW


def test_normal_mode_high_risk_requires_confirmation():
    v = _validator(level="normal", confirm=True)
    d = v.check_tool("delete_file", {"path": "x"})
    assert d.verdict is SafetyVerdict.CONFIRM


def test_full_mode_skips_confirmation():
    v = _validator(level="full")
    assert v.check_tool("delete_file", {"path": "x"}).verdict is SafetyVerdict.ALLOW
    # but hard-deny still applies
    assert v.check_tool("execute_terminal", {"command": "rm -rf /"}).verdict is SafetyVerdict.DENY


def test_read_tools_always_allowed():
    v = _validator(level="safe")
    for tool in ("read_file", "list_directory", "search_project", "git_status"):
        assert v.check_tool(tool, {}).verdict is SafetyVerdict.ALLOW
