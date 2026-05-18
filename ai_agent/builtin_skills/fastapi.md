---
name: fastapi
description: FastAPI conventions (async, pydantic, dependency injection)
triggers:
  dependencies: ["fastapi"]
  keywords: ["fastapi", "endpoint", "route"]
---

## Layout
- `main.py` is the entrypoint (creates the `FastAPI()` instance, mounts routers).
- One router per feature: `routers/users.py` with `router = APIRouter(prefix="/users", tags=["users"])`.
- Pydantic models in `schemas/` (request + response), DB models in `models/` separately.
- Business logic in `services/`, called from routes. Routes stay thin.

## Endpoints
- Annotate everything: response body, request body, query params.
- Use Pydantic v2 models for both — FastAPI gives you free OpenAPI docs + validation.
- For optional query params: `q: str | None = None`.
- For path params: `@router.get("/{user_id}")` → `async def f(user_id: int)`.
- Default to `async def`; use plain `def` only when work is genuinely sync.

## Dependency injection
- `Depends()` for shared logic: auth, DB session, current user.
  ```python
  async def get_db() -> AsyncIterator[AsyncSession]:
      async with SessionLocal() as s: yield s

  @router.get("/users")
  async def list_users(db: AsyncSession = Depends(get_db)): ...
  ```
- Avoid manually constructing dependencies inside endpoints.

## Async + IO
- Use async DB drivers: `asyncpg`, `aiomysql`, `motor`, SQLAlchemy 2.0 async.
- HTTP calls: `httpx.AsyncClient` shared via a dependency, not constructed per-request.
- Long-running tasks: don't block — use `BackgroundTasks` or push to a queue (Celery, Arq, RQ).

## Errors
- Raise `HTTPException(status_code=..., detail=...)` for client-facing errors.
- Use exception handlers (`@app.exception_handler(MyError)`) for custom domain exceptions.
- Don't leak stack traces in production: configure `app.exception_handlers` with sane defaults.

## Testing
- For async tests use **`httpx.AsyncClient(transport=ASGITransport(app=app), ...)`** —
  the old `TestClient` is sync only.
- **CRITICAL**: always override `get_db` with a test database. Never let tests hit
  your dev/prod DB even if the fixture "creates and drops" the schema.
  ```python
  from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

  test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
  TestSession = async_sessionmaker(test_engine, expire_on_commit=False)

  async def override_get_db():
      async with TestSession() as s:
          yield s

  app.dependency_overrides[get_db] = override_get_db
  ```
- Recreate schema per test (autouse fixture) so tests don't pollute each other.
- With `asyncio_mode = "auto"` in pyproject.toml, you DON'T need `@pytest.mark.asyncio`
  on every test — just `async def test_*` is enough.

## SQLAlchemy 2.0 (modern style)
- Use **`Mapped[...]` + `mapped_column()`** instead of the legacy `Column(...)`:
  ```python
  from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
  from sqlalchemy import String

  class Base(DeclarativeBase):
      pass

  class Usuario(Base):
      __tablename__ = "usuarios"
      id: Mapped[int] = mapped_column(primary_key=True)
      nombre: Mapped[str] = mapped_column(String(100))
      email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
  ```
  - Free type hints, integrates with mypy.
  - `Mapped[int | None]` for nullable, no need for `nullable=True`.
- Use `select(Model).where(...)` + `await session.execute(stmt)` + `.scalar_one_or_none()` etc.
- `async_sessionmaker` (not the legacy `sessionmaker(class_=AsyncSession)`).
- For relationships: `Mapped[list["Other"]] = relationship(back_populates="...")`.

## Common pitfalls
- Mutable default params in Pydantic models (use `Field(default_factory=list)`).
- Forgetting `response_model=` → returns whatever you happen to return (leaks fields).
- Mixing `def` and `async def` — sync routes block the event loop.
- Global state for "current user" — use a dependency instead.
- Heavy work in route handlers — push to background tasks or a worker.
