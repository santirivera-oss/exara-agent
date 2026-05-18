"""Skills loader + matcher."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent.skills import (
    Skill,
    Triggers,
    detect_stack,
    load_skills,
    render_skill_block,
    select_active,
)
from ai_agent.skills.loader import parse_skill


SKILL_NEXT = """---
name: nextjs
description: Next.js conventions
triggers:
  dependencies: [next]
  keywords: [app router]
---

Use server components by default.
"""

SKILL_ALWAYS = """---
name: code-style
description: Universal style
triggers:
  always: true
---

Names describe what, not how.
"""

SKILL_NO_TRIGGERS = """---
name: niche
description: only by file
triggers:
  files_present: [Cargo.toml]
---

Rust-specific.
"""

SKILL_BAD_FRONTMATTER = """No frontmatter here, just text."""


def test_parse_skill_full():
    s = parse_skill(SKILL_NEXT)
    assert s is not None
    assert s.name == "nextjs"
    assert s.description == "Next.js conventions"
    assert s.triggers.dependencies == ["next"]
    assert s.triggers.keywords == ["app router"]
    assert "server components" in s.body.lower()


def test_parse_skill_always():
    s = parse_skill(SKILL_ALWAYS)
    assert s is not None
    assert s.triggers.always is True


def test_parse_skill_malformed_returns_none():
    assert parse_skill(SKILL_BAD_FRONTMATTER) is None


def test_load_skills_from_dir(tmp_path: Path):
    (tmp_path / "a.md").write_text(SKILL_NEXT, encoding="utf-8")
    (tmp_path / "b.md").write_text(SKILL_ALWAYS, encoding="utf-8")
    (tmp_path / "bad.md").write_text(SKILL_BAD_FRONTMATTER, encoding="utf-8")
    skills = load_skills(tmp_path)
    names = sorted(s.name for s in skills)
    assert names == ["code-style", "nextjs"]


def test_select_active_always(tmp_path: Path):
    s = parse_skill(SKILL_ALWAYS)
    active = select_active([s], stack_tags=set(), files=set())
    assert len(active) == 1


def test_select_active_by_dependency(tmp_path: Path):
    s = parse_skill(SKILL_NEXT)
    active = select_active([s], stack_tags={"next"}, files=set())
    assert active == [s]


def test_select_active_by_files_present(tmp_path: Path):
    s = parse_skill(SKILL_NO_TRIGGERS)
    active = select_active([s], stack_tags=set(), files={"Cargo.toml"})
    assert active == [s]


def test_select_active_by_keyword(tmp_path: Path):
    s = parse_skill(SKILL_NEXT)
    active = select_active([s], stack_tags=set(), files=set(),
                           user_text="I'm building an app router project")
    assert active == [s]


def test_select_no_match(tmp_path: Path):
    s = parse_skill(SKILL_NEXT)
    active = select_active([s], stack_tags={"python"}, files={"pyproject.toml"})
    assert active == []


def test_render_skill_block_includes_bodies():
    s1 = parse_skill(SKILL_NEXT)
    s2 = parse_skill(SKILL_ALWAYS)
    block = render_skill_block([s1, s2])
    assert "# Active skills" in block
    assert "## nextjs" in block
    assert "Names describe what" in block


# --- stack detection -------------------------------------------------------

def test_detect_python_workspace(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["fastapi>=0.115", "pydantic>=2.7"]\n',
        encoding="utf-8",
    )
    tags, files = detect_stack(tmp_path)
    assert "python" in tags
    assert "fastapi" in tags
    assert "pydantic" in tags
    assert "pyproject.toml" in files


def test_detect_nextjs_workspace(tmp_path: Path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "x",
        "dependencies": {"next": "15.0.0", "react": "19.0.0"},
        "devDependencies": {"typescript": "5.6.0"},
    }), encoding="utf-8")
    tags, files = detect_stack(tmp_path)
    assert "nextjs" in tags
    assert "react" in tags
    assert "typescript" in tags
    assert "javascript" in tags
    assert "package.json" in files


def test_detect_empty_workspace(tmp_path: Path):
    tags, files = detect_stack(tmp_path)
    assert tags == set()
    assert files == set()


# --- multi-source load_all_skills ----------------------------------------

def test_load_all_skills_includes_bundled(tmp_path: Path, monkeypatch):
    """Even with no workspace skills/, bundled skills must show up."""
    from ai_agent.skills import load_all_skills
    # Redirect home so the user dir is empty during the test
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
    skills = load_all_skills(tmp_path / "nonexistent")
    names = {s.name for s in skills}
    assert "code-style" in names
    assert "python" in names
    assert "design" in names


def test_load_all_skills_workspace_overrides_bundled(tmp_path: Path, monkeypatch):
    """A workspace-level skill with the same name should win."""
    from ai_agent.skills import load_all_skills
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake-home")
    ws_skills = tmp_path / "skills"
    ws_skills.mkdir()
    (ws_skills / "code-style.md").write_text(
        "---\nname: code-style\ndescription: my custom override\ntriggers:\n  always: true\n---\n"
        "My team's rules.\n",
        encoding="utf-8",
    )
    skills = load_all_skills(ws_skills)
    cs = next(s for s in skills if s.name == "code-style")
    assert cs.description == "my custom override"
    assert "My team's rules" in cs.body


# --- multi-source MCP config ----------------------------------------------

def test_load_merged_mcp_config_user_only(tmp_path: Path, monkeypatch):
    """User-wide mcp.json (no workspace file) should be loaded."""
    from ai_agent.mcp.config import load_merged_mcp_config
    fake_home = tmp_path / "fake-home"
    (fake_home / ".ai-agent").mkdir(parents=True)
    (fake_home / ".ai-agent" / "mcp.json").write_text(
        '{"mcpServers": {"global-srv": {"command": "echo", "args": ["x"]}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    merged = load_merged_mcp_config(tmp_path / "nonexistent-ws.json")
    assert "global-srv" in merged


def test_load_merged_mcp_config_workspace_overrides_user(tmp_path: Path, monkeypatch):
    from ai_agent.mcp.config import load_merged_mcp_config
    fake_home = tmp_path / "fake-home"
    (fake_home / ".ai-agent").mkdir(parents=True)
    (fake_home / ".ai-agent" / "mcp.json").write_text(
        '{"mcpServers": {"same": {"command": "user-cmd", "args": []}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    ws_file = tmp_path / "mcp.json"
    ws_file.write_text(
        '{"mcpServers": {"same": {"command": "workspace-cmd", "args": []}}}',
        encoding="utf-8",
    )
    merged = load_merged_mcp_config(ws_file)
    assert merged["same"].command == "workspace-cmd"
