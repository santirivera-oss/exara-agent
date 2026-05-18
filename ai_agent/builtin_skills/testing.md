---
name: testing
description: Test design principles and common patterns
triggers:
  always: true
---

## What to test
- Public behaviour, not implementation. If a refactor changes internals but not behaviour, tests shouldn't break.
- Edge cases > happy path. Empty, null, max size, duplicate, concurrent, malformed.
- Error paths get tests too — they're the parts you rarely run manually.
- Skip tests for trivial getters/setters or pure delegation.

## Structure
- AAA: **Arrange** (setup) → **Act** (call) → **Assert** (verify). One per test.
- One concept per test. If you need "and" in the test name, split it.
- Test names describe the scenario: `test_returns_404_when_user_not_found`,
  not `test_get_user`.

## Mocks / fakes
- Prefer **fakes** (in-memory implementations) over **mocks** (record/verify).
  - Mocks couple tests to call patterns. Fakes test behaviour.
- Mock at the system boundary (HTTP client, database driver), not deep internals.
- If you need to mock 5+ things to test a function, the function is probably doing too much.

## Async
- Pytest: `pytest-asyncio` with `asyncio_mode = "auto"` in config = test functions can just be `async def`.
- Use real event loops + real async libs; avoid `asyncio.run` inside tests.
- For timing-sensitive tests, use `freezegun` or `pytest-freezegun`, not `time.sleep`.

## Fixtures (pytest)
- Scope to the smallest level that works: `function` > `class` > `module` > `session`.
- Yield-based fixtures with explicit cleanup are clearer than raw return + finalizer.
- Composable: small fixtures that combine into bigger ones.

## What NOT to do
- Don't share mutable state between tests (DB, files, env vars). Use `tmp_path`, transaction rollbacks, monkeypatch.
- Don't test against your mocks (`assert_called_with` chains that mirror the implementation).
- Don't test the framework (e.g. that pydantic validates types — it does).
- Don't write tests that pass when the system is broken (assert nothing, sleep + hope).

## Determinism
- Tests must pass on every run. Flaky tests are bugs.
- Avoid `time.time()`, `random`, network, real clocks. Inject them.
- Order-independent: any subset of tests must pass in any order.
