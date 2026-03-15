"""Composition functions for Block: join, pad, border, truncate, vslice."""

from __future__ import annotations

from enum import Enum

from ._text_width import char_width, display_width
from .block import Block
from .borders import ROUNDED, BorderChars
from .cell import Cell, Style


class Align(Enum):
    START = "start"  # top or left
    CENTER = "center"
    END = "end"  # bottom or right


# Cached default-style space cell for gap/pad operations.
_SPACE_CELL = Cell(" ", Style())

# Cache for border cells keyed by (char, style).
_border_cell_cache: dict[tuple[str, Style], Cell] = {}


def _border_cell(char: str, style: Style) -> Cell:
    key = (char, style)
    cell = _border_cell_cache.get(key)
    if cell is not None:
        return cell
    cell = Cell(char, style)
    _border_cell_cache[key] = cell
    return cell


def join_horizontal(*blocks: Block, gap: int = 0, align: Align = Align.START) -> Block:
    """Join blocks left-to-right with optional gap and vertical alignment."""
    if not blocks:
        return Block.empty(0, 0)

    max_height = max(b.height for b in blocks)
    total_width = sum(b.width for b in blocks) + gap * (len(blocks) - 1)

    has_ids = any((b.id is not None) or (b._ids is not None) for b in blocks)
    gap_cell = _SPACE_CELL
    if not has_ids:
        if gap == 0 and align is Align.START and all(b.height == max_height for b in blocks):
            rows: list[tuple[Cell, ...]] = []
            for row_idx in range(max_height):
                row = tuple()
                for block in blocks:
                    row += block.row(row_idx)
                rows.append(row)
            return Block(rows, total_width)

        rows: list[tuple[Cell, ...]] = [tuple() for _ in range(max_height)]
        gap_cells = (gap_cell,) * gap
        for i, block in enumerate(blocks):
            # Calculate vertical offset for alignment
            offset = _valign_offset(block.height, max_height, align)
            blank_row = (gap_cell,) * block.width

            for row_idx in range(max_height):
                src_row = row_idx - offset
                if 0 <= src_row < block.height:
                    rows[row_idx] += block.row(src_row)
                else:
                    rows[row_idx] += blank_row

                # Add gap cells between blocks (not after the last)
                if i < len(blocks) - 1 and gap > 0:
                    rows[row_idx] += gap_cells

        return Block(rows, total_width)

    rows: list[list[Cell]] = [[] for _ in range(max_height)]
    ids_rows: list[list[str | None]] = [[] for _ in range(max_height)]

    for i, block in enumerate(blocks):
        # Calculate vertical offset for alignment
        offset = _valign_offset(block.height, max_height, align)

        for row_idx in range(max_height):
            src_row = row_idx - offset
            if 0 <= src_row < block.height:
                rows[row_idx].extend(block.row(src_row))
                if block._ids is not None:
                    ids_rows[row_idx].extend(block._ids[src_row])
                elif block.id is not None:
                    ids_rows[row_idx].extend([block.id] * block.width)
                else:
                    ids_rows[row_idx].extend([None] * block.width)
            else:
                rows[row_idx].extend([gap_cell] * block.width)
                ids_rows[row_idx].extend([None] * block.width)

            # Add gap cells between blocks (not after the last)
            if i < len(blocks) - 1 and gap > 0:
                rows[row_idx].extend([gap_cell] * gap)
                ids_rows[row_idx].extend([None] * gap)

    return Block(rows, total_width, ids=ids_rows)


def join_vertical(*blocks: Block, gap: int = 0, align: Align = Align.START) -> Block:
    """Join blocks top-to-bottom with optional gap and horizontal alignment."""
    if not blocks:
        return Block.empty(0, 0)

    max_width = max(b.width for b in blocks)
    pad_cell = _SPACE_CELL

    rows: list[list[Cell] | tuple[Cell, ...]] = []
    has_ids = any((b.id is not None) or (b._ids is not None) for b in blocks)
    ids_rows: list[list[str | None]] | None = [] if has_ids else None

    if ids_rows is None:
        gap_row = (pad_cell,) * max_width
        for i, block in enumerate(blocks):
            offset = _halign_offset(block.width, max_width, align)
            pad_left = (pad_cell,) * offset
            pad_right = (pad_cell,) * (max_width - offset - block.width)
            for row_idx in range(block.height):
                rows.append(pad_left + block.row(row_idx) + pad_right)
            if i < len(blocks) - 1 and gap > 0:
                for _ in range(gap):
                    rows.append(gap_row)
        return Block(rows, max_width)

    for i, block in enumerate(blocks):
        offset = _halign_offset(block.width, max_width, align)

        for row_idx in range(block.height):
            row: list[Cell] = []
            row_ids: list[str | None] = []
            # Left padding
            if offset > 0:
                row.extend([pad_cell] * offset)
                row_ids.extend([None] * offset)
            # Block content
            row.extend(block.row(row_idx))
            if block._ids is not None:
                row_ids.extend(block._ids[row_idx])
            elif block.id is not None:
                row_ids.extend([block.id] * block.width)
            else:
                row_ids.extend([None] * block.width)
            # Right padding
            right_pad = max_width - offset - block.width
            if right_pad > 0:
                row.extend([pad_cell] * right_pad)
                row_ids.extend([None] * right_pad)
            rows.append(row)
            ids_rows.append(row_ids)

        # Insert gap rows between blocks (not after the last)
        if i < len(blocks) - 1 and gap > 0:
            for _ in range(gap):
                rows.append([pad_cell] * max_width)
                ids_rows.append([None] * max_width)

    if ids_rows is None:
        return Block(rows, max_width)
    return Block(rows, max_width, ids=ids_rows)


