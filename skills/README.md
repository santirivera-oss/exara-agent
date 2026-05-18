# Project-specific skills

This directory is for skills scoped to **this project only**. They override
built-in skills with the same name.

The built-in skills (`code-style`, `python`, `fastapi`, `web-frontend`,
`design`, `programming`, `testing`, `security`, `nextjs`, `typescript-react`)
now ship with the `exara-agent` package itself — they are available from any
directory you run `exara` in.

## Loader precedence (highest wins)

1. `./skills/*.md` (this directory — project overrides)
2. `~/.ai-agent/skills/*.md` (user-wide skills you want everywhere)
3. Built-in (bundled with the package, in `ai_agent/builtin_skills/`)

Same `name:` in two locations → the higher-precedence one wins.

## Inspect

```bash
exara skills list           # what's active here and from where
exara skills show <name>    # full body
```

## Create a project-specific skill

Drop a markdown file here with YAML frontmatter:

```markdown
---
name: my-team-conventions
description: How we structure code in this monorepo
triggers:
  always: true
---

## Naming
- ...
```

See `ai_agent/builtin_skills/code-style.md` for a complete reference.
