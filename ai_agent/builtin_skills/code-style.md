---
name: code-style
description: Cross-language defaults for clean, maintainable code
triggers:
  always: true
---

When writing or modifying code, follow these defaults unless the codebase
clearly overrides them.

## Naming
- Variables: `snake_case` in Python/Rust, `camelCase` in JS/TS.
- Types/classes: `PascalCase` everywhere.
- Constants: `UPPER_SNAKE`.
- Booleans: prefer `is_`, `has_`, `should_` prefixes (`is_active`, not `active`).
- Names describe **what**, not how. `users_by_id` over `userMap`.

## Functions
- One responsibility per function. If you need "and" in the name, split it.
- Early returns over deep nesting.
- 5 args max — beyond that, take a config object/dataclass.
- Pure functions where possible; isolate side effects.
- Async-first when there's any IO.

## Errors
- Throw/raise specific exception types (`ValueError`, `KeyError`), not bare `Exception`.
- At system boundaries (HTTP, CLI, file IO), catch and translate to user-friendly messages.
- Never silence exceptions with bare `except:` or `catch {}`.
- Validate inputs at the edge of your system, trust them inside.

## Comments
- Default: write none. Names + structure should explain.
- DO write comments for: non-obvious WHY (workaround, business rule, perf trick), heads-up about gotchas, links to specs/RFCs.
- DON'T write comments for: what the code obviously does, scaffold like "# imports", change history (that's git).

## Refactors
- One refactor per change. Don't mix refactor + feature in the same diff.
- If you find smelly code unrelated to your task, leave it (or open a follow-up note).
- Prefer minimal targeted edits over rewrites unless the rewrite is the task.

## When in doubt
- Match the surrounding style of the file you're editing — consistency > personal preference.
- Read 2-3 nearby files to learn the codebase's conventions before adding new patterns.
