"""Style catalog — pins painted's full Style vocabulary at the cell level.

The appearance tier's whole job is the style layer the old goldens stripped.
This scenario renders one labeled row per text attribute, one per named fg color,
a fg+bg pair, and a `Style.merge` row — so any regression in attribute or color
emission (a lost bold, a flipped fg, a merge-precedence bug) shows up as a precise
one-line diff in the structured snapshot.
"""

from __future__ import annotations

from painted import Block, Line, Span, Style, join_vertical

_WIDTH = 24

_ATTRS = ("bold", "italic", "underline", "dim", "reverse")
_COLORS = ("red", "green", "yellow", "blue", "magenta", "cyan", "white", "black")


def _row(label: str, style: Style) -> Block:
    return Line(spans=(Span(label, style),)).to_block(_WIDTH)


def test_style_catalog(appearance) -> None:
    rows = []

    # One row per text attribute — label carries the attribute it names.
    for attr in _ATTRS:
        rows.append(_row(attr, Style(**{attr: True})))

    # One row per named fg color.
    for color in _COLORS:
        rows.append(_row(f"fg {color}", Style(fg=color)))

    # A fg+bg paired row.
    rows.append(_row("fg+bg", Style(fg="white", bg="blue")))

    # Style.merge — overlay overrides base fg, both attrs survive (italic+bold).
    base = Style(fg="blue", bold=True)
    overlay = Style(fg="red", italic=True)
    rows.append(_row("merged", base.merge(overlay)))

    block = join_vertical(*rows)
    appearance.assert_block(block, "catalog")
