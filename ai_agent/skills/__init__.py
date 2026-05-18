"""Skills system — auto-loaded markdown knowledge packs.

Each skill is a `.md` file with YAML-ish frontmatter declaring when it
should be active and a body containing actionable guidance for the model.

When the agent starts a session (or processes a new user prompt), it
inspects the workspace (which manifests / files are present) and the
user's message (keywords), then injects the matching skills into the
system prompt as a "# Active skills" section.

Frontmatter shape:

    ---
    name: nextjs
    description: Next.js 16 App Router conventions
    triggers:
      always: false
      files_present: ["package.json"]
      dependencies: ["next"]
      keywords: ["next.js", "nextjs", "app router", "server component"]
    ---

    # body — markdown the model will read

Triggers are OR-ed: if any one matches, the skill activates. `always: true`
forces it on for every session.
"""
from .loader import (
    Skill,
    Triggers,
    load_all_skills,
    load_skills,
    render_skill_block,
    select_active,
)
from .stack import detect_stack

__all__ = [
    "Skill",
    "Triggers",
    "load_skills",
    "load_all_skills",
    "render_skill_block",
    "select_active",
    "detect_stack",
]
