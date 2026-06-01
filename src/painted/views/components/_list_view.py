"""List view component: scrollable list with selection."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...core.block import Block
from ...core.buffer import Buffer
from ...core.cell import Style
from ...cursor import Cursor
from ...core.span import Line, Span
from ...viewport import Viewport

if TYPE_CHECKING:
    from ...icon_set import IconSet
    from ...palette import Palette


@dataclass(frozen=True)
class ListState:
    """Immutable list state tracking selection and scroll position.

    Composition:
    - `cursor`: selection index over `item_count`
    - `viewport`: scroll offset/visible/content for rendering
    """

    cursor: Cursor = Cursor()
    viewport: Viewport = Viewport()

    @property
    def selected(self) -> int:
        return self.cursor.index

    @property
    def item_count(self) -> int:
        return self.cursor.count

    @property
    def scroll_offset(self) -> int:
        return self.viewport.offset

    def move_up(self) -> ListState:
        """Move selection up, clamping to 0."""
        return replace(self, cursor=self.cursor.prev())

    def move_down(self) -> ListState:
        """Move selection down, clamping to last item."""
        return replace(self, cursor=self.cursor.next())

    def move_to(self, index: int) -> ListState:
        """Move selection to a specific index, clamped to valid range."""
        return replace(self, cursor=self.cursor.move_to(index))

    def with_count(self, count: int) -> ListState:
        """Update item_count, clamping selection + scroll offset."""
        cursor = self.cursor.with_count(count)
        viewport = self.viewport.with_content(cursor.count)
        return replace(self, cursor=cursor, viewport=viewport)

    def with_visible(self, height: int) -> ListState:
        """Update viewport visible height."""
        return replace(self, viewport=self.viewport.with_visible(height))

    def scroll_into_view(self, visible_height: int) -> ListState:
        """Adjust viewport so selected item is visible."""
        vp = self.viewport.with_visible(visible_height).with_content(self.cursor.count)
        vp = vp.scroll_into_view(self.cursor.index)
        return replace(self, viewport=vp)


def list_view(
    state: ListState,
    items: list[Line],
    visible_height: int,
    *,
    width: int | None = None,
    selected_style: Style | None = None,
    cursor_char: str | None = None,
    palette: Palette | None = None,
    icons: IconSet | None = None,
) -> Block:
    """Render a scrollable list with selection highlight.

    Styling is derived from the ambient Palette and IconSet by default.
    Explicit arguments override the ambient values.

    Args:
        selected_style: Style for selected row. Defaults to reverse.
        cursor_char: Selection indicator character. Defaults to icons.check glyph prefix.
        palette: Optional Palette override (uses ambient if None).
        icons: Optional IconSet override (uses ambient if None).
    """
    from ...icon_set import current_icons
    from ...palette import current_palette

    if not items:
        return Block.empty(1, visible_height)

    p = palette or current_palette()
    ic = icons or current_icons()

    ss = selected_style or Style(reverse=True)
    prefix = cursor_char or "▸"

    vp = state.viewport.with_visible(visible_height).with_content(len(items))
    cursor = state.cursor.with_count(len(items))

    # Determine visible window
    start = vp.offset
    end = min(start + visible_height, len(items))

    # Find max width across visible items (+ 2 for cursor prefix)
    max_width = max((items[i].width for i in range(start, end)), default=0) + 2
    if width is not None:
        max_width = min(max_width, width)

    # Paint into a temporary buffer
    buf = Buffer(max_width, visible_height)

    for row_idx, i in enumerate(range(start, end)):
        is_selected = i == cursor.index
        prefix_char = prefix if is_selected else " "

        # Build a Line: cursor prefix + item spans
        prefix_span = Span(prefix_char + " ", ss if is_selected else Style())
        if is_selected:
            # Merge selected_style as base onto item spans
            row_line = Line(
                spans=(prefix_span,) + items[i].spans,
                style=ss,
            )
        else:
            row_line = Line(
                spans=(prefix_span,) + items[i].spans,
            )

        row_line = row_line.truncate(max_width)
        view = buf.region(0, row_idx, max_width, 1)
        row_line.paint(view, 0, 0)

        # Fill remainder with selected_style if selected
        filled = row_line.width
        if filled < max_width:
            fill_style = ss if is_selected else Style()
            buf.fill(filled, row_idx, max_width - filled, 1, " ", fill_style)

    # Extract rows from buffer into Block
    rows = []
    for y in range(visible_height):
        row = [buf.get(x, y) for x in range(max_width)]
        rows.append(row)

    return Block(rows, max_width)
