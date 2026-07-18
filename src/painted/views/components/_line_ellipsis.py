"""Styled-``Line`` ellipsis truncation — the shared row-tail mark (law 6).

When a component cuts a styled row to fit an allotted width, the cut is the
component's own choice, so it owes the mark (RENDER_MODEL law 6: whoever decides
what is not shown marks it). This is the ``Line`` analogue of
``core._text_width.truncate_ellipsis`` / ``core.compose.truncate``: it preserves
each span's style across the cut and stamps the ambient ``IconSet.ellipsis`` (so
it degrades to ASCII under ``use_icons(ASCII_ICONS)`` like every other glyph).

``table`` (cell ellipsis) and ``list_view`` (row-tail ellipsis) share it rather
than inventing the mark twice.
"""

from __future__ import annotations

from enum import Enum

from ...core._text_width import display_width
from ...core.cell import Style
from ...core.span import Line, Span


class EllipsisSide(Enum):
    """Which end of a truncated cell the ``…`` marker sits on (and thus which
    end of the content survives).

    A dedicated two-valued type rather than a reuse of ``Align``: the choice is
    *which content is kept*, not how a short value is positioned, and ``Align``
    would admit a meaningless ``CENTER``.

    - ``END`` (default): marker on the right, keep the head — ``"long descrip…"``.
    - ``START``: marker on the left, keep the tail — ``"…Code/siftd"`` (so a path
      leaf survives).
    """

    END = "end"
    START = "start"


def truncate_keep_end(line: Line, max_width: int) -> Line:
    """Truncate a Line keeping its *rightmost* ``max_width`` columns.

    The mirror of ``Line.truncate`` (which keeps the leftmost) — used for the
    left-ellipsis case where the tail (a path leaf) is the part worth keeping.
    Display-width aware; preserves each span's style across the cut.
    """
    remaining = max_width
    kept: list[Span] = []
    for span in reversed(line.spans):
        sw = span.width
        if sw <= remaining:
            kept.append(span)
            remaining -= sw
        else:
            chars: list[str] = []
            used = 0
            for ch in reversed(span.text):
                cw = display_width(ch) or 1
                if used + cw > remaining:
                    break
                chars.append(ch)
                used += cw
            if chars:
                kept.append(Span("".join(reversed(chars)), span.style))
            break
    return Line(spans=tuple(reversed(kept)), style=line.style)


def ellipsize_line(line: Line, max_width: int, side: EllipsisSide, style: Style) -> Line:
    """Truncate ``line`` to ``max_width`` columns with a ``…`` marker.

    ``side == EllipsisSide.START`` puts the ellipsis on the left and keeps the
    tail; ``EllipsisSide.END`` puts it on the right and keeps the head. Falls
    back to a plain cut (kept side preserved) when there is no room for the
    marker.

    The marker is the ambient ``IconSet.ellipsis`` so it degrades to ASCII under
    ``use_icons(ASCII_ICONS)`` like every other glyph.
    """
    from ...icon_set import current_icons

    ellipsis = current_icons().ellipsis
    ell_w = display_width(ellipsis)
    if max_width <= ell_w:
        if side == EllipsisSide.START:
            return truncate_keep_end(line, max_width)
        return line.truncate(max_width)
    budget = max_width - ell_w
    ell_span = Span(ellipsis, style)
    if side == EllipsisSide.START:
        kept = truncate_keep_end(line, budget)
        return Line(spans=(ell_span, *kept.spans), style=line.style)
    kept = line.truncate(budget)
    return Line(spans=(*kept.spans, ell_span), style=line.style)
