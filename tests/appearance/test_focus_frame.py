"""Appearance scenario — focus/selection frame.

Pins the *styled* signals that the old text-only goldens stripped to nothing:

- a SELECTED list row in reverse-video vs plain unselected rows,
- a single reverse-video CURSOR cell inside a text field,
- a FOCUSED panel (cyan/accent border) vs an UNFOCUSED panel (dim border),
- a status bar styled black-on-white.

All four are pure Style state on the cell grid, invisible to a stripped-text
match. The serialized snapshot makes "selection lost its reverse run" or
"focused border lost its cyan" a one-line diff.
"""

from __future__ import annotations

from painted import Block, Line, Span, Style, border, join_horizontal, join_vertical

_W = 18


def _row(text: str, *, selected: bool) -> Block:
    """A list row: reverse-video when selected, plain otherwise."""
    style = Style(reverse=True) if selected else Style()
    return Line(spans=(Span(text.ljust(_W), style),)).to_block(_W)


def _text_field(before: str, cursor: str, after: str) -> Block:
    """A text input with one reverse-video cursor cell mid-field."""
    line = Line(
        spans=(
            Span(before, Style()),
            Span(cursor, Style(reverse=True)),
            Span(after, Style()),
        )
    )
    return line.to_block(_W)


def _panel(title_text: str, body: Block, *, focused: bool) -> Block:
    """A bordered panel: accent (cyan) border when focused, dim when not."""
    border_style = Style(fg="cyan") if focused else Style(dim=True)
    return border(body, style=border_style, title=title_text, title_style=border_style)


def test_focus_frame(appearance) -> None:
    # List: middle row selected (reverse), neighbours plain.
    list_body = join_vertical(
        _row("alpha", selected=False),
        _row("beta", selected=True),
        _row("gamma", selected=False),
    )
    list_panel = _panel("files", list_body, focused=True)

    # Text input with a reverse-video cursor cell.
    field = _text_field("name: ab", "c", "")
    input_panel = _panel("input", field, focused=False)

    panels = join_horizontal(list_panel, input_panel, gap=1)

    # Status bar: black on white, full width of the composed panels.
    status = Line(
        spans=(Span(" READY ".ljust(panels.width), Style(fg="black", bg="white")),)
    ).to_block(panels.width)

    frame = join_vertical(panels, status)
    appearance.assert_block(frame, "frame")
