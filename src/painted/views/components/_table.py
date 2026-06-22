"""Table component: scrollable table with headers and row selection."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
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


class _Auto:
    """Sentinel width: size the column to its natural content width."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "AUTO"


AUTO = _Auto()
"""Size a column to the widest of its header and cell content (wcwidth-aware)."""


@dataclass(frozen=True)
class Fill:
    """A flex column width: share leftover budget with other Fill columns.

    ``weight`` sets the proportion when several Fill columns compete for the
    same leftover space (``Fill(weight=2)`` takes twice the share of
    ``Fill()``). With no width budget (``table(..., width=None)``) a Fill column
    falls back to its natural content width, exactly like ``AUTO``.
    """

    weight: float = 1.0


# A column's width is a track-sizing function over the available budget:
#   int   — a fixed number of display columns
#   AUTO  — the column's natural content width
#   Fill  — a flex share of whatever budget remains after fixed/AUTO columns
ColumnWidth = int | _Auto | Fill


class Overflow(Enum):
    """How ``table()`` reconciles a too-wide table with its ``width`` budget.

    - ``CLIP`` (default, historical): columns keep their resolved widths and the
      assembled block is truncated at the right edge if it exceeds the budget —
      trailing columns can disappear.
    - ``FIT``: size columns to content, but when the table is over budget shrink
      the ``Fill`` columns (ellipsized per their ``ellipsis``/``ellipsis_side``)
      to bring it within the budget, and *never stretch* a ``Fill`` past its
      content when there is slack. If the non-``Fill`` columns alone exceed the
      budget the table overflows (natural width) rather than clipping data — no
      column or value is silently dropped.
    """

    CLIP = "clip"
    FIT = "fit"


@dataclass(frozen=True)
class Column:
    """Column definition for a table.

    ``width`` is a track-sizing function: a fixed ``int``, ``AUTO`` (natural
    content width), or ``Fill`` (a flex share of leftover budget).
    ``min_width``/``max_width`` clamp the resolved width. The responsive
    resolution runs whenever ``table()`` is given a ``width`` budget; without
    one, columns size naturally — the historical behavior.

    ``ellipsis`` adds a ``…`` marker when a cell is truncated to its column
    width; ``ellipsis_side`` chooses which end the marker sits on —
    ``Align.END`` keeps the head (``"long descrip…"``), ``Align.START`` keeps
    the tail (``"…Code/siftd-7"``, so a path leaf survives). Without
    ``ellipsis`` an over-wide cell is cut on the right with no marker (historical
    behavior).
    """

    header: Line
    width: ColumnWidth = AUTO
    align: Align = Align.START
    min_width: int | None = None
    max_width: int | None = None
    ellipsis: bool = False
    ellipsis_side: Align = Align.END


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


def _truncate_keep_end(line: Line, max_width: int) -> Line:
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


def _ellipsize_line(line: Line, max_width: int, side: Align, style: Style) -> Line:
    """Truncate ``line`` to ``max_width`` columns with a ``…`` marker.

    ``side == Align.START`` puts the ellipsis on the left and keeps the tail;
    any other side puts it on the right and keeps the head. Falls back to a
    plain cut (kept side preserved) when there is no room for the marker.

    The marker is the ambient ``IconSet.ellipsis`` so it degrades to ASCII under
    ``use_icons(ASCII_ICONS)`` like every other glyph.
    """
    from ...icon_set import current_icons

    ellipsis = current_icons().ellipsis
    ell_w = display_width(ellipsis)
    if max_width <= ell_w:
        if side == Align.START:
            return _truncate_keep_end(line, max_width)
        return line.truncate(max_width)
    budget = max_width - ell_w
    ell_span = Span(ellipsis, style)
    if side == Align.START:
        kept = _truncate_keep_end(line, budget)
        return Line(spans=(ell_span, *kept.spans), style=line.style)
    kept = line.truncate(budget)
    return Line(spans=(*kept.spans, ell_span), style=line.style)


