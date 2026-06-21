"""Callout: a severity-tagged message line (or boxed panel).

A small semantic component for CLI status / notice output — a colored severity
glyph plus a message, with an optional muted continuation hint and an optional
box. The severity drives BOTH the glyph (from the ambient IconSet) and the color
(from the ambient Palette role), so callouts inherit any active theme and
ASCII-degrade under ``use_icons(ASCII_ICONS)``.

    callout("Database not found", severity="error", hint="Run 'siftd ingest'")
    callout("Imported 412 files", severity="success")
"""

from __future__ import annotations

from ...core.block import Block
from ...core.borders import LIGHT
from ...core.cell import Style
from ...core.compose import border, join_vertical, pad
from ...core.span import Line, Span
from ...icon_set import current_icons
from ...palette import current_palette

# severity → (IconSet glyph attribute, Palette role attribute).
# "info" has no dedicated palette role; it rides "muted" (recedes), matching the
# journalctl principle — neutral notices stay quiet.
_SEVERITY: dict[str, tuple[str, str]] = {
    "success": ("ok", "success"),
    "info": ("info", "muted"),
    "warning": ("warn", "warning"),
    "error": ("error", "error"),
}


def callout(
    subject: str,
    *,
    severity: str = "info",
    detail: str | None = None,
    hint: str | None = None,
    box: bool = False,
    width: int | None = None,
) -> Block:
    """Render a severity-tagged message as a Block.

    ``severity`` ∈ {"success", "info", "warning", "error"} selects the glyph
    (from the ambient IconSet — so it ASCII-degrades under
    ``use_icons(ASCII_ICONS)``) and the color (from the ambient Palette role).
    ``detail`` adds a muted continuation line; ``hint`` adds a muted "↳ …"
    next-step line. ``box`` wraps the whole thing in a LIGHT border in the
    severity color. ``width`` fixes the block width (default: natural).

    Unknown severities fall back to "info".
    """
    icon_attr, role_attr = _SEVERITY.get(severity, _SEVERITY["info"])
    icons = current_icons()
    palette = current_palette()
    glyph = getattr(icons, icon_attr)
    role = getattr(palette, role_attr)
    muted = palette.muted

    lines: list[Line] = [Line((Span(f"{glyph} ", role), Span(subject)))]
    if detail:
        lines.append(Line((Span("  ", Style()), Span(detail, muted))))
    if hint:
        lines.append(Line((Span(f"  {icons.arrow} ", muted), Span(hint, muted))))

    w = width if width is not None else max(line.width for line in lines)
    block = join_vertical(*(line.to_block(w) for line in lines))
    if box:
        block = border(pad(block, left=1, right=1), LIGHT, role)
    return block
