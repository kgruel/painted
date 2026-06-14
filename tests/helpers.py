"""Shared helpers for tests.

These are intentionally lightweight and dependency-free (beyond painted itself),
and are used across unit + golden tests to avoid copy-pasting utilities.
"""

from __future__ import annotations

import io

from painted import Block, Cell, CliContext, Fidelity, Style, Zoom
from painted.cli import OutputMode
from painted.core.writer import print_block


def static_ctx(
    zoom: Zoom, *, visible: tuple[str, ...] = (), lines: int = 0, chars: int = 0
) -> CliContext:
    """Build a deterministic CliContext for golden/snapshot testing.

    ``visible`` sets fidelity facets explicitly — this harness builds the
    spec directly, so tag implications are the caller's to state (use
    ``painted.cli.implied_visible`` to mirror what the CLI would compile).
    ``lines``/``chars`` set the density budget (the ``--max-lines``/``--max-chars``
    ceilings); 0 leaves that dimension unlimited.
    """
    return CliContext(
        fidelity=Fidelity(depth=int(zoom), visible=frozenset(visible), lines=lines, chars=chars),
        mode=OutputMode.STATIC,
        use_ansi=False,
        is_tty=False,
        width=80,
        height=24,
    )


def block_to_text(block: Block, *, use_ansi: bool = False) -> str:
    """Render a Block into plain text (or ANSI) via painted.writer.print_block()."""
    buf = io.StringIO()
    print_block(block, buf, use_ansi=use_ansi)
    return buf.getvalue()


def row_text(block: Block, row_idx: int) -> str:
    """Return the characters for a single block row."""
    return "".join(c.char for c in block.row(row_idx))


def text_block(lines: list[str], style: Style | None = None, *, id: str | None = None) -> Block:
    """Build a Block from text lines, padding rows to uniform width."""
    style = style or Style()
    width = max((len(ln) for ln in lines), default=0)
    rows: list[list[Cell]] = []
    for line in lines:
        row = [Cell(ch, style) for ch in line]
        row += [Cell(" ", style)] * (width - len(line))
        rows.append(row)
    return Block(rows, width, id=id)