def pad(
    block: Block,
    *,
    left: int = 0,
    right: int = 0,
    top: int = 0,
    bottom: int = 0,
    style: Style = Style(),
) -> Block:
    """Add empty cell padding around a block."""
    new_width = block.width + left + right
    space = _border_cell(" ", style)

    rows: list[list[Cell] | tuple[Cell, ...]] = []
    ids_rows: list[list[str | None]] | None = [] if block._ids is not None else None

    if ids_rows is None:
        pad_left = (space,) * left
        pad_right = (space,) * right
        pad_row = (space,) * new_width
        for _ in range(top):
            rows.append(pad_row)
        for row_idx in range(block.height):
            rows.append(pad_left + block.row(row_idx) + pad_right)
        for _ in range(bottom):
            rows.append(pad_row)
        return Block(rows, new_width, id=block.id)

    # Top padding
    for _ in range(top):
        rows.append([space] * new_width)
        ids_rows.append([None] * new_width)

    # Content rows with left/right padding
    for row_idx in range(block.height):
        row: list[Cell] = []
        row_ids: list[str | None] = []
        if left > 0:
            row.extend([space] * left)
            row_ids.extend([None] * left)
        row.extend(block.row(row_idx))
        row_ids.extend(block._ids[row_idx])
        if right > 0:
            row.extend([space] * right)
            row_ids.extend([None] * right)
        rows.append(row)
        ids_rows.append(row_ids)

    # Bottom padding
    for _ in range(bottom):
        rows.append([space] * new_width)
        ids_rows.append([None] * new_width)

    if ids_rows is None:
        return Block(rows, new_width, id=block.id)
    return Block(rows, new_width, ids=ids_rows)


def border(
    block: Block,
    chars: BorderChars = ROUNDED,
    style: Style = Style(),
    title: str | None = None,
    title_style: Style | None = None,
    id: str | None = None,
) -> Block:
    """Wrap a block with a 1-cell border, optionally with a title in the top row."""
    new_width = block.width + 2
    rows: list[list[Cell] | tuple[Cell, ...]] = []
    has_ids = (id is not None) or (block._ids is not None)
    ids_rows: list[list[str | None]] | None = [] if has_ids else None
    border_id: str | None = id
    if border_id is None and block._ids is None:
        border_id = block.id

    # Top border
    horizontal_cell = _border_cell(chars.horizontal, style)
    top_row: list[Cell] | tuple[Cell, ...]
    if ids_rows is None and title is None:
        top_row = (
            (_border_cell(chars.top_left, style),)
            + (horizontal_cell,) * block.width
            + (_border_cell(chars.top_right, style),)
        )
    else:
        top_row = (
            [_border_cell(chars.top_left, style)]
            + [horizontal_cell] * block.width
            + [_border_cell(chars.top_right, style)]
        )

    # Paint title into top row if provided
    title_width = display_width(title) if title else 0
    # Title is painted starting at index 2 (leaving one horizontal cell intact).
    # Ensure we don't overwrite the top_right corner.
    if title and block.width >= title_width + 3:
        ts = title_style if title_style is not None else style
        pos = 2  # start after top_left + 1 padding cell
        # Space before title
        space_cell = _border_cell(" ", ts)
        top_row[pos] = space_cell
        pos += 1
        for ch in title:
            w = char_width(ch)
            if w == 0:
                continue
            if pos > block.width:
                break
            if w == 2 and pos + 1 > block.width:
                break
            top_row[pos] = _border_cell(ch, ts)
            if w == 2:
                top_row[pos + 1] = space_cell
            pos += w
        # Space after title
        if pos <= block.width:
            top_row[pos] = space_cell

    rows.append(top_row)
    if ids_rows is not None:
        ids_rows.append([border_id] * new_width)

    # Content rows with vertical borders
    vertical_cell = _border_cell(chars.vertical, style)
    if ids_rows is None:
        for row_idx in range(block.height):
            rows.append((vertical_cell, *block.row(row_idx), vertical_cell))
    else:
        for row_idx in range(block.height):
            rows.append([vertical_cell] + list(block.row(row_idx)) + [vertical_cell])
            inner_ids: list[str | None]
            if block._ids is not None:
                inner_ids = list(block._ids[row_idx])
            elif block.id is not None:
                inner_ids = [block.id] * block.width
            else:
                inner_ids = [None] * block.width
            ids_rows.append([border_id] + inner_ids + [border_id])

    # Bottom border
    if ids_rows is None:
        bottom_row = (
            (_border_cell(chars.bottom_left, style),)
            + (horizontal_cell,) * block.width
            + (_border_cell(chars.bottom_right, style),)
        )
    else:
        bottom_row = (
            [_border_cell(chars.bottom_left, style)]
            + [horizontal_cell] * block.width
            + [_border_cell(chars.bottom_right, style)]
        )
    rows.append(bottom_row)
    if ids_rows is not None:
        ids_rows.append([border_id] * new_width)

    if ids_rows is None:
        return Block(rows, new_width, id=block.id)
    return Block(rows, new_width, ids=ids_rows)


