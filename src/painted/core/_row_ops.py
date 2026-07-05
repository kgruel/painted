"""Helpers for traversing row-encoded wide characters safely."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from ._text_width import char_width
from .cell import Cell, Style

_space_cells: dict[Style, Cell] = {}


def blank_cell(style: Style) -> Cell:
    """Return a cached space cell for the given style."""
    space = _space_cells.get(style)
    if space is None:
        space = Cell(" ", style)
        _space_cells[style] = space
    return space


@dataclass(frozen=True, slots=True)
class RowSpan:
    """A visible glyph span inside a row-encoded block."""

    start: int
    width: int
    cells: tuple[Cell, ...]
    refs: tuple[str | None, ...] | None = None


def _is_wide_pair(row: Sequence[Cell], idx: int) -> bool:
    if idx + 1 >= len(row):
        return False
    cell = row[idx]
    if char_width(cell.char) <= 1:
        return False
    next_cell = row[idx + 1]
    return next_cell.char == " " and next_cell.style == cell.style


def iter_row_spans(
    row: Sequence[Cell],
    refs: Sequence[str | None] | None = None,
) -> Iterator[RowSpan]:
    """Iterate row cells as visible glyph spans.

    Wide characters are yielded as a two-cell span (lead char + placeholder).
    Malformed rows fall back to single-cell spans so callers remain robust.
    """
    i = 0
    while i < len(row):
        if _is_wide_pair(row, i):
            yield RowSpan(
                start=i,
                width=2,
                cells=(row[i], row[i + 1]),
                refs=((refs[i], refs[i + 1]) if refs is not None else None),
            )
            i += 2
            continue

        yield RowSpan(
            start=i,
            width=1,
            cells=(row[i],),
            refs=((refs[i],) if refs is not None else None),
        )
        i += 1


def row_visible_text(row: Sequence[Cell]) -> str:
    """Render a row's visible text, skipping wide-char placeholder cells.

    Fast path: if all characters are ASCII, there are no wide characters and
    therefore no placeholder cells — join directly without iter_row_spans.

    Intermediate path: if non-ASCII chars are all width-1 (e.g. em-dash,
    arrows, mathematical symbols), there are no placeholder cells either —
    join directly without iter_row_spans.

    Slow path: only when actual wide (2-cell) characters are present.
    """
    text = "".join(cell.char for cell in row)
    if text.isascii():
        return text
    # Check if any non-ASCII char is actually wide (display width > 1).
    # Width-1 non-ASCII chars (em-dash, arrows, etc.) have no placeholder cells
    # and the joined text is already correct.
    if all(char_width(c) <= 1 for c in text if not c.isascii()):
        return text
    # Slow path: wide (2-cell) chars present — skip placeholder cells.
    return "".join(span.cells[0].char for span in iter_row_spans(row))


def iter_trimmed_row_spans(
    row: Sequence[Cell],
    refs: Sequence[str | None] | None = None,
) -> Iterator[RowSpan]:
    """Iterate visible spans, trimming trailing single-cell space padding.

    Block composition pads rows to a uniform width. Writing those trailing
    padding cells in ANSI mode can hit the terminal's last column and trigger
    an unwanted auto-wrap before the explicit newline.

    Wide-character placeholder cells are preserved because they are yielded as
    width-2 spans by ``iter_row_spans()`` and therefore never match the
    trimmed-single-space rule.
    """
    spans = list(iter_row_spans(row, refs))
    end = len(spans)
    while end > 0:
        span = spans[end - 1]
        if span.width == 1 and span.cells[0].char == " ":
            end -= 1
            continue
        break
    yield from spans[:end]


def take_row_prefix(
    row: Sequence[Cell],
    max_width: int,
    refs: Sequence[str | None] | None = None,
) -> tuple[list[Cell], list[str | None] | None, int]:
    """Take a display-width prefix without splitting wide-character spans."""
    if max_width <= 0:
        return ([], [] if refs is not None else None, 0)

    cells: list[Cell] = []
    out_refs: list[str | None] | None = [] if refs is not None else None
    used = 0

    for span in iter_row_spans(row, refs):
        if used + span.width > max_width:
            break
        cells.extend(span.cells)
        if out_refs is not None and span.refs is not None:
            out_refs.extend(span.refs)
        used += span.width

    return (cells, out_refs, used)
