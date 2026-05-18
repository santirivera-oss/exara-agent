"""Cosmetic helpers — ASCII banners, status spinners, color choices.

Everything here is opt-in: nothing changes runtime behaviour, only what the
user sees in the CLI.
"""
from __future__ import annotations

from rich.align import Align
from rich.console import Console, Group
from rich.text import Text


def render_banner(
    console: Console,
    name: str,
    tagline: str = "",
    *,
    font: str = "ansi_shadow",
    color: str = "cyan",
) -> None:
    """Print an ASCII-art banner. Falls back to plain text if pyfiglet errors."""
    try:
        import pyfiglet
        art = pyfiglet.figlet_format(name, font=font)
    except Exception:
        art = name.upper()

    art_text = Text(art.rstrip("\n"), style=f"bold {color}")
    elems: list = [Align.left(art_text)]
    if tagline:
        elems.append(Text(tagline, style="dim italic"))
    console.print(Group(*elems))
