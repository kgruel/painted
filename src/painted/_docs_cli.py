"""Docs command: render in-code documents to the terminal via the doc lens.

The front door for the doc-IR (``docs/DOC_IR_DESIGN.md``). Each doc is authored
as a Block-producing node tree and rendered through ``run_cli`` — so ``-v``/``-vv``
map to ``Fidelity.depth`` and ``--show <tag>`` populates ``Fidelity.visible``, the
same Fidelity that drives every other painted surface. The terminal sink here and
the (future) HTML publisher read the *same* tree.

This is an early seam: one doc, prose authored as plain ``str`` (the rich Inline
union and ``Code(ref=...)`` docgen resolution are the next fill-ins — see the
design doc). Render it: ``painted docs primitives -v --show rationale``.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

from painted import Block, Style, join_vertical, print_block, run_cli
from painted.cli import OutputMode
from painted.core.fidelity import Fidelity
from painted.views.lens.doc import (
    Code,
    Def,
    Defs,
    Doc,
    Figure,
    Prose,
    Section,
    doc_lens,
)


@dataclass(frozen=True)
class DocEntry:
    name: str
    description: str
    build: Callable[[], Doc]


# ---------------------------------------------------------------------------
# Content (authored as code — the whole point)
# ---------------------------------------------------------------------------


def _style_gallery() -> Block:
    """A genuine Figure: Style attributes rendered live from the real API."""
    return join_vertical(
        Block.text("bold", Style(bold=True)),
        Block.text("red", Style(fg="red")),
        Block.text("green", Style(fg="green")),
        Block.text("blue", Style(fg="blue")),
        Block.text("dim italic", Style(dim=True, italic=True)),
        Block.text("reverse cyan", Style(fg="cyan", reverse=True)),
    )


def _primitives_doc() -> Doc:
    return Doc(
        title="Primitives and Blocks",
        body=(
            Prose(
                "painted is built from a small set of immutable render-layer value "
                "types. These are the inputs to every higher-level feature — "
                "composition, buffers, the TUI, widgets."
            ),
            Defs(
                (
                    Def("Primitives", "Style, Cell, Span, Line"),
                    Def("Rectangles", "Block"),
                )
            ),
            Section(
                "Style",
                body=(
                    Prose(
                        "Style is an immutable bundle of attributes — colors plus "
                        "bold/italic/underline/reverse/dim. Styles combine via "
                        "merge(), where the overlay wins."
                    ),
                    Code(
                        text="base = Style(fg='blue', bold=True)\nmerged = base.merge(Style(italic=True))"
                    ),
                    Figure(_style_gallery(), caption="Style attributes, rendered live"),
                ),
            ),
            Section(
                "Cell",
                body=(
                    Prose(
                        "Cell is the atom: one character plus one Style. Most code "
                        "manipulates Blocks rather than individual cells."
                    ),
                ),
            ),
            Section(
                "Span and Line",
                body=(
                    Prose(
                        "Span is text plus Style, measured in display columns "
                        "(wide-char aware). A Line is a tuple of spans that paints "
                        "into a buffer or converts to a Block."
                    ),
                ),
            ),
            Section(
                "Why this matters",
                min_depth=2,
                body=(
                    Prose(
                        "painted pushes complexity up the stack: these immutable "
                        "values are safe to share and cache, so higher-level systems "
                        "treat rendering as a pure transformation — state to blocks."
                    ),
                ),
            ),
            Section(
                "Design note",
                tag="rationale",
                body=(
                    Prose(
                        "This page is itself a doc-IR node tree. The terminal you are "
                        "reading it in and the docs site render the same tree through "
                        "different projectors — so the docs cannot drift from the code."
                    ),
                ),
            ),
        ),
    )


_DOCS: dict[str, DocEntry] = {
    "primitives": DocEntry(
        "primitives",
        "The render-layer value types: Style, Cell, Span, Line, Block",
        _primitives_doc,
    ),
}


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def list_docs(_args: list[str]) -> int:
    rows = [Block.text("Available docs", Style(bold=True)), Block.text(" ", Style())]
    for entry in _DOCS.values():
        rows.append(Block.text(f"  {entry.name:<14}{entry.description}", Style()))
    rows.append(Block.text(" ", Style()))
    rows.append(
        Block.text(
            "Run painted docs <name> [-v|-vv] [--show <tag>]",
            Style(dim=True),
        )
    )
    print_block(join_vertical(*rows))
    return 0


def run_doc(name: str, args: list[str]) -> int:
    entry = _DOCS.get(name)
    if entry is None:
        print_block(Block.text(f"Unknown doc: {name}", Style(fg="red")))
        list_docs([])
        return 1

    doc = entry.build()

    def _add_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--show",
            action="append",
            default=[],
            metavar="TAG",
            help="Reveal a tagged layer (e.g. rationale)",
        )

    def _build_fidelity(parsed: argparse.Namespace, fid: Fidelity) -> Fidelity:
        tags = getattr(parsed, "show", None) or []
        return fid.with_visible(*tags) if tags else fid

    def render(ctx, d: Doc) -> Block:
        return doc_lens(d, fidelity=ctx.fidelity, width=ctx.width)

    return run_cli(
        args,
        render=render,
        fetch=lambda: doc,
        default_mode=OutputMode.STATIC,
        description=entry.description,
        prog=f"painted docs {name}",
        add_args=_add_args,
        build_fidelity=_build_fidelity,
    )
