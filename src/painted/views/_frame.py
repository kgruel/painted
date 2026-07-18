"""Scroll evidence and frame assembly — the law-6 vocabulary for the host rung.

Two public artifacts, one vocabulary (HOST_RUNG_DESIGN §6):

- ``evidence_row`` builds the reserved scroll-evidence *row* — ``… ▼ 763 more
  rows`` — that marks content a window omits (RENDER_MODEL law 6: whoever
  decides what is not shown marks it). It is a **row, never a rail**: it never
  perturbs width, so a height-only re-slice needs no re-render (§6, the width
  contract). It counts **rows**, not entries — the caller knows Block height and
  offset, never how rows map to semantic records; ``label=`` is the seam for
  caller-supplied entry wording.

- ``assemble_frame`` is the pure F-conditional frame builder beside it: given
  natural-height content, a frame height ``F ≥ 0``, and a row offset, it slices
  and pads to exactly ``F`` rows, appending an evidence row when content
  overflows. It holds no state — ``Viewport`` stays the scroll-state carrier;
  this only slices and assembles.

Both the S3 host viewport adapter (the omitted arm) and offered-arm final
renderers that reserve their own body viewport (e.g. a dashboard's chrome, §6)
consume the same builder rather than inventing evidence twice — which is why it
is public in 0.13. The windowed components (``list_view``/``table``/
``data_explorer``) reuse ``evidence_row`` directly, reserving their last body row
under overflow (0.14 honesty-remediation S1, RENDER_MODEL law 6).

Placement (views, not core.compose): this is a *meaning-bearing* disclosure
artifact — it renders the semantics of omission through the ambient icon set and
palette — not a generic geometric op. ``core.compose`` is pure Block geometry;
growing it a palette-styled, law-6 evidence builder would blur that split. The
frame helper lives here beside the row because they are one vocabulary
(``assemble_frame`` calls ``evidence_row``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.compose import join_vertical, pad, vslice
from ..core.errors import ContractError

if TYPE_CHECKING:
    from ..core.block import Block


def evidence_row(
    hidden_above: int,
    hidden_below: int,
    width: int,
    *,
    ref: str | None = None,
    label: str | None = None,
) -> Block:
    """One row marking rows a window omits above and/or below — exactly ``width``.

    ``hidden_above``/``hidden_below`` are **row** counts (negatives clamp to 0):
    how many content rows fall before / after the visible window. The default
    wording counts the total hidden rows (``… ▼ 763 more rows``); pass ``label``
    to substitute caller-owned wording (an entry count, an app noun) — the seam
    that keeps entry semantics the application's, never this builder's.

    The direction glyph is the ambient ``IconSet`` (``scroll_up``/``scroll_down``,
    ASCII ``^``/``v``) so it degrades like every other gutter marker; styling is
    the ambient palette's ``muted`` role. Glyph and colour cosmetics are deferred
    to appearance review (§6) — these are sensible defaults, not polish.

    ``ref`` stamps the whole row with a uniform denotation ref (``refs.py``), so
    a host can route clicks on the evidence row through the denotation channel.

    It is a row, never a rail: the result is exactly ``width`` columns
    (clipped/padded per the width contract), so a height-only re-slice never
    perturbs width.
    """
    from ..core.block import Block
    from ..icon_set import current_icons
    from ..palette import current_palette

    above = max(0, hidden_above)
    below = max(0, hidden_below)

    icons = current_icons()
    if above and below:
        direction = icons.scroll_up + icons.scroll_down
    elif below:
        direction = icons.scroll_down
    elif above:
        direction = icons.scroll_up
    else:
        direction = ""

    text = label if label is not None else f"{above + below} more rows"
    marker = " ".join(part for part in (icons.ellipsis, direction, text) if part)

    return Block.text(marker, current_palette().muted, width=width, ref=ref)


def assemble_frame(
    content: Block,
    height: int,
    offset: int = 0,
    *,
    ref: str | None = None,
    label: str | None = None,
) -> Block:
    """Assemble ``content`` into an exact ``height``-row frame (HOST_RUNG §6).

    ``height`` is the frame allocation ``F ≥ 0`` (a negative offer is a host bug
    and fails loudly). The F-conditional algorithm:

    - ``F = 0`` → an empty zero-height frame, evidence **waived** (the §5
      degenerate rule: law-6 evidence is owed only where the allocation
      physically permits a row).
    - content **fits** at ``F ≥ 1`` (``content.height ≤ F``) → shown from the top
      and padded to exactly ``F`` rows; no evidence (nothing is omitted).
    - content **overflows** at ``F ≥ 1`` (``content.height > F``) → ``F − 1``
      content rows sliced at ``offset`` plus one ``evidence_row``. At ``F = 1``
      the single row **is** the evidence row (``InPlaceRenderer``'s shipped
      head-clip precedent).

    ``offset`` is clamped into the valid range so the frame is exactly ``F`` rows
    for any offset — this holds no scroll state (``Viewport`` is the carrier); it
    only slices and assembles. Frame width is the content's natural width — the
    evidence row matches it, never perturbing it. ``ref``/``label`` forward to the
    evidence row.
    """
    if height < 0:
        raise ContractError(f"assemble_frame height must be >= 0, got {height}")

    if height == 0:
        from ..core.block import Block

        return Block.empty(content.width, 0)

    # Fits: show from the top, pad the remainder. Ownership follows the offer —
    # here the host constructs the exact frame, so the host pads (§5).
    if content.height <= height:
        if content.height == height:
            return content
        return pad(content, bottom=height - content.height)

    # Overflow: F-1 content rows at the (clamped) offset + one evidence row.
    shown = height - 1
    off = max(0, min(offset, content.height - shown))
    above = off
    below = content.height - (off + shown)
    evidence = evidence_row(above, below, content.width, ref=ref, label=label)

    if shown == 0:  # F=1 overflow — the one row is evidence
        return evidence
    return join_vertical(vslice(content, off, shown), evidence)
