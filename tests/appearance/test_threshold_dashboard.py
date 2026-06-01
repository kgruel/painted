"""Threshold-colored dashboard — pins per-band role color, incl. the hot-phase accent.

The motivating bug: a dashboard marks a "hot phase" purely by COLOR (the palette
accent role) with NO text marker. A stripped-text golden cannot see color, so a
regression dropping that accent fg — or flipping a threshold band's role — sails
through invisibly. This appearance snapshot pins the role color of every band,
including the hot-phase row whose ONLY signal is `palette.accent` as an fg.

We build the rows from the public API (Span/Line/Style + join_vertical) over the
default palette roles (`current_palette().success/.warning/.error/.accent`) — the
suite resets ambient palette to defaults around every test, so the snapshot
captures the role colors the scenario reads, not a leaked ambient one.
"""

from __future__ import annotations

from painted import Line, Span, Style, current_palette, join_vertical

# Dashboard column geometry: a fixed-width label column + a usage-bar column.
_LABEL_W = 12
_BAR_W = 10


def _bar(pct: float) -> str:
    """A simple text usage bar — proportion-filled, fixed width."""
    filled = round(pct * _BAR_W)
    return "█" * filled + "░" * (_BAR_W - filled)


def _row(label: str, pct: float, role: Style) -> Line:
    """One dashboard row: `<label> <bar> <pct%>`, every span styled by `role`.

    The role color is the *only* per-band signal carried in the bar+pct; the
    hot-phase row reuses a normal label with the accent role so that text is
    identical to a normal row and only the color distinguishes it.
    """
    text = f"{label:<{_LABEL_W}}{_bar(pct)} {int(pct * 100):>3}%"
    return Line(spans=(Span(text, role),))


def test_threshold_dashboard(appearance) -> None:
    palette = current_palette()

    rows = (
        _row("api", 0.50, palette.success),  # normal   → green
        _row("cache", 0.80, palette.warning),  # warning  → yellow
        _row("db", 0.95, palette.error),  # critical → red
        # HOT PHASE: byte-identical text to the normal `api` row above, NO text
        # marker — the accent fg is the entire signal distinguishing them. A
        # stripped-text test sees two identical rows; only color tells them
        # apart. This is the unguarded case.
        _row("api", 0.50, palette.accent),  # hot      → accent (cyan)
    )

    width = _LABEL_W + _BAR_W + 5
    block = join_vertical(*(line.to_block(width) for line in rows))
    appearance.assert_block(block, "dashboard")
