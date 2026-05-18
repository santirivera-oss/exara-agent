"""Read skill markdown files + decide which apply to the current session."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Triggers:
    always: bool = False
    files_present: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass
class Skill:
    name: str
    description: str
    body: str
    triggers: Triggers
    path: Path | None = None

    def matches(self, *, stack_tags: set[str], files: set[str], user_text: str | None) -> bool:
        t = self.triggers
        if t.always:
            return True
        # files_present: any glob pattern that maps to something in `files`
        for pat in t.files_present:
            if pat in files:
                return True
        # dependencies: any string in the inferred stack tags
        for dep in t.dependencies:
            if dep.lower() in stack_tags:
                return True
        # keywords against the user's last prompt
        if user_text and t.keywords:
            low = user_text.lower()
            for kw in t.keywords:
                if kw.lower() in low:
                    return True
        return False


_FRONTMATTER_RE = re.compile(r"^---\s*\n(?P<fm>.*?)\n---\s*\n(?P<body>.*)$", re.DOTALL)


def parse_skill(text: str, *, path: Path | None = None) -> Skill | None:
    """Parse a single skill markdown string. Returns None if frontmatter is malformed."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None
    try:
        meta: dict[str, Any] = yaml.safe_load(match.group("fm")) or {}
    except yaml.YAMLError:
        return None
    name = meta.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    triggers_raw = meta.get("triggers") or {}
    if not isinstance(triggers_raw, dict):
        triggers_raw = {}
    triggers = Triggers(
        always=bool(triggers_raw.get("always", False)),
        files_present=[str(x) for x in (triggers_raw.get("files_present") or [])],
        dependencies=[str(x) for x in (triggers_raw.get("dependencies") or [])],
        keywords=[str(x) for x in (triggers_raw.get("keywords") or [])],
    )
    return Skill(
        name=name.strip(),
        description=str(meta.get("description", "")).strip(),
        body=match.group("body").strip(),
        triggers=triggers,
        path=path,
    )


def load_skills(directory: Path) -> list[Skill]:
    """Return every well-formed skill in `directory` (recursive). Single-source
    loader — for the multi-source one that merges bundled + user + workspace,
    use `load_all_skills`.
    """
    if not directory.exists():
        return []
    out: list[Skill] = []
    for p in sorted(directory.rglob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        skill = parse_skill(text, path=p)
        if skill is not None:
            out.append(skill)
    return out


def _load_bundled_skills() -> list[Skill]:
    """Skills shipped with the pip package itself — available from any cwd."""
    try:
        import importlib.resources as r
        root = r.files("ai_agent") / "builtin_skills"
        if not root.is_dir():
            return []
        out: list[Skill] = []
        for entry in root.iterdir():
            if not entry.name.endswith(".md"):
                continue
            try:
                text = entry.read_text(encoding="utf-8")
            except OSError:
                continue
            skill = parse_skill(text, path=None)
            if skill:
                out.append(skill)
        return out
    except (ImportError, FileNotFoundError, ModuleNotFoundError):
        return []


def load_all_skills(workspace_skills_dir: Path | None) -> list[Skill]:
    """Merge sources in precedence order: bundled < ~/.ai-agent/skills < workspace.
    Same `name` in two sources → the higher-precedence one wins.
    """
    sources: list[list[Skill]] = [_load_bundled_skills()]
    user_dir = Path.home() / ".ai-agent" / "skills"
    if user_dir.is_dir():
        sources.append(load_skills(user_dir))
    if workspace_skills_dir is not None and workspace_skills_dir.is_dir():
        sources.append(load_skills(workspace_skills_dir))

    by_name: dict[str, Skill] = {}
    for skills in sources:
        for s in skills:
            by_name[s.name] = s
    return list(by_name.values())


def select_active(
    skills: list[Skill],
    *,
    stack_tags: set[str],
    files: set[str],
    user_text: str | None = None,
) -> list[Skill]:
    return [s for s in skills if s.matches(stack_tags=stack_tags, files=files, user_text=user_text)]


def render_skill_block(skills: list[Skill]) -> str:
    """Format selected skills as a single markdown block for the system prompt."""
    if not skills:
        return ""
    parts = ["\n\n# Active skills", ""]
    for s in skills:
        parts.append(f"## {s.name}  — _{s.description}_" if s.description else f"## {s.name}")
        parts.append(s.body)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"