def _pad_line(
    line: Line,
    target_width: int,
    align: Align,
    style: Style,
    *,
    ellipsis: bool = False,
    ellipsis_side: Align = Align.END,
) -> Line:
    """Truncate or pad a Line to exactly target_width columns.

    When ``ellipsis`` is set, an over-wide line is truncated with a ``…`` marker
    on ``ellipsis_side``; otherwise it is cut on the right with no marker.
    """
    current = line.width
    if current > target_width:
        if ellipsis:
            return _ellipsize_line(line, target_width, ellipsis_side, style)
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


def resolve_column_widths(
    columns: list[Column],
    rows: list[list[Line]],
    available: int | None,
    *,
    sep_width: int = 1,
    overflow: Overflow = Overflow.CLIP,
) -> list[int]:
    """Resolve each column's track-sizing function to an exact integer width.

    The responsive-width pre-pass: fixed columns pass through, ``AUTO`` columns
    take their natural (wcwidth-aware) content width, and ``Fill`` columns share
    whatever budget remains after the others, split by ``weight``.
    ``min_width``/``max_width`` clamp every result.

    ``available`` is the total width budget *including* separators. When it is
    ``None`` there is no budget, so ``Fill`` falls back to natural width and the
    returned widths sum to the table's natural size.

    Under ``Overflow.CLIP`` (default): a budget makes the uncapped ``Fill``
    columns stretch to fill it exactly; with no ``Fill`` column and content
    wider than the budget, the widths are returned unshrunk and ``table()``
    clips the assembled block at the right edge.

    Under ``Overflow.FIT``: ``Fill`` columns size to their content and never
    stretch past it. When the natural table exceeds the budget, the ``Fill``
    columns shrink (toward their ``min_width`` floors) to absorb the overflow;
    if even their floors plus the non-``Fill`` columns exceed the budget, the
    widths are returned at natural/floor size and the table is allowed to
    overflow — ``table()`` does not clip, so no column or value is dropped.
    """
    n = len(columns)
    if n == 0:
        return []

    # 1. Natural content width per column: widest of header and any cell.
    natural = [col.header.width for col in columns]
    for row in rows:
        for i in range(min(len(row), n)):
            w = row[i].width
            if w > natural[i]:
                natural[i] = w

    def clamp(value: int, col: Column) -> int:
        if col.min_width is not None and value < col.min_width:
            value = col.min_width
        if col.max_width is not None and value > col.max_width:
            value = col.max_width
        return value if value > 0 else 0

    # 2. Base resolution. Fixed and AUTO resolve now; Fill defers for leftover.
    widths = [0] * n
    fills: dict[int, Fill] = {}
    for i, col in enumerate(columns):
        if isinstance(col.width, Fill):
            fills[i] = col.width
        elif isinstance(col.width, _Auto):
            widths[i] = clamp(natural[i], col)
        else:  # fixed int
            widths[i] = clamp(int(col.width), col)

    fill_idx = list(fills)

    if available is None:
        # No budget: Fill behaves like AUTO — nothing to share.
        for i in fill_idx:
            widths[i] = clamp(natural[i], columns[i])
        return widths

    sep_total = sep_width * (n - 1)

    if overflow == Overflow.FIT:
        # Fit-to-content: Fill columns sit at natural width and only *shrink*
        # (never stretch) when the table is over budget. If they can't shrink
        # enough, the table overflows rather than clipping — table() honors that.
        for i in fill_idx:
            widths[i] = clamp(natural[i], columns[i])
        natural_total = sum(widths) + sep_total
        if natural_total <= available or not fill_idx:
            return widths

        nonfill_total = sum(widths[i] for i in range(n) if i not in fills) + sep_total
        leftover = available - nonfill_total  # combined width for all Fill columns
        floors = {i: (columns[i].min_width or 1) for i in fill_idx}
        total_weight = sum(f.weight for f in fills.values())
        if leftover <= sum(floors.values()) or total_weight <= 0:
            # Non-Fill columns already overflow: hold Fills at their floors and
            # let the table exceed the budget (lossless — table() won't clip).
            for i in fill_idx:
                widths[i] = floors[i]
            return widths

        # Share the leftover across Fill columns by weight (largest-remainder),
        # clamped to [floor, natural] — shrink only, never stretch past content.
        exact = {i: leftover * fills[i].weight / total_weight for i in fill_idx}
        share = {i: int(exact[i]) for i in fill_idx}
        remainder = leftover - sum(share.values())
        by_frac = sorted(fill_idx, key=lambda i: (exact[i] - share[i], -i), reverse=True)
        for i in by_frac[:remainder]:
            share[i] += 1
        for i in fill_idx:
            w = max(floors[i], share[i])
            widths[i] = min(w, clamp(natural[i], columns[i]))
        return widths

    if not fill_idx:
        # No flex columns: fixed/AUTO widths stand. If they exceed the budget,
        # table()'s tail truncate clips the block (over-budget fallback).
        return widths

    # 3. Distribute leftover budget across Fill columns by weight.
    budget = available - sep_total
    floor = {i: (columns[i].min_width or 0) for i in fill_idx}
    used = sum(widths[i] for i in range(n) if i not in fills) + sum(floor.values())
    leftover = budget - used

    total_weight = sum(f.weight for f in fills.values())
    if leftover <= 0 or total_weight <= 0:
        # No room to fill (or degenerate zero weights): Fill takes its floor.
        for i in fill_idx:
            widths[i] = clamp(floor[i], columns[i])
        return widths

    exact = {i: leftover * fills[i].weight / total_weight for i in fill_idx}
    share = {i: int(exact[i]) for i in fill_idx}
    remainder = leftover - sum(share.values())
    # Largest-remainder: hand the leftover pixels to the biggest fractional
    # parts, breaking ties by lowest column index for determinism.
    by_frac = sorted(fill_idx, key=lambda i: (exact[i] - share[i], -i), reverse=True)
    for i in by_frac[:remainder]:
        share[i] += 1
    for i in fill_idx:
        widths[i] = clamp(floor[i] + share[i], columns[i])
    return widths


