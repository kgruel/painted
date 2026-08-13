"""The wall plaque — a showcase's maker note, rendered like a museum label.

Two showcases arrived at the same shape independently (harmonograph, then
mandelbrot): a titled panel of prose, signed, disclosed behind a named facet,
degrading to a marker when the delivery is too narrow to hold it. This is that
shape, extracted once, so a third showcase inherits it instead of re-deriving
it — and so the *conventions* around it stop living in review vigilance:

  - ``NOTE_TAG`` is the shared declaration. A note is named-only, never
    implied by depth: depth is anonymous detail about the *subject*, and who
    made a thing is not more detail about it. Because every showcase takes the
    same ``Tag`` object, that ruling cannot drift one demo at a time.
  - ``MAX_NOTE_*`` caps the note. A maker's note is a label, not an essay;
    the cap is derived, not picked (see the constants).
  - The signature is right-aligned under the prose, em-dashed. One place.

Disclosure is *not* re-implemented here. The doc-IR nodes carry their own
``tag``/``min_depth`` and ``doc_lens`` runs the one shared disclosure walk
(``painted.core.doc.visible_body``) — this module only asks that walk what
survived, and uses the answer for both the render and the too-narrow marker.

Not a library API: this is curriculum chrome, private to ``demos/showcase/``.
Import it as a sibling (``from _plaque import Plaque``) — the demo loaders put
a demo's own directory on ``sys.path``, so that resolves under ``uv run``,
``painted demos <name>``, the liveness smoke, and ``tools/capture.py`` alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from painted import Block, Fidelity, Line, Span, Style, Wrap, fit_to_width, join_vertical, pad
from painted.capabilities import current_capabilities
from painted.cli import Tag
from painted.core.doc import Doc, Prose, Section, doc_lens, visible_body
from painted.core.errors import DeclarationError
from painted.palette import current_palette

__all__ = [
    "MAX_NOTE_CHARS",
    "MAX_NOTE_PARAGRAPHS",
    "MIN_PLAQUE_WIDTH",
    "NOTE_TAG",
    "Plaque",
    "render_plaque",
]


# --- The declaration ---

# Named-only, by ruling: `--note` at any depth, implied at none. Every showcase
# imports *this object*, so the convention is encoded rather than remembered
# (the ratchet in tests/unit/test_plaque.py holds the shape).
NOTE_TAG = Tag("note", "Show the maker's note")

# A note is a label, not an essay. Both numbers are derived, not taste:
# MAX_NOTE_CHARS is the largest note that still renders inside 24 rows at the
# 66-column natural plate width — one standard terminal, and no taller than the
# work it annotates. test_longest_legal_note_fits_one_screen pins the
# derivation, so raising the cap fails the gate rather than silently sprawling.
MAX_NOTE_PARAGRAPHS = 3
MAX_NOTE_CHARS = 1100

# Below this the prose column is under ~24 columns and word-wrap degenerates
# into a ragged stack. The plaque withholds itself and says so (law 6).
MIN_PLAQUE_WIDTH = 28

_MARGIN = 2  # the label's left margin


@dataclass(frozen=True)
class Plaque:
    """A maker's note, plus whatever else the demo wants under the same label.

    ``sections`` is doc-IR passed straight through to the body — a showcase
    with a score or a stats table (harmonograph has both) hangs them here and
    they disclose behind their own ``tag``/``min_depth``, through the same
    walk. A showcase whose facts belong *inside* the frame — mandelbrot reads
    its legend and ledger as captions on the picture, not as wall text —
    leaves it empty.
    """

    title: str
    note: tuple[str, ...]  # paragraphs
    maker: str
    sections: tuple[Section, ...] = field(default=())

    def __post_init__(self) -> None:
        # DeclarationError, not ContractError: a plaque is *declared* at module
        # import, so a malformed one fires before any rendering happens.
        if not self.title.strip():
            raise DeclarationError("Plaque.title is empty — a note needs a name")
        if not self.note:
            raise DeclarationError("Plaque.note is empty — declare paragraphs or drop the plaque")
        if any(not p.strip() for p in self.note):
            raise DeclarationError("Plaque.note has a blank paragraph")
        if not self.maker.strip():
            raise DeclarationError("Plaque.maker is empty — an unsigned note is not a plaque")
        if len(self.note) > MAX_NOTE_PARAGRAPHS:
            raise DeclarationError(
                f"Plaque.note has {len(self.note)} paragraphs; the cap is {MAX_NOTE_PARAGRAPHS}"
            )
        chars = sum(len(p) for p in self.note)
        if chars > MAX_NOTE_CHARS:
            raise DeclarationError(
                f"Plaque.note is {chars} characters; the cap is {MAX_NOTE_CHARS} "
                "(a maker's note is a label, not an essay)"
            )


# --- Projection ---


def plaque_doc(plaque: Plaque) -> Doc:
    """The plaque as doc-IR — the disclosure spec, before any width is known.

    The note's paragraphs carry ``NOTE_TAG.name``; the sections carry whatever
    the demo declared. Nothing here consults a Fidelity: gating is ``doc_lens``'
    job, and doing it twice is how two answers drift apart.
    """
    body: list[Prose | Section] = [Prose(p, tag=NOTE_TAG.name) for p in plaque.note]
    body.extend(plaque.sections)
    return Doc(None, tuple(body))


def _rule(title: str, width: int) -> Block:
    """The label's hairline — a title inset into a rule.

    Not ``border()``: a full box around wall text beside a boxed work reads as
    two frames competing. One rule says "a different kind of thing starts here"
    with a single row.
    """
    dash = "─" if current_capabilities().glyph else "-"
    p = current_palette()
    accent = p.accent.merge(Style(bold=True))
    lead = dash + " "
    # Measured, not counted: a title is display columns wide, not len() wide.
    lead_w = Block.text(lead, Style()).width
    # Content before chrome — the title keeps what the rule would have spent,
    # and an over-long one is ellipsized (marked) rather than silently clipped.
    room = max(1, width - lead_w)
    head = Block.text(title, accent, width=min(room, Block.text(title, Style()).width), wrap=Wrap.ELLIPSIS)
    spans = [Span(lead, p.muted), Span(_chars(head), accent)]
    fill = width - lead_w - head.width - 1
    if fill > 0:
        spans.append(Span(" " + dash * fill, p.muted))
    return Line(spans=tuple(spans)).to_block(width)


def _chars(block: Block) -> str:
    """The text of a single-row block — how a fitted title re-enters a Line."""
    return "".join(cell.char for cell in block.row(0))


def _signature(maker: str, width: int) -> Block:
    """The attribution, right-aligned under the prose — the convention, in code."""
    em = "—" if current_capabilities().glyph else "--"
    sig = Block.text(f"{em} {maker}", current_palette().muted, wrap=Wrap.ELLIPSIS)
    return fit_to_width(pad(sig, left=max(0, width - sig.width)), width)


def _withheld(plaque: Plaque, fidelity: Fidelity, width: int) -> Block:
    """Law 6: content dropped for want of room owes evidence naming the loss.

    The names come from the same disclosure walk that would have rendered
    them, so the marker cannot claim a facet the render would have skipped.
    """
    shown = visible_body(plaque_doc(plaque).body, fidelity.depth, fidelity)
    names: list[str] = []
    if any(isinstance(node, Prose) for node, _ in shown):
        names.append("maker note")
    names.extend(
        node.heading for node, _ in shown if isinstance(node, Section) and node.heading is not None
    )
    # "withheld: " and not "withheld, too narrow: " — the marker has at most
    # MIN_PLAQUE_WIDTH - 1 columns to work in, and a longer preamble spends
    # them on prose until the *names* are what gets ellipsized away. Evidence
    # that names nothing is not evidence.
    return Block.text(
        "withheld: " + ", ".join(names),
        current_palette().muted,
        width=width,
        wrap=Wrap.ELLIPSIS,
    )


def render_plaque(plaque: Plaque, *, fidelity: Fidelity, width: int) -> Block | None:
    """The plaque at a width, or ``None`` when nothing in it is visible.

    ``None`` rather than an empty Block so the caller composes nothing at all —
    an empty block still costs a gap row in ``join_vertical``.
    """
    doc = plaque_doc(plaque)
    shown = visible_body(doc.body, fidelity.depth, fidelity)
    if not shown:
        return None
    if width < MIN_PLAQUE_WIDTH:
        return _withheld(plaque, fidelity, width)

    # A left margin, because wall text is never flush against its rule. The
    # body is laid out at the reduced width and *then* shifted, so the margin
    # never costs the plaque its exactness.
    inner = width - _MARGIN
    body = pad(doc_lens(doc, fidelity=fidelity, width=inner), left=_MARGIN)
    rows: list[Block] = [_rule(plaque.title, width), body]
    if any(isinstance(node, Prose) for node, _ in shown):
        rows.append(_signature(plaque.maker, width))
    return fit_to_width(join_vertical(*rows, gap=1), width)
