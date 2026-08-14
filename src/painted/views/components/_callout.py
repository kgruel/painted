"""Callout: a severity-tagged message line (or boxed panel).

A small semantic component for CLI status / notice output — a colored severity
glyph plus a message, with an optional muted continuation detail, an optional
muted "↳ hint" next-step line, and an optional box. The severity drives BOTH the
glyph (from the ambient IconSet) and the color (from the ambient Palette role),
so callouts inherit any active theme and ASCII-degrade under
``use_icons(ASCII_ICONS)``.

    callout("Database not found", severity=Severity.ERROR, hint="Run 'siftd ingest'")
    callout("Imported 412 files", severity=Severity.SUCCESS)
"""

from __future__ import annotations

from enum import Enum

from ...core.block import Block
from ...core.borders import LIGHT
from ...core.cell import Style
from ...core.errors import ContractError
from ...core.compose import border, fit_to_width, join_vertical, pad
from ...core.span import Line, Span
from ...icon_set import current_icons
from ...palette import current_palette
from ...vocabulary import mark_style


class Severity(Enum):
    """The severity of a ``callout`` — selects its glyph and its color.

    A closed four-level vocabulary rather than a free string: a typo is a
    construction error, not a silent fall-through to ``INFO``. Each level names
    one ``IconSet`` glyph slot and one ``Palette`` role:

    - ``SUCCESS`` — ``✓``, the ``success`` role.
    - ``INFO`` — ``ℹ``, the ``muted`` role (info has no dedicated role; neutral
      notices stay quiet, the journalctl principle).
    - ``WARNING`` — ``⚠``, the ``warning`` role.
    - ``ERROR`` — ``✗``, the ``error`` role.
    """

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# Severity -> IconSet glyph attribute. The glyph is its own treatment dimension
# (IconSet vocabulary); the COLOR half resolves through the built-in "severity"
# vocabulary (mark_style), so callouts also honor Theme(roles=...). Keyed by the
# enum so an unknown value is a KeyError at the boundary, never a silent default.
_SEVERITY_ICON: dict[Severity, str] = {
    Severity.SUCCESS: "ok",
    Severity.INFO: "info",
    Severity.WARNING: "warn",
    Severity.ERROR: "error",
}

# LIGHT border (1 col each side) + horizontal pad (1 col each side) when boxed.
_BOX_CHROME = 4


def callout(
    subject: str,
    *,
    severity: Severity = Severity.INFO,
    detail: str | None = None,
    hint: str | None = None,
    box: bool = False,
    width: int | None = None,
) -> Block:
    """Render a severity-tagged message as a Block.

    ``severity`` (a :class:`Severity`) selects the glyph — from the ambient
    ``IconSet``, so it ASCII-degrades under ``use_icons(ASCII_ICONS)`` — and the
    color, from the ambient ``Palette`` role. ``detail`` adds a muted
    continuation line; ``hint`` adds a muted "↳ …" next-step line. ``box`` wraps
    the whole thing in a LIGHT border in the severity color.

    ``width`` fixes the block width *exactly* (painted's width contract): content
    is clipped or padded to ``width``, and with ``box=True`` the border is part
    of that total — the inner content fits to ``width - 4`` — so a boxed callout
    is never wider than its budget. Omitted, the callout sizes to its content.

    ``subject``/``detail``/``hint`` render as clean single rows — each slot is
    one line by contract, so callout *declares* the flatten: newlines collapse
    to spaces here (the Line layer would otherwise honor them as line breaks),
    and remaining control characters (tabs, raw ANSI) are neutralized at the
    cell level (see :class:`~painted.core.cell.Cell`), so no input can split
    or corrupt the block.

    Raises :class:`~painted.core.errors.ContractError` if ``severity`` is not a
    :class:`Severity` member (no silent fall-through to ``INFO`` — that was the
    pre-hardening defect).
    """
    icon_attr = _SEVERITY_ICON.get(severity)
    if icon_attr is None:
        raise ContractError(
            f"Unknown severity: {severity!r} (pass a Severity member, e.g. Severity.ERROR)"
        )
    icons = current_icons()
    palette = current_palette()
    glyph = getattr(icons, icon_attr)
    role = mark_style("severity", severity.value)
    muted = palette.muted

    def _one_line(text: str) -> str:
        return text.replace("\r\n", " ").replace("\n", " ")

    lines: list[Line] = [Line((Span(f"{glyph} ", role), Span(_one_line(subject))))]
    if detail:
        lines.append(Line((Span("  ", Style()), Span(_one_line(detail), muted))))
    if hint:
        lines.append(Line((Span(f"  {icons.arrow} ", muted), Span(_one_line(hint), muted))))

    if width is None:
        inner_w = max(line.width for line in lines)
    elif box:
        inner_w = max(0, width - _BOX_CHROME)
    else:
        inner_w = width
    block = join_vertical(*(line.to_block(inner_w) for line in lines))
    if box:
        block = border(pad(block, left=1, right=1), LIGHT, role)
    if width is not None:
        # Identity in the common path (content/box already sized to width);
        # the safety net when the budget is smaller than the box chrome.
        block = fit_to_width(block, width)
    return block
