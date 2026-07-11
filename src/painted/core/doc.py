"""The doc-IR: a document node tree, and ``doc_lens`` — its projection to a Block.

A **document compositor**, peer of ``compose.py``: where ``compose`` lays out raw
Blocks (join/pad/border), ``doc_lens`` lays out a *document* — a fixed vocabulary
painted defines (``Doc``/``Section``/``Defs``/``Def``/``Prose``/…) — into a Block.
It interprets a known structure, not arbitrary domain data, which is why it lives
in ``core`` beside the other structural primitives rather than in ``views`` with
the data lenses (``shape_lens``/``tree_lens``). Core placement is what lets the CLI
framework (help) and the ``painted docs`` front door both consume it without
``cli``/``views`` crossing their peer boundary.

This is the *terminal* projector of the doc-IR (`to_block` in the taxonomy of
``docs/DOC_IR_DESIGN.md``). The same node tree is also read by the *publisher*
``to_html`` (``painted/publish.py``) — it emits foreign (web) semantics, while
this one lands in painted's own ``Block`` type. Both projectors iterate bodies
through the one ``visible_body`` walk below, so they cannot disclose
differently. (``to_markdown`` is sketched in the design doc, not built.)

Disclosure is governed entirely by ``Fidelity`` (``core/fidelity.py``): no node
carries a bespoke zoom primitive. Each node renders at an *effective tier*

    eff = depth - node.min_depth          (hidden when eff < 0, or its tag is off)

where ``depth`` is the local ``-v``/``-vv`` budget and ``tag`` is an opt-in
semantic layer (a declared ``--rationale`` flag), checked against ``fidelity.visible``.
``eff`` is **relative**: a ``Section`` consumes its ``min_depth`` and passes the
remaining budget (its own ``eff``) down to its body as the local depth — so a
flag list nested under a group heading is one tier compacter than the same list
at the top level, without re-authoring ``min_depth`` on every child. This cascade
is what lets help's framework groups collapse to a terse line at the default view
while the command's own args stay expanded on the same screen.

``eff`` drives *density*, not re-authoring: a ``Defs`` shows terms-only at
``eff == 0``, term+summary columns at ``eff >= 1``, and adds ``Def.detail`` at
``eff >= 2`` — the same content, never written twice. Prose, items, code, figures,
and ``Section`` headings are binary (shown whenever ``eff >= 0``); only the list
density and the ``Section.hint`` subhead are tiered.

Status: validated against both help and a real guide (the primitives page, in
terminal and site form). At 0.10 the authoring seam settled (the Inline union,
``Link`` first) and the node vocabulary + ``doc_lens`` graduated into
``painted.core.__all__`` under the semver guard. The disclosure walk
(``visible_body``/``capped``) stays unexported: it is the mechanism that
guarantees the sinks disclose identically, and painted's two projectors are
its only sanctioned readers — a second out-of-package publisher is the
evidence that would export it.
"""

from __future__ import annotations

import warnings
from dataclasses import InitVar, dataclass
from typing import TypeVar

from ._text_width import display_width
from .block import Block, Wrap
from .cell import Cell, Style
from .compose import join_vertical, pad
from .errors import ContractError
from .fidelity import Fidelity
from .span import Line, Span


@dataclass(frozen=True, slots=True)
class Link:
    """An inline link: what the reader sees, and a ref naming what it denotes.

    ``target`` is a ref — ``"scheme:value"``, resolved through the declared
    ``RefScheme`` (docs/REFS_DESIGN.md). A ``Link`` rides the existing
    denotation channel, not a new one: ``doc_lens`` stamps ``target`` on the
    text's cells (the writer's OSC 8 emission and ``render_html``'s
    ``<a href>`` wrapping already honor it), and the ``to_html`` publisher
    resolves it through the same ``resolve_ref``. Identical inertness in both
    worlds: an undeclared scheme renders ``text`` as plain content — painted
    never invents URIs. (An absolute web URL is just a ref whose scheme the
    page declares.)
    """

    text: str
    target: str


# Inline content — settled at 0.10 (DOC_IR_DESIGN.md): a single text span, or
# a sequence of spans where plain ``str`` IS the text span and ``Link`` is the
# first rich member. ``Emphasis``/``CodeSpan`` stay unminted until a consumer
# demonstrates need; adding a union member is additive.
Inline = str | tuple[str | Link, ...]

_T = TypeVar("_T")


def inline_spans(content: Inline) -> tuple[str | Link, ...]:
    """Normalize ``Inline`` to its span sequence — THE shared inline walk.

    Both projectors (``doc_lens`` here, the ``to_html`` publisher) iterate
    inline content through this one function, the ``visible_body`` pattern
    applied to spans: written once, so two sinks cannot render a span
    differently.
    """
    if isinstance(content, str):
        return (content,)
    return content


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