def truncate(block: Block, width: int, ellipsis: str = "…") -> Block:
    """Truncate a block to width, appending ellipsis if truncated."""
    if block.width <= width:
        return block

    rows: list[list[Cell]] = []
    ids_rows: list[list[str | None]] | None = [] if block._ids is not None else None
    for row_idx in range(block.height):
        src_row = block.row(row_idx)
        if width <= 0:
            rows.append([])
            if ids_rows is not None:
                ids_rows.append([])
        elif width == 1:
            # Only room for ellipsis
            rows.append([Cell(ellipsis, src_row[0].style)])
            if ids_rows is not None:
                ids_rows.append([block._ids[row_idx][0]])
        else:
            new_row = list(src_row[: width - 1])
            new_row.append(Cell(ellipsis, src_row[width - 1].style))
            rows.append(new_row)
            if ids_rows is not None:
                src_ids = block._ids[row_idx]
                new_ids = list(src_ids[: width - 1])
                new_ids.append(src_ids[width - 1])
                ids_rows.append(new_ids)

    if ids_rows is None:
        return Block(rows, width, id=block.id)
    return Block(rows, width, ids=ids_rows)


def vslice(block: Block, offset: int, height: int) -> Block:
    """Extract a vertical slice of rows [offset, offset+height) from a block.

    Clamps offset to [0, block.height]. If offset+height exceeds block height,
    returns fewer rows (no padding). If offset >= block height, returns an
    empty block preserving the original width.
    """
    offset = max(0, min(offset, block.height))
    end = min(offset + height, block.height)

    if offset >= end:
        return Block.empty(block.width, 0, id=block.id)

    rows = [list(block.row(r)) for r in range(offset, end)]
    if block._ids is None:
        return Block(rows, block.width, id=block.id)
    ids_rows = [list(block._ids[r]) for r in range(offset, end)]
    return Block(rows, block.width, ids=ids_rows)


def _valign_offset(block_height: int, container_height: int, align: Align) -> int:
    """Calculate vertical offset for alignment within a container."""
    diff = container_height - block_height
    if align == Align.START:
        return 0
    elif align == Align.CENTER:
        return diff // 2
    else:  # END
        return diff


def _halign_offset(block_width: int, container_width: int, align: Align) -> int:
    """Calculate horizontal offset for alignment within a container."""
    diff = container_width - block_width
    if align == Align.START:
        return 0
    elif align == Align.CENTER:
        return diff // 2
    else:  # END
        return diff


def join_responsive(
    *blocks: Block,
    available_width: int,
    gap: int = 0,
    align: Align = Align.START,
) -> Block:
    """Join blocks horizontally if they fit, vertically if not.

    Args:
        blocks: Blocks to compose
        available_width: Container width to fit within
        gap: Space between blocks
        align: Alignment for both orientations

    Returns:
        Horizontal join if total width fits, vertical join otherwise.
    """
    if not blocks:
        return Block.empty(0, 0)

    total_width = sum(b.width for b in blocks) + gap * (len(blocks) - 1)

    if total_width <= available_width:
        return join_horizontal(*blocks, gap=gap, align=align)
    else:
        return join_vertical(*blocks, gap=gap, align=align)
