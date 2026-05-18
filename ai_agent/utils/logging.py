"""Structured logging — quiet console, full-detail JSONL file output.

Design choices:
- structlog goes through stdlib logging (BoundLogger + LoggerFactory) so all
  loggers share the same handlers.
- Console handler shows WARNING+ only — the CLI is for chat UX, not for
  watching INFO chatter from httpx/anyio/mcp. Anything you want the user to
  see lives in `console.print(...)` calls inside the CLI, not in loggers.
- File handler at DEBUG level keeps every structured event as JSONL in
  `logs/agent.jsonl` so post-mortem debugging stays easy.
"""
from __future__ import annotations

import logging
from pathlib import Path

import structlog
from rich.console import Console
from rich.logging import RichHandler

_configured = False
# legacy_windows=False bypasses cp1252 cmd.exe path and uses ANSI/UTF-8 directly.
console = Console(legacy_windows=False)


def configure_logging(level: str = "INFO", log_dir: str | Path = "./logs", json_output: bool = True, width: int | None = None) -> None:
    global _configured, console
    if _configured:
        return

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    console = Console(legacy_windows=False, width=width)

    # --- Console handler: WARNINGS and above only, plain text ---
    console_handler = RichHandler(
        console=console,
        show_time=False,
        show_path=False,
        show_level=True,
        markup=False,
        # rich_tracebacks=False — even when something escalates to WARNING/ERROR,
        # we don't want a 30-line traceback panel in the chat. The full stack
        # is still captured in logs/agent.jsonl for post-mortem debugging.
        rich_tracebacks=False,
    )
    console_handler.setLevel(logging.WARNING)

    handlers: list[logging.Handler] = [console_handler]

    # --- File handler: full JSONL at DEBUG+ ---
    if json_output:
        file_handler = logging.FileHandler(log_path / "agent.jsonl", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        file_handler.setLevel(logging.DEBUG)
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.DEBUG,  # root captures everything; handlers filter
        format="%(message)s",
        handlers=handlers,
        force=True,
    )

    # Third-party libraries that spam INFO. Drop them to WARNING so they don't
    # show up in the chat UI — file handler still captures any of them at WARN+.
    for noisy in ("httpx", "httpcore", "mcp", "mcp.server", "mcp.client", "anyio", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # asyncio sometimes complains about "an error occurred during closing of
    # asynchronous generator" when the interpreter tears down MCP stdio
    # streams from the wrong task. Cosmetic noise — silence it specifically.
    class _DropAsyncgenClose(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            msg = record.getMessage()
            return "closing of asynchronous generator" not in msg
    logging.getLogger("asyncio").addFilter(_DropAsyncgenClose())

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    # JSON for the file; console handler only sees WARN+ so the JSON-ish strings
    # rarely appear there in practice.
    processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None):
    if not _configured:
        configure_logging()
    return structlog.get_logger(name) if name else structlog.get_logger()