# Sentinel for the deprecated ``Code(ref=)`` alias: an InitVar so it is passed to
# ``__post_init__`` and never stored, distinguishing "not passed" from ``None``.
_CODE_REF_UNSET: object = object()


@dataclass(frozen=True, slots=True)
class Code:
    """A code block. Either inline ``text`` or a docgen ``src`` locator (resolution
    is a deferred seam — for now an unresolved locator renders as a placeholder)."""

    text: str | None = None
    src: str | None = None  # e.g. "py:painted.cell:Style#definition"
    lang: str = "python"
    min_depth: int = 0
    tag: str | None = None
    # Deprecated alias for ``src`` (removed at 1.0). InitVar: accepted at
    # construction, folded into ``src``, never stored as its own attribute.
    ref: InitVar[object] = _CODE_REF_UNSET

    def __post_init__(self, ref: object) -> None:
        if ref is not _CODE_REF_UNSET:
            if self.src is not None:
                raise ContractError("pass src=, not both src= and the deprecated ref= (Code)")
            warnings.warn(
                "Code(ref=) is deprecated; use Code(src=) (removed at 1.0)",
                DeprecationWarning,
                stacklevel=3,
            )
            object.__setattr__(self, "src", ref)


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


def _eff(node: Node, depth: int, fidelity: Fidelity) -> int | None:
    """The node's effective render tier, or ``None`` if it is hidden.

    ``depth`` is the *local* budget (the parent ``Section``'s ``eff``, or
    ``fidelity.depth`` at the root). ``tag`` is checked against the absolute
    ``fidelity.visible`` set — semantic layers are not relative.
    """
    if node.tag is not None and not fidelity.shows(node.tag):
        return None
    eff = depth - node.min_depth
    return eff if eff >= 0 else None


def visible_body(
    nodes: tuple[Node, ...], depth: int, fidelity: Fidelity
) -> tuple[tuple[Node, int], ...]:
    """The visible nodes of a body, each paired with its effective tier.

    THE shared disclosure walk: every projector — ``doc_lens`` here, the
    ``to_html`` publisher in ``painted/publish.py`` — iterates bodies through this one
    function, so the cascade is written exactly once and two sinks cannot
    disclose differently. The cascade rule for callers: when a ``Section``
    renders its body, pass the Section's own ``eff`` as the body's ``depth``.
    """
    return tuple((node, eff) for node in nodes if (eff := _eff(node, depth, fidelity)) is not None)


def capped(items: tuple[_T, ...], fidelity: Fidelity) -> tuple[_T, ...]:
    """Apply the Fidelity ``lines`` budget (0 == unlimited) to a node's items.

    Truncation is deliberately *silent* (no "+N more" row): the budget is the
    consumer's explicit ask for that much and no more, and both projectors
    must drop the same tail.
    """
    return items if fidelity.lines <= 0 else items[: fidelity.lines]


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
    body = _render_body(doc.body, fidelity.depth, fidelity, width)
    if body is not None:
        blocks.append(body)
    if not blocks:
        return Block.empty(width or 0, 0)
    return join_vertical(*blocks, gap=1)


def _render_body(
    nodes: tuple[Node, ...],
    depth: int,
    fidelity: Fidelity,
    width: int | None,
) -> Block | None:
    """Join the visible body nodes vertically, a blank line between each.

    ``depth`` is the local budget; each node's tier is ``depth - node.min_depth``.
    """
    rendered = [
        (eff, _render_node(node, eff, fidelity, width))
        for node, eff in visible_body(nodes, depth, fidelity)
    ]
    if not rendered:
        return None
    # A blank line separates nodes, except between two adjacent compact-tier
    # (eff == 0) siblings — those pack tightly, terse by definition (the default
    # help screen's framework groups).
    result = rendered[0][1]
    for (prev_eff, _), (eff, block) in zip(rendered, rendered[1:]):
        gap = 0 if prev_eff == 0 and eff == 0 else 1
        result = join_vertical(result, block, gap=gap)
    return result


def _render_node(node: Node, eff: int, fidelity: Fidelity, width: int | None) -> Block:
    match node:
        case Section():
            return _render_section(node, eff, fidelity, width)
        case Prose():
            return _line(node.content, Style(), width, wrap=Wrap.WORD)
        case Defs():
            return _render_defs(node, eff, fidelity, width)
        case Items():
            return _render_items(node, fidelity, width)
        case Code():
            return _render_code(node, width)
        case Figure():
            return _render_figure(node, width)


