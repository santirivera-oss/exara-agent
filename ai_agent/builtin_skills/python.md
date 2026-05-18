---
name: python
description: Modern Python 3.12+ conventions and tooling
triggers:
  files_present: ["pyproject.toml", "requirements.txt", "setup.py"]
  dependencies: ["python"]
  keywords: ["python", ".py", "pytest", "fastapi", "django", "flask"]
---

## Versions
- Target Python 3.12+. Use new syntax: `match/case`, `|` in type hints, `Self`,
  generic syntax `class Foo[T]`, `TypedDict`, `Self`, type-statement.
- Use modern typing in annotations: `list[int]` not `List[int]`, `int | None` not `Optional[int]`.

## Tooling defaults
- **Format**: `ruff format` (replaces black).
- **Lint**: `ruff check`. Common rules: E, F, I (imports), B (bugbear), UP (upgrade syntax), SIM, N.
- **Type check**: `mypy --strict` for libraries, `--strict-equality --warn-unused-ignores` minimum.
- **Test**: `pytest` with `pytest-asyncio` for async. Mark async tests with `async def test_*`.
- **Deps**: prefer `uv` or `pip` with `pyproject.toml`. Pin only major versions: `httpx>=0.27`.

## Async
- Don't mix `time.sleep` in async code — use `await asyncio.sleep`.
- Don't block the event loop with sync IO; use `asyncio.to_thread` or async libs.
- `httpx.AsyncClient` over `requests` in async contexts.
- For subprocesses use `asyncio.create_subprocess_exec`, not `subprocess.run`.

## Errors
- Subclass `Exception` (not `BaseException`).
- Chain context: `raise NewError(...) from original`.
- For input validation prefer pydantic v2 models — free type coercion + nice errors.

## Pydantic v2
- `BaseModel` with `Field(...)` for required, `Field(default, ...)` for optional.
- `model_validate(dict)` not `parse_obj`. `model_dump()` not `dict()`.
- `Annotated[str, Field(min_length=3)]` for complex constraints.
- `model_config = {"from_attributes": True}` to read from SQLAlchemy rows etc.
  (was `orm_mode = True` in v1).
- For settings: `pydantic-settings.BaseSettings` + **`SettingsConfigDict`**,
  NOT the v1-style `class Config:` (deprecated):
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")
      database_url: str = "sqlite:///./db.sqlite"
  ```

## Anti-patterns
- Mutable default args (`def f(x=[]):`). Use `None` + `if x is None: x = []`.
- Catching `Exception` blindly. Catch specific types or let it bubble.
- `print()` for debugging in shipped code — use `logging` or `structlog`.
- Wildcard imports `from x import *`.
- Modifying a list while iterating it.
