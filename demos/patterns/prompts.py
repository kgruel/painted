#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Declared prompts — the DECLARED rung's real output, as content.

`--force` and `Are you sure? [y/N]` are the same declaration at different
fidelities (docs/PROMPTS_DESIGN.md): one resolves from argv, one resolves
interactively at a TTY. This demo never opens a terminal prompt — it renders
what the DECLARED rung produces on its own, non-interactively, the way a
script or a CI run sees it: a declared default resolving with one record
line of proof, and an honest refusal naming the flag that would answer it.
No fabricated text — every line below is real output captured from the
real resolver (`PromptSession`), the same one `ctx.ask` delegates to.

    uv run demos/patterns/prompts.py       # rung 1: the two default record lines
    uv run demos/patterns/prompts.py -v    # rung 2: + the real refusal text
    uv run demos/patterns/prompts.py -vv   # rung 3: + the resolution ladder
"""

from __future__ import annotations

import contextlib
import io
import sys
from dataclasses import dataclass

from painted import Block, CliContext, Style, Zoom, join_vertical, run_cli, truncate
from painted.cli import Confirm, Select
from painted.cli.prompts import PromptSession

# --- Declarations the demo resolves — never rendered interactively, only
# their non-interactive DECLARED-rung output is (§12 step 6: prompts are a
# rung, not a drive — no walkthrough stage, no live prompt on this CLI). ---

_DEFAULTED = [
    Confirm("force", "Force overwrite?", default=False),
    Select("scope", "Which store?", values=("local", "config", "all"), default="local"),
]

_UNDECLARED_DEFAULT = Confirm("overwrite", "Overwrite existing files?")


# --- Data model ---


@dataclass(frozen=True)
class PromptsData:
    record_lines: tuple[str, ...]
    refusal: str


def _record_lines() -> tuple[str, ...]:
    """Real record lines: no flag, no TTY — each declared default resolves
    and leaves one line of proof, exactly what a CI run would see on stderr."""
    session = PromptSession(_DEFAULTED, {}, stdin_tty=False, stderr_tty=False)
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        session.ask("force")
        session.ask("scope")
    return tuple(line for line in captured.getvalue().splitlines() if line)


def _refusal() -> str:
    """The real ContractError text: no flag, no default, stdin not a
    terminal — the honest refusal that names the flag (design §3 rule 3)."""
    session = PromptSession([_UNDECLARED_DEFAULT], {}, stdin_tty=False)
    try:
        session.ask("overwrite")
        return ""
    except Exception as exc:
        return str(exc)


def _fetch() -> PromptsData:
    return PromptsData(record_lines=_record_lines(), refusal=_refusal())


# --- Rendering ---


def _render(ctx: CliContext, data: PromptsData) -> Block:
    if ctx.zoom < Zoom.SUMMARY:
        summary = "  ".join(data.record_lines) or "no defaults resolved"
        return truncate(Block.text(summary, Style(dim=True)), ctx.width)

    rows: list[Block] = [
        Block.text("Declared prompts resolve without a human", Style(bold=True)),
        Block.text("", Style()),
    ]
    rows.extend(Block.text(f"  {line}", Style()) for line in data.record_lines)

    if ctx.zoom >= Zoom.DETAILED:
        rows.append(Block.text("", Style()))
        rows.append(Block.text("No flag, no default, stdin not a terminal:", Style(bold=True)))
        rows.append(Block.text(f"  {data.refusal}", Style(fg="red")))

    if ctx.zoom >= Zoom.FULL:
        rows.append(Block.text("", Style()))
        rows.append(
            Block.text(
                "Resolution ladder: argv flag -> prompt at a TTY -> declared default -> "
                "ContractError naming the flag.",
                Style(dim=True),
            )
        )

    return truncate(join_vertical(*rows), ctx.width)


def main() -> int:
    return run_cli(
        sys.argv[1:],
        render=_render,
        fetch=_fetch,
        description=__doc__,
        prog="prompts.py",
    )


if __name__ == "__main__":
    sys.exit(main())
