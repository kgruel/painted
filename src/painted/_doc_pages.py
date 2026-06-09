"""Authored doc-IR pages: the node trees behind ``painted docs`` and the site.

Content lives here — a neutral module — rather than in the CLI dispatch
(``_docs_cli.py``) because TWO consumers read the same trees: the terminal front
door (``painted docs <name>`` via ``doc_lens``) and the site publisher
(``tools/doc_publish.py`` via ``to_html``). That shared readership is the doc-IR
thesis (``docs/DOC_IR_DESIGN.md``): one tree, projected per medium, so the docs
cannot drift from the code. A page is authored as code on purpose — its
``Figure`` nodes embed live-rendered Blocks from the real API (doc == demo).

Private module: the node vocabulary is still provisional (not in
``core.__all__``), so the pages that use it stay out of the public surface too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from painted import Block, Style, join_vertical
from painted.core.doc import (
    Code,
    Def,
    Defs,
    Doc,
    Figure,
    Prose,
    Section,
)


@dataclass(frozen=True)
class DocEntry:
    name: str
    description: str
    build: Callable[[], Doc]


# ---------------------------------------------------------------------------
# Pages (authored as code — the whole point)
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


def primitives_doc() -> Doc:
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


DOCS: dict[str, DocEntry] = {
    "primitives": DocEntry(
        "primitives",
        "The render-layer value types: Style, Cell, Span, Line, Block",
        primitives_doc,
    ),
}
