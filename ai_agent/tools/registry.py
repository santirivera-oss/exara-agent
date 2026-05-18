"""Tool registry — discover, register, and dispatch tools."""
from __future__ import annotations

from typing import Any

from .base import Tool, ToolContext, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool | type[Tool]) -> None:
        instance = tool() if isinstance(tool, type) else tool
        if instance.name in self._tools:
            raise ValueError(f"Tool already registered: {instance.name}")
        self._tools[instance.name] = instance

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def openai_specs(self) -> list[dict[str, Any]]:
        # Call via instance so subclasses (e.g. MCPTool) can override per-instance.
        return [t.to_openai_spec() for t in self._tools.values()]

    async def dispatch(self, name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                output="",
                error=f"unknown tool: {name!r}. Available: {self.names()}",
            )
        return await tool.run(args, ctx)


# Tools that mutate state — these are filtered out when the agent is in plan mode.
WRITE_TOOLS = frozenset({
    "write_file", "edit_file", "multi_edit", "create_file", "delete_file",
    "execute_terminal", "bash_background", "kill_process",
    "run_python", "install_package", "git_commit",
})


def build_default_registry() -> ToolRegistry:
    """Construct the registry with all built-in tools."""
    from . import audio, background, browser, delegate, file_ops, git_ops, package, pdf, plan, python_exec, search, shell, todos, vision, web  # noqa: F401

    reg = ToolRegistry()
    # Order roughly matches expected frequency of use.
    reg.register(file_ops.ReadFile)
    reg.register(file_ops.WriteFile)
    reg.register(file_ops.EditFile)
    reg.register(file_ops.MultiEdit)
    reg.register(file_ops.CreateFile)
    reg.register(file_ops.DeleteFile)
    reg.register(file_ops.ListDirectory)
    reg.register(search.SearchProject)
    reg.register(web.WebFetch)
    reg.register(pdf.ReadPdf)
    reg.register(vision.ReadImage)
    reg.register(audio.ReadAudio)
    reg.register(browser.BrowserNavigate)
    reg.register(browser.BrowserGetText)
    reg.register(browser.BrowserClick)
    reg.register(browser.BrowserFill)
    reg.register(browser.BrowserScreenshot)
    reg.register(shell.ExecuteTerminal)
    reg.register(background.BashBackground)
    reg.register(background.Monitor)
    reg.register(background.KillProcess)
    reg.register(background.ListProcesses)
    reg.register(python_exec.RunPython)
    reg.register(git_ops.GitStatus)
    reg.register(git_ops.GitDiff)
    reg.register(git_ops.GitLog)
    reg.register(git_ops.GitCommit)
    reg.register(package.InstallPackage)
    reg.register(plan.ExitPlanMode)
    reg.register(delegate.Delegate)
    reg.register(todos.TodoWrite)
    reg.register(todos.TodoRead)
    return reg


default_registry = build_default_registry()
