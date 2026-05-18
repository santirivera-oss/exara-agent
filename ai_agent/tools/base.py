"""Base classes for the tool plugin system.

Tools are async, declare a Pydantic args schema, and return a ToolResult.
The OpenAI/Ollama tool-calling JSON schema is generated from the args model.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel


@dataclass
class ToolContext:
    """Per-invocation context passed to every tool — workspace, logger, settings, etc."""
    workspace: Path
    settings: Any  # avoid circular import
    logger: Any
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    success: bool
    output: str
    data: dict[str, Any] | None = None
    error: str | None = None

    def to_model_message(self) -> str:
        """Compact serialisation for tool-result messages back to the LLM."""
        if self.success:
            return self.output if self.output else "(ok)"
        return f"ERROR: {self.error or 'unknown error'}"


class Tool(ABC):
    """Base tool. Subclasses set name/description/Args and implement _run()."""

    name: ClassVar[str]
    description: ClassVar[str]
    Args: ClassVar[type[BaseModel]]

    # Optional metadata
    requires_confirmation: ClassVar[bool] = False
    read_only: ClassVar[bool] = False

    @abstractmethod
    async def _run(self, args: BaseModel, ctx: ToolContext) -> ToolResult: ...

    async def run(self, raw_args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        try:
            parsed = self.Args.model_validate(raw_args or {})
        except Exception as e:
            return ToolResult(success=False, output="", error=f"invalid args: {e}")
        try:
            result = await self._run(parsed, ctx)
        except Exception as e:  # tools should not crash the agent loop
            # Use warning (no stack) — tool failures are expected and the
            # error string is already returned to the model. Stack traces
            # only pollute the chat.
            ctx.logger.warning("tool_error", tool=self.name, error=str(e))
            return ToolResult(success=False, output="", error=str(e))
        # Defensive: scrub API keys / tokens from output before the model sees it.
        # Cheap regex pass; covers built-in + MCP + everything that returns text.
        from ..utils.secrets import redact_secrets
        if result.output:
            redacted, n = redact_secrets(result.output)
            if n > 0:
                ctx.logger.warning("redacted_secrets", tool=self.name, count=n)
                result.output = redacted
        return result

    @classmethod
    def to_openai_spec(cls) -> dict[str, Any]:
        """Return the OpenAI/Ollama tool-calling spec for this tool."""
        schema = cls.Args.model_json_schema()
        # Pydantic emits $defs / title fields; strip noise the API doesn't need.
        schema.pop("title", None)
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": cls.description,
                "parameters": schema,
            },
        }
