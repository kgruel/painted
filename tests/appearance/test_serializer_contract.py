"""Serializer contract — locks the appearance snapshot format itself.

Distinct from the canonical appearance scenarios (which pin how specific views
*look*): this guards how the fixture *serializes*, so a regression in run
coalescing, wide-char handling, or style-field emission surfaces here rather than
silently reshaping every scenario snapshot at once. One representative block
exercising a styled run, a plain run, a wide char, and width-pad coalescing.
"""

from __future__ import annotations

from painted import Line, Span, Style, join_vertical


def test_serializer_shape(appearance) -> None:
    row0 = Line(
        spans=(
            Span("PASS", Style(fg="green", bold=True)),
            Span(" 12 世", Style()),
        )
    ).to_block(14)
    row1 = Line(
        spans=(
            Span("FAIL", Style(fg="red", reverse=True)),
            Span(" 1 bad", Style(dim=True)),
        )
    ).to_block(14)
    block = join_vertical(row0, row1)
    appearance.assert_block(block, "panel")
