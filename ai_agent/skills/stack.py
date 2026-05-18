"""Workspace stack detection — used as skill triggers.

Returns a set of lowercase tags describing the project: language, framework,
key dependencies. Triggers can match any of these.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def detect_stack(workspace: Path) -> tuple[set[str], set[str]]:
    """Return (tags, files_present).

    - tags: things the project is built with, e.g. {'python', 'fastapi', 'pytest'}
    - files_present: top-level manifest filenames the project has
    """
    tags: set[str] = set()
    files: set[str] = set()

    # ---- Python ----
    pyproject = workspace / "pyproject.toml"
    if pyproject.is_file():
        files.add("pyproject.toml")
        tags.add("python")
        try:
            txt = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            tags.update(_extract_python_deps(txt))
        except OSError:
            pass

    req = workspace / "requirements.txt"
    if req.is_file():
        files.add("requirements.txt")
        tags.add("python")
        try:
            for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
                pkg = line.strip().split("=")[0].split("<")[0].split(">")[0].split("[")[0]
                if pkg and not pkg.startswith("#"):
                    tags.add(pkg.lower())
        except OSError:
            pass

    # ---- Node / TS ----
    package_json = workspace / "package.json"
    if package_json.is_file():
        files.add("package.json")
        tags.add("javascript")
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8", errors="ignore"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            for k in deps:
                tags.add(k.lower())
            if "typescript" in deps:
                tags.add("typescript")
            if "next" in deps:
                tags.add("nextjs")
            if "react" in deps:
                tags.add("react")
            if "vue" in deps:
                tags.add("vue")
            if "svelte" in deps:
                tags.add("svelte")
            if "@nestjs/core" in deps:
                tags.add("nestjs")
            if "express" in deps:
                tags.add("express")
        except (OSError, json.JSONDecodeError):
            pass

    # ---- Rust ----
    if (workspace / "Cargo.toml").is_file():
        files.add("Cargo.toml")
        tags.add("rust")

    # ---- Go ----
    if (workspace / "go.mod").is_file():
        files.add("go.mod")
        tags.add("go")

    # ---- Misc ----
    if (workspace / "Dockerfile").is_file():
        files.add("Dockerfile")
        tags.add("docker")
    if (workspace / "docker-compose.yml").is_file() or (workspace / "compose.yml").is_file():
        tags.add("docker-compose")
    if (workspace / ".github" / "workflows").is_dir():
        tags.add("github-actions")
    if (workspace / "frontend").is_dir() and (workspace / "frontend" / "package.json").is_file():
        tags.add("frontend-subdir")

    return tags, files


def _extract_python_deps(pyproject_text: str) -> set[str]:
    """Cheap textual scan of a pyproject.toml — no toml parser dependency."""
    tags: set[str] = set()
    # Find the dependencies = [ ... ] block(s). Tolerant — works for [project]
    # and optional-dependencies tables alike.
    for block in re.findall(r"dependencies\s*=\s*\[(.*?)\]", pyproject_text, re.DOTALL):
        # Each dep is a quoted string. Capture them regardless of whether the
        # author put them on one line or several.
        for raw in re.findall(r'["\']([^"\']+)["\']', block):
            raw = raw.strip()
            if not raw:
                continue
            pkg = re.split(r"[<>=!~\[ ]", raw, 1)[0].strip().lower()
            if pkg:
                tags.add(pkg)
    return tags