def table(
    state: TableState,
    columns: list[Column],
    rows: list[list[Line]],
    visible_height: int,
    *,
    width: int | None = None,
    overflow: Overflow = Overflow.CLIP,
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
        overflow: How a too-wide table reconciles with ``width`` — ``CLIP``
            (default) right-clips the block; ``FIT`` shrinks ``Fill`` columns
            (ellipsized) to fit and otherwise overflows rather than dropping
            columns. See ``Overflow``.
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

    # Resolve each column's track-sizing function (fixed/AUTO/Fill) against the
    # budget, then lay out exactly as before from the resolved integer widths.
    # Display columns, not codepoints — separator is caller-overridable via borders=.
    sep_width = display_width(separator)
    resolved = resolve_column_widths(
        columns, rows, available=width, sep_width=sep_width, overflow=overflow
    )
    total_width = sum(resolved) + sep_width * (len(columns) - 1)

    # Total rows: header + separator + visible data
    total_rows = 2 + visible_height
    buf = Buffer(total_width, total_rows)

    # -- Header row --
    col_x = 0
    for i, col in enumerate(columns):
        cw = resolved[i]
        header_line = _pad_line(
            col.header,
            cw,
            col.align,
            hs,
            ellipsis=col.ellipsis,
            ellipsis_side=col.ellipsis_side,
        )
        header_line = Line(spans=header_line.spans, style=hs)
        view = buf.region(col_x, 0, cw, 1)
        header_line.paint(view, 0, 0)
        col_x += cw
        if i < len(columns) - 1:
            buf.put_text(col_x, 0, separator, hs)
            col_x += sep_width

    # -- Separator line --
    col_x = 0
    for i, col in enumerate(columns):
        buf.put_text(col_x, 1, b.horizontal * resolved[i], sep_style)
        col_x += resolved[i]
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
            cw = resolved[i]
            cell_line = row_data[i] if i < len(row_data) else Line.plain("")
            padded = _pad_line(
                cell_line,
                cw,
                col.align,
                row_style,
                ellipsis=col.ellipsis,
                ellipsis_side=col.ellipsis_side,
            )
            padded = Line(spans=padded.spans, style=row_style)
            view = buf.region(col_x, buf_y, cw, 1)
            padded.paint(view, 0, 0)
            col_x += cw
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
    # CLIP truncates an over-budget block at the right edge; FIT has already
    # shrunk or chosen to overflow, so it never clips (no column/value dropped).
    if overflow is Overflow.CLIP and width is not None and result.width > width:
        result = truncate(result, width)
    return result