def _render_section(section: Section, eff: int, fidelity: Fidelity, width: int | None) -> Block:
    rows: list[Block] = []
    heading = section.heading or ""
    if section.hint and eff >= 1:  # the subhead is a tier-1 reveal, like a flag's columns
        heading = f"{heading} {section.hint}" if heading else section.hint
    if heading:
        rows.append(_line(heading, Style(bold=True), width))

    body_width = None if width is None else max(0, width - _INDENT)
    # Cascade: the section's own eff becomes the local depth budget for its body.
    body = _render_body(section.body, eff, fidelity, body_width)
    if body is not None:
        rows.append(pad(body, left=_INDENT))

    if not rows:
        return Block.empty(width or 0, 0)
    return join_vertical(*rows, gap=0)


def _render_defs(defs: Defs, eff: int, fidelity: Fidelity, width: int | None) -> Block:
    items = capped(defs.items, fidelity)
    if not items:
        return Block.empty(width or 0, 0)

    if eff == 0:
        # Compact tier: terms only, flowed to width (the terse default-help line).
        text = "  ".join(d.term for d in items)
        return _line(text, Style(dim=True), width, wrap=Wrap.WORD)

    col = max(display_width(d.term) for d in items) + 2
    show_detail = eff >= 2

    rows: list[Block] = []
    for d in items:
        term = d.term + " " * (col - display_width(d.term))
        rows.append(_line(d.summary, Style(), width, lead=term))
        if show_detail and d.detail:
            detail_width = None if width is None else max(0, width - col)
            rows.append(
                pad(_line(d.detail, Style(dim=True), detail_width, wrap=Wrap.WORD), left=col)
            )
    return join_vertical(*rows, gap=0)


def _render_items(items: Items, fidelity: Fidelity, width: int | None) -> Block:
    entries = capped(items.entries, fidelity)
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
        # Deferred docgen resolution — placeholder until the src seam lands.
        label = f"[code: {code.src}]" if code.src else "[code]"
        return _line(label, Style(dim=True), width)
    lines = code.text.split("\n")
    return join_vertical(*(_line(ln, Style(), width) for ln in lines), gap=0)


def _render_figure(fig: Figure, width: int | None) -> Block:
    if fig.caption:
        # Caption renders at the available width, not the (often narrower) block's.
        caption = _line(fig.caption, Style(dim=True), width, wrap=Wrap.WORD)
        return join_vertical(fig.block, caption, gap=0)
    return fig.block


# =============================================================================
# Helpers
# =============================================================================


def _spans(content: Inline, style: Style) -> tuple[Span, ...]:
    """Inline content as styled Spans — a Link's target rides as the span ref.

    The lens half of the shared walk: every span comes through
    ``inline_spans``, and a ``Link`` renders its ``text`` with ``ref=target``
    stamped on the cells (the delivery layers resolve it — OSC 8 in ANSI,
    ``<a href>`` in ``render_html``). No styling: link color is the
    delivery's concern (REFS_DESIGN §4).
    """
    return tuple(
        Span(s.text, style, ref=s.target) if isinstance(s, Link) else Span(s, style)
        for s in inline_spans(content)
    )


def _line(
    content: Inline, style: Style, width: int | None, *, wrap: Wrap = Wrap.NONE, lead: str = ""
) -> Block:
    """A text block: natural when width is None, else honoring width exactly.

    ``content`` is any Inline; ``lead`` is a same-style prefix (the Defs term
    column) that participates in the width budget like the content itself.
    Plain ``str`` keeps the single-style ``Block.text`` path; a span tuple
    renders through ``Line`` so each span's ref rides its cells.
    """
    if isinstance(content, str):
        text = lead + content
        if width is None:
            return Block.text(text, style)
        return Block.text(text, style, width=width, wrap=wrap)
    spans = (Span(lead, style),) if lead else ()
    line = Line(spans + _spans(content, style))
    if width is None:
        return line.to_block(line.width)
    return line.wrap(width, wrap=wrap)


def _with_marker(block: Block, marker: str) -> Block:
    """Stamp a list marker onto the first row of an already-indented block.

    The ref channel rides through: the marker lands on left-pad cells (which
    denote nothing), and every content cell keeps its ref."""
    cells = list(block.row(0))
    for i, ch in enumerate(marker):
        if i < len(cells):
            cells[i] = Cell(ch, cells[i].style)
    rows = [tuple(cells), *(block.row(r) for r in range(1, block.height))]
    return Block(rows, block.width, ref=block.ref, refs=block._refs)
