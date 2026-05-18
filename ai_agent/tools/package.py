"""Package install — pip / npm / pnpm / yarn detection."""
from __future__ import annotations

import asyncio
import shutil
import sys

from pydantic import BaseModel, Field

from .base import Tool, ToolContext, ToolResult


# Heuristic: pip pins use "==", npm scopes start with "@". An Ollama tag looks
# like "name:tag" with no "==" and no leading "@" — e.g. "llava:13b", "gemma4:latest".
_OLLAMA_KNOWN_MODELS = {
    "llama", "qwen", "gemma", "mistral", "phi", "codellama", "codestral",
    "deepseek", "llava", "moondream", "bakllava", "starcoder", "magicoder",
    "mixtral", "nous", "wizard", "orca", "vicuna", "yi",
}


def _looks_like_ollama_tag(pkg: str) -> bool:
    if "==" in pkg or pkg.startswith("@"):
        return False
    if ":" not in pkg:
        return False
    name_root = pkg.split(":", 1)[0].lower().split("-")[0].split("/")[-1]
    return any(known in name_root for known in _OLLAMA_KNOWN_MODELS)


class InstallPackageArgs(BaseModel):
    package: str = Field(..., description="Package name (or 'pkg==version'). Pass exactly one package per call.")
    manager: str = Field(
        "auto",
        description="auto | pip | npm | pnpm | yarn. 'auto' detects from the project files.",
    )
    dev: bool = Field(False, description="For npm/pnpm/yarn: install as devDependency")


class InstallPackage(Tool):
    name = "install_package"
    description = (
        "Install a single package using the project's package manager. "
        "Auto-detects pip vs npm/pnpm/yarn. Always requires user confirmation in normal mode."
    )
    Args = InstallPackageArgs
    requires_confirmation = True

    async def _run(self, args: InstallPackageArgs, ctx: ToolContext) -> ToolResult:
        # Catch the common mistake of trying to install an Ollama model through here.
        if _looks_like_ollama_tag(args.package):
            return ToolResult(
                False, "",
                error=(
                    f"'{args.package}' looks like an Ollama model tag, not a language "
                    "package. install_package only handles pip / npm / pnpm / yarn. "
                    f"To install an Ollama model, ask the user to run:  ollama pull {args.package}"
                ),
            )

        manager = args.manager
        if manager == "auto":
            manager = self._detect_manager(ctx)
            if not manager:
                return ToolResult(False, "", error="could not detect package manager — pass manager explicitly")

        cmd = self._build_command(manager, args)
        if not cmd:
            return ToolResult(False, "", error=f"unsupported manager: {manager}")

        if not shutil.which(cmd[0]) and cmd[0] != sys.executable:
            return ToolResult(False, "", error=f"{cmd[0]} not found on PATH")

        ctx.logger.info("install_package", manager=manager, package=args.package)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(ctx.workspace),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult(False, "", error="install timed out after 300s")
        stdout = out.decode("utf-8", errors="replace")
        stderr = err.decode("utf-8", errors="replace")
        ok = proc.returncode == 0
        return ToolResult(
            ok,
            f"exit_code={proc.returncode}\n{stdout}\n{stderr}".strip(),
            data={"manager": manager, "exit_code": proc.returncode},
            error=None if ok else f"install failed (exit {proc.returncode})",
        )

    @staticmethod
    def _detect_manager(ctx: ToolContext) -> str | None:
        ws = ctx.workspace
        if (ws / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (ws / "yarn.lock").exists():
            return "yarn"
        if (ws / "package.json").exists():
            return "npm"
        if (ws / "pyproject.toml").exists() or (ws / "requirements.txt").exists():
            return "pip"
        return None

    @staticmethod
    def _build_command(manager: str, args: InstallPackageArgs) -> list[str] | None:
        if manager == "pip":
            return [sys.executable, "-m", "pip", "install", args.package]
        if manager == "npm":
            base = ["npm", "install"]
            if args.dev:
                base.append("--save-dev")
            base.append(args.package)
            return base
        if manager == "pnpm":
            base = ["pnpm", "add"]
            if args.dev:
                base.append("-D")
            base.append(args.package)
            return base
        if manager == "yarn":
            base = ["yarn", "add"]
            if args.dev:
                base.append("--dev")
            base.append(args.package)
            return base
        return None
