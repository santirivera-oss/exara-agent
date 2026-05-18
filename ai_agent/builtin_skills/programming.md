---
name: programming
description: Cross-language fundamentals — applies regardless of stack
triggers:
  always: true
---

## Data over algorithms
- Get the data shape right and most code becomes obvious.
- Prefer flat, normalised structures with stable IDs over deeply nested objects.
- Immutable values by default. Mutate explicitly when there's a reason.
- Avoid sentinel values (-1, "", "N/A"). Use proper option/maybe/null with clear meaning.

## Naming
- A good name eliminates the need for a comment.
- Length scales with scope: loop var can be `i`, exported function deserves full words.
- Domain language > technical jargon. Talk like the user, not the framework.
- Avoid `get_`, `do_`, `manage_`, `handle_` unless you can't be more specific.

## Functions
- Each does one thing. "And" in the name = split it.
- 3 args sweet spot, 5 max. Beyond that: pass a struct/options object.
- Return early on the unhappy path. Avoid deep nesting (max 3 levels).
- Pure where possible: same input → same output, no side effects. Easy to test.
- Side effects (IO, network, mutation) go at the boundary, isolated.

## Error handling
- Treat error paths as first-class — they're how real users encounter your code.
- At the source: throw/return a specific error type with context.
- At the boundary: catch, translate to a user-friendly message, log the original.
- **Don't catch what you don't handle.** A swallowed exception is a bug waiting.
- Failures that the caller MUST handle → use the type system (Result, Either, exceptions of type X). Failures the caller CAN ignore → log and continue.

## Concurrency
- Default: write sequential code. Add concurrency only when there's a measured problem.
- Shared mutable state across threads = bugs. Prefer message passing (channels, queues, actors).
- Async-first for IO-bound work. Threads/processes for CPU-bound.
- Cancellation is part of the design, not an afterthought.
- Deadlocks: always acquire locks in the same order.

## Performance
- Measure before optimising. Profilers > intuition.
- Big-O matters at the scales you'll actually hit. O(n²) for n<100 is fine; for n>10k it's a fire.
- Most wins: avoid IO, batch IO, cache IO results — in that order.
- Don't pessimise: don't pre-cache, pre-async, pre-thread before you need to.

## Abstraction
- Three usages before extracting. Premature abstraction is worse than duplication.
- Abstractions should hide complexity, not just rename it.
- If your abstraction needs an "escape hatch" everywhere it's used, it's the wrong abstraction.
- Coupling > abstraction. Loose coupling lets you change one piece without rewriting five.

## Dependencies
- Each dependency is a long-term contract. Add them slowly, remove them when possible.
- Prefer the standard library when it suffices.
- Pin versions in production. Lockfile in version control.
- A dependency you can't replace in a day owns you, not the other way around.

## Testing
- Write tests at the level you want to refactor at. Tests of internals couple you to internals.
- Cover the boundary: inputs at the edge, outputs at the edge. Don't test trivial getters.
- Tests must be deterministic. Flaky tests are bugs.

## Things to avoid
- **Cleverness for its own sake**. Tomorrow-you reads code slower than you wrote it.
- **Mutable defaults** (Python's `def f(x=[])`, JS shared object literals).
- **Hidden control flow** (deep callback chains, magic ORM hooks, autoloaded plugins).
- **Boolean params** that flip behaviour. Two methods or an enum is clearer.
- **God classes / files**. If you scroll through it, split it.
- **Comments that lie**. No comment > wrong comment.

## When stuck
- Read the code you're modifying carefully — at least 2-3 surrounding files.
- Reproduce the bug before "fixing" it. If you can't reproduce, you're guessing.
- Bisect: when did it last work? What changed between then and now?
- Explain the problem out loud (or in writing). Half the time you solve it that way.
