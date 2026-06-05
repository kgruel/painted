#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Help is a document — authored as a doc-IR node tree, projected at each zoom.

There is no bespoke help renderer: a help screen is a ``Doc`` (title, prose,
definition lists) and the zoom level picks how much of it shows. The same
``doc_lens`` projector drives ``painted docs`` and painted's own ``--help``.
Disclosure is a tier — ``eff = depth - min_depth`` — so framework groups gated
at ``min_depth=SUMMARY`` collapse to a terse names line at the default view and
expand as you add -v.

    uv run demos/patterns/help.py -q           # one-line summary
    uv run demos/patterns/help.py              # sample help at SUMMARY
    uv run demos/patterns/help.py -v           # sample help at DETAILED
    uv run demos/patterns/help.py -vv          # SUMMARY and DETAILED side by side
    uv run demos/patterns/help.py --help       # this demo's own zoom-aware help
    uv run demos/patterns/help.py --help -v    # ...with more detail
"""

from __future__ import annotations

import sys

from painted import (
    Block,
    CliContext,
    Style,
    Zoom,
    border,
    join_horizontal,
    join_vertical,
    pad,
    run_cli,
    truncate,
    ROUNDED,
)
from painted.core.doc import Def, Defs, Doc, Prose, Section, doc_lens
from painted.core.fidelity import Fidelity


# --- Sample help, authored as a document (a hypothetical full-featured CLI) ---


def _flag(short: str | None, long: str | None, summary: str, detail: str | None = None) -> Def:
    term = ", ".join(p for p in (short, long) if p)
    return Def(term=term, summary=summary, detail=detail)


def _group(heading: str, hint: str, detail: str, flags: tuple[Def, ...]) -> Section:
    # min_depth=SUMMARY: the group is terse at the default view, expands at -v;
    # its detail prose (min_depth=2, relative) appears only at -vv.
    return Section(
        heading,
        hint=hint,
        min_depth=Zoom.SUMMARY,
        body=(Prose(detail, min_depth=2), Defs(flags)),
    )


SAMPLE_HELP = Doc(
    title="deploy",
    body=(
        Prose("Ship services to production."),
        _group(
            "Zoom",
            "(what to show)",
            "Controls how much detail is rendered. Stackable: -v for detailed, -vv for full.",
            (
                _flag("-q", "--quiet", "Minimal output"),
                _flag("-v", "--verbose", "Detailed (-v) or full (-vv)"),
            ),
        ),
        _group(
            "Mode",
            "(how to deliver)",
            "Delivery mechanism. AUTO selects LIVE for TTY, STATIC for pipes.",
            (
                _flag("-i", "--interactive", "Interactive TUI"),
                _flag(None, "--static", "Static output, no animation"),
                _flag(None, "--live", "Live output with in-place updates"),
            ),
        ),
        _group(
            "Format",
            "(serialization)",
            "Output serialization. ANSI is default for TTY, PLAIN for pipes.",
            (
                _flag(None, "--json", "JSON output", "Implies --static."),
                _flag(None, "--plain", "Plain text, no ANSI codes", "Implies --static when piped."),
            ),
        ),
        Section(
            "Help",
            min_depth=Zoom.SUMMARY,
            body=(Defs((_flag("-h", "--help", "Show this help", "Add -v for more detail."),)),),
        ),
    ),
)


def _render_doc(doc: Doc, depth: Zoom, width: int) -> Block:
    return doc_lens(doc, fidelity=Fidelity(depth=int(depth)), width=width)


# --- Render functions (the demo renders the sample at several zooms) ---


def render_minimal(doc: Doc, width: int) -> Block:
    """One-line: program name + flag count."""
    groups = [n for n in doc.body if isinstance(n, Section)]
    flag_count = sum(len(d.items) for g in groups for d in g.body if isinstance(d, Defs))
    names = ", ".join(g.heading.lower() for g in groups if g.heading)
    desc = next((n.content for n in doc.body if isinstance(n, Prose)), "")
    label = f"{doc.title} — {desc} ({flag_count} flags: {names})"
    return truncate(Block.text(label, Style()), width)


def render_at(doc: Doc, depth: Zoom, width: int, label: str) -> Block:
    """Show the sample help rendered at one zoom, under a dim caption."""
    return join_vertical(
        Block.text(label, Style(dim=True)),
        Block.text("", Style()),
        _render_doc(doc, depth, width),
    )


def render_full(doc: Doc, width: int) -> Block:
    """Side-by-side: SUMMARY vs DETAILED."""
    col_width = max(30, (width - 3) // 2)
    summary_block = _render_doc(doc, Zoom.SUMMARY, col_width)
    detailed_block = _render_doc(doc, Zoom.DETAILED, col_width)

    summary_box = border(
        pad(summary_block, right=max(0, col_width - 2 - summary_block.width)),
        title="--help",
        chars=ROUNDED,
    )
    detailed_box = border(
        pad(detailed_block, right=max(0, col_width - 2 - detailed_block.width)),
        title="--help -v",
        chars=ROUNDED,
    )

    return join_vertical(
        Block.text("SUMMARY vs DETAILED:", Style(dim=True)),
        Block.text("", Style()),
        join_horizontal(summary_box, Block.text(" ", Style()), detailed_box),
    )


# --- run_cli integration ---


def _fetch() -> Doc:
    return SAMPLE_HELP


def _render(ctx: CliContext, doc: Doc) -> Block:
    if ctx.zoom == Zoom.MINIMAL:
        return render_minimal(doc, ctx.width)
    if ctx.zoom == Zoom.SUMMARY:
        return render_at(doc, Zoom.SUMMARY, ctx.width, "Help at default zoom:")
    if ctx.zoom == Zoom.FULL:
        return render_full(doc, ctx.width)
    return render_at(doc, Zoom.DETAILED, ctx.width, "Help at --help -v:")


def main() -> int:
    return run_cli(
        sys.argv[1:],
        render=_render,
        fetch=_fetch,
        description=__doc__,
        prog="help.py",
    )


if __name__ == "__main__":
    sys.exit(main())
