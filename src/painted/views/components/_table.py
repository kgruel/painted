"""Table component: scrollable table with headers and row selection."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...core.block import Block
from ...core.buffer import Buffer
from ...core.cell import Style
from ...core.compose import Align, truncate
from ...core._text_width import display_width
from ...cursor import Cursor
from ...core.span import Line, Span
from ...viewport import Viewport

if TYPE_CHECKING:
    from ...core.borders import BorderChars
    from ...palette import Palette


@dataclass(frozen=True)
class Column:
    """Column definition for a table."""

    header: Line
    width: int
    align: Align = Align.START


@dataclass(frozen=True)
class TableState:
    """Immutable table state tracking row selection and scroll position.

    Composition:
    - `cursor`: selected row index over `row_count`
    - `viewport`: scroll offset/visible/content for rendering
    """

    cursor: Cursor = Cursor()
    viewport: Viewport = Viewport()

    @property
    def selected_row(self) -> int:
        return self.cursor.index

    @property
    def row_count(self) -> int:
        return self.cursor.count

    @property
    def scroll_offset(self) -> int:
        return self.viewport.offset

    def move_up(self) -> TableState:
        """Move selection up, clamping to 0."""
        return replace(self, cursor=self.cursor.prev())

    def move_down(self) -> TableState:
        """Move selection down, clamping to last row."""
        return replace(self, cursor=self.cursor.next())

    def move_to(self, row: int) -> TableState:
        """Move selection to a specific row, clamped to valid range."""
        return replace(self, cursor=self.cursor.move_to(row))

    def with_count(self, count: int) -> TableState:
        """Update row_count, clamping selection + scroll offset."""
        cursor = self.cursor.with_count(count)
        viewport = self.viewport.with_content(cursor.count)
        return replace(self, cursor=cursor, viewport=viewport)

    def with_visible(self, height: int) -> TableState:
        """Update viewport visible height."""
        return replace(self, viewport=self.viewport.with_visible(height))

    def scroll_into_view(self, visible_height: int) -> TableState:
        """Adjust viewport so selected row is visible."""
        vp = self.viewport.with_visible(visible_height).with_content(self.cursor.count)
        vp = vp.scroll_into_view(self.cursor.index)
        return replace(self, viewport=vp)


def _pad_line(line: Line, target_width: int, align: Align, style: Style) -> Line:
    """Truncate or pad a Line to exactly target_width columns."""
    current = line.width
    if current > target_width:
        return line.truncate(target_width)
    if current == target_width:
        return line
    padding = target_width - current
    if align == Align.START:
        return Line(spans=line.spans + (Span(" " * padding, style),), style=line.style)
    elif align == Align.END:
        return Line(spans=(Span(" " * padding, style),) + line.spans, style=line.style)
    else:  # CENTER
        left = padding // 2
        right = padding - left
        return Line(
            spans=(Span(" " * left, style),) + line.spans + (Span(" " * right, style),),
            style=line.style,
        )


def table(
    state: TableState,
    columns: list[Column],
    rows: list[list[Line]],
    visible_height: int,
    *,
    width: int | None = None,
    header_style: Style | None = None,
    selected_style: Style | None = None,
    separator_style: Style | None = None,
    palette: Palette | None = None,
    borders: BorderChars | None = None,
) -> Block:
    """Render a table with headers, scrolling, and row selection.

    Styling is derived from the ambient Palette and BorderChars by default.
    Explicit style/border arguments override the ambient values.

    Args:
        header_style: Style for header row. Defaults to palette.accent + bold.
        selected_style: Style for selected data row. Defaults to reverse.
        separator_style: Style for the separator line. Defaults to palette.muted.
        palette: Optional Palette override (uses ambient if None).
        borders: Optional BorderChars override (uses ambient if None).
    """
    from ...core.borders import current_borders
    from ...palette import current_palette

    if not columns:
        return Block.empty(1, visible_height + 2)

    p = palette or current_palette()
    b = borders or current_borders()

    hs = header_style or p.accent.merge(Style(bold=True))
    ss = selected_style or Style(reverse=True)
    sep_style = separator_style or p.muted

    separator = b.vertical

    vp = state.viewport.with_visible(visible_height).with_content(len(rows))
    cursor = state.cursor.with_count(len(rows))

    # Calculate total width: sum of column widths + separators.
    # Display columns, not codepoints — separator is caller-overridable via borders=.
    sep_width = display_width(separator)
    total_width = sum(c.width for c in columns) + sep_width * (len(columns) - 1)

    # Total rows: header + separator + visible data
    total_rows = 2 + visible_height
    buf = Buffer(total_width, total_rows)

    # -- Header row --
    col_x = 0
    for i, col in enumerate(columns):
        header_line = _pad_line(col.header, col.width, col.align, hs)
        header_line = Line(spans=header_line.spans, style=hs)
        view = buf.region(col_x, 0, col.width, 1)
        header_line.paint(view, 0, 0)
        col_x += col.width
        if i < len(columns) - 1:
            buf.put_text(col_x, 0, separator, hs)
            col_x += sep_width

    # -- Separator line --
    col_x = 0
    for i, col in enumerate(columns):
        buf.put_text(col_x, 1, b.horizontal * col.width, sep_style)
        col_x += col.width
        if i < len(columns) - 1:
            buf.put_text(col_x, 1, b.crossing * sep_width, sep_style)
            col_x += sep_width

    # -- Data rows (visible window) --
    start = vp.offset
    end = min(start + visible_height, len(rows))

    for row_offset, row_idx in enumerate(range(start, end)):
        row_data = rows[row_idx] if row_idx < len(rows) else []
        is_selected = row_idx == cursor.index
        row_style = ss if is_selected else Style()
        buf_y = 2 + row_offset

        col_x = 0
        for i, col in enumerate(columns):
            cell_line = row_data[i] if i < len(row_data) else Line.plain("")
            padded = _pad_line(cell_line, col.width, col.align, row_style)
            padded = Line(spans=padded.spans, style=row_style)
            view = buf.region(col_x, buf_y, col.width, 1)
            padded.paint(view, 0, 0)
            col_x += col.width
            if i < len(columns) - 1:
                buf.put_text(col_x, buf_y, separator, row_style)
                col_x += sep_width

    # Extract rows from buffer into Block
    block_rows = []
    actual_height = 2 + (end - start) + max(0, visible_height - (end - start))
    for y in range(actual_height):
        row = [buf.get(x, y) for x in range(total_width)]
        block_rows.append(row)

    result = Block(block_rows, total_width)
    if width is not None and result.width > width:
        result = truncate(result, width)
    return result
