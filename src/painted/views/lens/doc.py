"""Doc lens: a document node tree projected to a Block.

This is the *terminal* projector of the doc-IR (`to_block` in the taxonomy of
``docs/DOC_IR_DESIGN.md``). The same node tree is also read by the *publishers*
``to_html`` / ``to_markdown`` that live in ``tools/`` — but those emit foreign
(web/markdown) semantics, while this one lands in painted's own ``Block`` type,
which is what makes it a lens and keeps it in the library.

Disclosure is governed entirely by ``Fidelity`` (``core/fidelity.py``): no node
carries a bespoke zoom primitive. A node appears iff

    fidelity.depth >= node.min_depth  AND  (node.tag is None or fidelity.shows(node.tag))

``min_depth`` is the coarse ``-v``/``-vv`` ladder; ``tag`` is an opt-in semantic
layer (``--show rationale``). Disclosure reveals or hides whole nodes — it never
rewrites prose.

Status: provisional. These names are intentionally NOT exported from
``painted.views.__all__`` until validated against both help and a real guide.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...core._text_width import display_width
from ...core.block import Block, Wrap
from ...core.cell import Cell, Style
from ...core.compose import join_vertical, pad
from ...core.fidelity import Fidelity
from ...core.zoom import Zoom

# Inline content. The first cut accepts only plain ``str``; the rich union
# (Text / Emphasis / CodeSpan / Link) lands when prose guides come into scope.
Inline = str


# =============================================================================
# Node vocabulary
# =============================================================================
#
# Frozen dataclasses (project invariant). The repeated ``min_depth`` / ``tag``
# pair IS the Fidelity disclosure contract applied uniformly — it is the spine,
# not boilerplate. ``Doc`` (root) and ``Def`` (a row within ``Defs``) are the two
# shapes that do not carry disclosure of their own.


@dataclass(frozen=True, slots=True)
class Doc:
    """Document root."""

    title: str | None
    body: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Section:
    """A heading + nested body. Sections nest; heading level is the tree depth,
    not a stored field."""

    heading: str | None  # help groups can be unnamed ("")
    body: tuple[Node, ...]
    hint: str | None = None  # help's "(what to show)" subhead
    min_depth: int = 0
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class Prose:
    """A paragraph. Wraps to width (word-wrap) when a width is given."""

    content: Inline
    min_depth: int = 0
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class Def:
    """A definition-list entry — subsumes the old ``HelpFlag`` with the term
    kept intact (no lossy downcast). ``detail`` is revealed at depth >= DETAILED."""

    term: str  # "-v, --verbose"
    summary: Inline
    detail: Inline | None = None


@dataclass(frozen=True, slots=True)
class Defs:
    """A definition list (term + summary rows)."""

    items: tuple[Def, ...]
    min_depth: int = 0
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class Items:
    """A flat bullet/number list (``Defs`` is for term+description)."""

    entries: tuple[Inline, ...]
    ordered: bool = False
    min_depth: int = 0
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class Code:
    """A code block. Either inline ``text`` or a docgen ``ref`` (resolution is a
    deferred seam — for now an unresolved ref renders as a placeholder)."""

    text: str | None = None
    ref: str | None = None  # e.g. "py:painted.cell:Style#definition"
    lang: str = "python"
    min_depth: int = 0
    tag: str | None = None


@dataclass(frozen=True, slots=True)
class Figure:
    """Embed a live-rendered ``Block`` — the node that makes doc == demo. This is
    the only node the HTML publisher routes through ``Block -> HTML``."""

    block: Block
    caption: str | None = None
    min_depth: int = 0
    tag: str | None = None


# Block-level nodes (Doc is the root, not a body node).
Node = Section | Prose | Defs | Items | Code | Figure


# =============================================================================
# Disclosure
# =============================================================================

_INDENT = 2  # spaces a Section indents its body
_BULLET = "- "


def _visible(node: Node, fidelity: Fidelity) -> bool:
    """The shared disclosure predicate (see module docstring)."""
    if fidelity.depth < node.min_depth:
        return False
    if node.tag is not None and not fidelity.shows(node.tag):
        return False
    return True


def _cap(n: int, limit: int) -> int:
    """Apply a Fidelity line/item budget (0 == unlimited)."""
    return n if limit <= 0 else min(n, limit)


# =============================================================================
# Projection: doc node tree -> Block
# =============================================================================


def doc_lens(
    doc: Doc,
    *,
    fidelity: Fidelity = Fidelity(),
    width: int | None = None,
) -> Block:
    """Project a ``Doc`` to a ``Block`` (the ``to_block`` projector).

    Args:
        doc: The document node tree.
        fidelity: Disclosure spec (depth / visible tags / density budgets).
        width: Available width in columns. ``None`` renders at natural width
            (prose stays single-line). A given width is honored exactly per the
            width contract; prose word-wraps to it.
    """
    blocks: list[Block] = []
    if doc.title:
        blocks.append(_line(doc.title, Style(bold=True), width))
    body = _render_body(doc.body, fidelity, width)
    if body is not None:
        blocks.append(body)
    if not blocks:
        return Block.empty(width or 0, 0)
    return join_vertical(*blocks, gap=1)


def _render_body(
    nodes: tuple[Node, ...],
    fidelity: Fidelity,
    width: int | None,
) -> Block | None:
    """Join the visible body nodes vertically, a blank line between each."""
    rendered = [_render_node(node, fidelity, width) for node in nodes if _visible(node, fidelity)]
    if not rendered:
        return None
    return join_vertical(*rendered, gap=1)


def _render_node(node: Node, fidelity: Fidelity, width: int | None) -> Block:
    match node:
        case Section():
            return _render_section(node, fidelity, width)
        case Prose():
            return _line(node.content, Style(), width, wrap=Wrap.WORD)
        case Defs():
            return _render_defs(node, fidelity, width)
        case Items():
            return _render_items(node, fidelity, width)
        case Code():
            return _render_code(node, width)
        case Figure():
            return _render_figure(node)


def _render_section(section: Section, fidelity: Fidelity, width: int | None) -> Block:
    rows: list[Block] = []
    heading = section.heading or ""
    if section.hint:
        heading = f"{heading} {section.hint}" if heading else section.hint
    if heading:
        rows.append(_line(heading, Style(bold=True), width))

    body_width = None if width is None else max(0, width - _INDENT)
    body = _render_body(section.body, fidelity, body_width)
    if body is not None:
        rows.append(pad(body, left=_INDENT))

    if not rows:
        return Block.empty(width or 0, 0)
    return join_vertical(*rows, gap=0)


def _render_defs(defs: Defs, fidelity: Fidelity, width: int | None) -> Block:
    items = defs.items[: _cap(len(defs.items), fidelity.lines)] if fidelity.lines else defs.items
    if not items:
        return Block.empty(width or 0, 0)

    col = max(display_width(d.term) for d in items) + 2
    show_detail = fidelity.depth >= Zoom.DETAILED

    rows: list[Block] = []
    for d in items:
        term = d.term + " " * (col - display_width(d.term))
        rows.append(_line(f"{term}{d.summary}", Style(), width))
        if show_detail and d.detail:
            detail_width = None if width is None else max(0, width - col)
            rows.append(
                pad(_line(d.detail, Style(dim=True), detail_width, wrap=Wrap.WORD), left=col)
            )
    return join_vertical(*rows, gap=0)


def _render_items(items: Items, fidelity: Fidelity, width: int | None) -> Block:
    entries = items.entries[: _cap(len(items.entries), fidelity.lines)]
    if not entries:
        return Block.empty(width or 0, 0)
    rows: list[Block] = []
    for i, entry in enumerate(entries):
        marker = f"{i + 1}. " if items.ordered else _BULLET
        body_width = None if width is None else max(0, width - len(marker))
        line = pad(_line(entry, Style(), body_width, wrap=Wrap.WORD), left=len(marker))
        # Overwrite the leading pad with the marker on the first row.
        rows.append(_with_marker(line, marker))
    return join_vertical(*rows, gap=0)


def _render_code(code: Code, width: int | None) -> Block:
    if code.text is None:
        # Deferred docgen resolution — placeholder until the ref seam lands.
        label = f"[code: {code.ref}]" if code.ref else "[code]"
        return _line(label, Style(dim=True), width)
    lines = code.text.split("\n")
    return join_vertical(*(_line(ln, Style(), width) for ln in lines), gap=0)


def _render_figure(fig: Figure) -> Block:
    if fig.caption:
        return join_vertical(fig.block, _line(fig.caption, Style(dim=True), fig.block.width), gap=0)
    return fig.block


# =============================================================================
# Helpers
# =============================================================================


def _line(text: str, style: Style, width: int | None, *, wrap: Wrap = Wrap.NONE) -> Block:
    """A text block: natural when width is None, else honoring width exactly."""
    if width is None:
        return Block.text(text, style)
    return Block.text(text, style, width=width, wrap=wrap)


def _with_marker(block: Block, marker: str) -> Block:
    """Stamp a list marker onto the first row of an already-indented block."""
    cells = list(block.row(0))
    for i, ch in enumerate(marker):
        if i < len(cells):
            cells[i] = Cell(ch, cells[i].style)
    rows = [tuple(cells), *(block.row(r) for r in range(1, block.height))]
    return Block(rows, block.width)
