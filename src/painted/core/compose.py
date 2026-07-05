"""Composition functions for Block: join, pad, border, truncate, vslice."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from enum import Enum
from typing import NamedTuple, cast

from ._text_width import char_width, display_width, truncate_ellipsis
from .block import Block, _ALIAS_UNSET, _cells_from_text
from .borders import ROUNDED, BorderChars
from .cell import Cell, Style
from ._row_ops import blank_cell, take_row_prefix


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

    has_refs = any((b.ref is not None) or (b._refs is not None) for b in blocks)
    gap_cell = _SPACE_CELL
    if not has_refs:
        if gap == 0 and align is Align.START and all(b.height == max_height for b in blocks):
            n = len(blocks)
            if n == 2:
                b0, b1 = blocks
                return Block._create(
                    tuple(b0.row(i) + b1.row(i) for i in range(max_height)),
                    total_width,
                )
            if n == 3:
                b0, b1, b2 = blocks
                return Block._create(
                    tuple(b0.row(i) + b1.row(i) + b2.row(i) for i in range(max_height)),
                    total_width,
                )
            rows: list[tuple[Cell, ...]] = []
            for row_idx in range(max_height):
                row = tuple()
                for block in blocks:
                    row += block.row(row_idx)
                rows.append(row)
            return Block._create(tuple(rows), total_width)

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

        return Block._create(tuple(rows), total_width)

    rows: list[list[Cell]] = [[] for _ in range(max_height)]
    refs_rows: list[list[str | None]] = [[] for _ in range(max_height)]

    for i, block in enumerate(blocks):
        # Calculate vertical offset for alignment
        offset = _valign_offset(block.height, max_height, align)

        for row_idx in range(max_height):
            src_row = row_idx - offset
            if 0 <= src_row < block.height:
                rows[row_idx].extend(block.row(src_row))
                if block._refs is not None:
                    refs_rows[row_idx].extend(block._refs[src_row])
                elif block.ref is not None:
                    refs_rows[row_idx].extend([block.ref] * block.width)
                else:
                    refs_rows[row_idx].extend([None] * block.width)
            else:
                rows[row_idx].extend([gap_cell] * block.width)
                refs_rows[row_idx].extend([None] * block.width)

            # Add gap cells between blocks (not after the last)
            if i < len(blocks) - 1 and gap > 0:
                rows[row_idx].extend([gap_cell] * gap)
                refs_rows[row_idx].extend([None] * gap)

    return Block(rows, total_width, refs=refs_rows)


def join_vertical(*blocks: Block, gap: int = 0, align: Align = Align.START) -> Block:
    """Join blocks top-to-bottom with optional gap and horizontal alignment."""
    if not blocks:
        return Block.empty(0, 0)

    max_width = max(b.width for b in blocks)
    pad_cell = _SPACE_CELL

    rows: list[list[Cell] | tuple[Cell, ...]] = []
    has_refs = any((b.ref is not None) or (b._refs is not None) for b in blocks)
    refs_rows: list[list[str | None]] | None = [] if has_refs else None

    if refs_rows is None:
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
        return Block._create(tuple(rows), max_width)

    for i, block in enumerate(blocks):
        offset = _halign_offset(block.width, max_width, align)

        for row_idx in range(block.height):
            row: list[Cell] = []
            row_refs: list[str | None] = []
            # Left padding
            if offset > 0:
                row.extend([pad_cell] * offset)
                row_refs.extend([None] * offset)
            # Block content
            row.extend(block.row(row_idx))
            if block._refs is not None:
                row_refs.extend(block._refs[row_idx])
            elif block.ref is not None:
                row_refs.extend([block.ref] * block.width)
            else:
                row_refs.extend([None] * block.width)
            # Right padding
            right_pad = max_width - offset - block.width
            if right_pad > 0:
                row.extend([pad_cell] * right_pad)
                row_refs.extend([None] * right_pad)
            rows.append(row)
            refs_rows.append(row_refs)

        # Insert gap rows between blocks (not after the last)
        if i < len(blocks) - 1 and gap > 0:
            for _ in range(gap):
                rows.append([pad_cell] * max_width)
                refs_rows.append([None] * max_width)

    if refs_rows is None:
        return Block(rows, max_width)
    return Block(rows, max_width, refs=refs_rows)


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
    refs_rows: list[list[str | None]] | None = [] if block._refs is not None else None

    if refs_rows is None:
        pad_left = (space,) * left
        pad_right = (space,) * right
        pad_row = (space,) * new_width
        for _ in range(top):
            rows.append(pad_row)
        for row_idx in range(block.height):
            rows.append(pad_left + block.row(row_idx) + pad_right)
        for _ in range(bottom):
            rows.append(pad_row)
        return Block._create(tuple(rows), new_width, ref=block.ref)

    # Top padding
    for _ in range(top):
        rows.append([space] * new_width)
        refs_rows.append([None] * new_width)

    # Content rows with left/right padding
    for row_idx in range(block.height):
        row: list[Cell] = []
        row_refs: list[str | None] = []
        if left > 0:
            row.extend([space] * left)
            row_refs.extend([None] * left)
        row.extend(block.row(row_idx))
        row_refs.extend(block._refs[row_idx])
        if right > 0:
            row.extend([space] * right)
            row_refs.extend([None] * right)
        rows.append(row)
        refs_rows.append(row_refs)

    # Bottom padding
    for _ in range(bottom):
        rows.append([space] * new_width)
        refs_rows.append([None] * new_width)

    return Block(rows, new_width, refs=refs_rows)


def border(
    block: Block,
    chars: BorderChars = ROUNDED,
    style: Style = Style(),
    title: str | None = None,
    title_style: Style | None = None,
    ref: str | None = None,
    id: object = _ALIAS_UNSET,
) -> Block:
    """Wrap a block with a 1-cell border, optionally with a title in the top row."""
    if id is not _ALIAS_UNSET:
        warnings.warn(
            "border(id=) is deprecated; use ref= (removed at 1.0)",
            DeprecationWarning,
            stacklevel=2,
        )
        ref = cast("str | None", id)
    new_width = block.width + 2
    rows: list[list[Cell] | tuple[Cell, ...]] = []
    has_refs = (ref is not None) or (block._refs is not None)
    refs_rows: list[list[str | None]] | None = [] if has_refs else None
    border_ref: str | None = ref
    if border_ref is None and block._refs is None:
        border_ref = block.ref

    # Top border
    horizontal_cell = _border_cell(chars.horizontal, style)
    top_row: list[Cell] | tuple[Cell, ...]
    if refs_rows is None and title is None:
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

    if refs_rows is None and isinstance(top_row, list):
        top_row = tuple(top_row)
    rows.append(top_row)
    if refs_rows is not None:
        refs_rows.append([border_ref] * new_width)

    # Content rows with vertical borders
    vertical_cell = _border_cell(chars.vertical, style)
    if refs_rows is None:
        for row_idx in range(block.height):
            rows.append((vertical_cell, *block.row(row_idx), vertical_cell))
    else:
        for row_idx in range(block.height):
            rows.append([vertical_cell] + list(block.row(row_idx)) + [vertical_cell])
            inner_refs: list[str | None]
            if block._refs is not None:
                inner_refs = list(block._refs[row_idx])
            elif block.ref is not None:
                inner_refs = [block.ref] * block.width
            else:
                inner_refs = [None] * block.width
            refs_rows.append([border_ref] + inner_refs + [border_ref])

    # Bottom border
    if refs_rows is None:
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
    if refs_rows is not None:
        refs_rows.append([border_ref] * new_width)

    if refs_rows is None:
        return Block._create(tuple(rows), new_width, ref=block.ref)
    return Block(rows, new_width, refs=refs_rows)


def truncate(block: Block, width: int, ellipsis: str | None = None) -> Block:
    """Truncate a block to width, appending ellipsis if truncated.

    ``ellipsis=None`` (the default) reads the ambient ``IconSet.ellipsis`` so the
    marker degrades to ASCII under ``use_icons(ASCII_ICONS)``; pass an explicit
    string to override.
    """
    if block.width <= width:
        return block

    if ellipsis is None:
        from ..icon_set import current_icons

        ellipsis = current_icons().ellipsis
    ellipsis_width = display_width(ellipsis)
    rows: list[list[Cell]] = []
    refs_rows: list[list[str | None]] | None = [] if block._refs is not None else None
    for row_idx in range(block.height):
        src_row = block.row(row_idx)
        src_refs = block._refs[row_idx] if block._refs is not None else None
        if width <= 0:
            rows.append([])
            if refs_rows is not None:
                refs_rows.append([])
        else:
            if ellipsis_width <= 0:
                prefix_budget = width
            elif ellipsis_width >= width:
                prefix_budget = 0
            else:
                prefix_budget = width - ellipsis_width

            prefix_cells, prefix_refs, used = take_row_prefix(src_row, prefix_budget, src_refs)
            style_idx = min(len(src_row) - 1, prefix_budget) if src_row else 0
            fill_style = src_row[style_idx].style if src_row else Style()
            while used < prefix_budget:
                prefix_cells.append(blank_cell(fill_style))
                if prefix_refs is not None and src_refs is not None:
                    prefix_refs.append(src_refs[used])
                used += 1

            ell_style = src_row[style_idx].style if src_row else Style()
            ell_cells = _cells_from_text(ellipsis, ell_style, max_width=width - used)
            if not ell_cells and width > used:
                ell_cells = [blank_cell(ell_style)] * (width - used)

            new_row = prefix_cells + ell_cells
            if len(new_row) < width:
                new_row.extend([blank_cell(ell_style)] * (width - len(new_row)))
            rows.append(new_row)
            if refs_rows is not None:
                if prefix_refs is None:
                    prefix_refs = []
                ell_ref_idx = min(len(src_refs) - 1, prefix_budget) if src_refs else 0
                ell_ref = src_refs[ell_ref_idx] if src_refs else None
                new_refs = list(prefix_refs)
                new_refs.extend([ell_ref] * (width - len(new_refs)))
                refs_rows.append(new_refs)

    if refs_rows is None:
        return Block(rows, width, ref=block.ref)
    return Block(rows, width, refs=refs_rows)


def rule(width: int, *, char: str | None = None, style: Style | None = None) -> Block:
    """A horizontal divider: one row of ``char`` exactly ``width`` columns wide.

    ``char=None`` (the default) reads the ambient ``IconSet.rule`` so the divider
    degrades to ASCII (``-``) under ``use_icons(ASCII_ICONS)``; ``style=None``
    reads ``current_palette().muted``. Honors the width contract exactly (clipped
    or padded to ``width``); ``width <= 0`` yields an empty block.

    Consumers were hand-drawing ``char * n`` plus a fallback; this is the general
    form (a second consumer beyond siftd justified graduating it into painted).
    """
    if width <= 0:
        return Block.empty(0, 0)
    if char is None:
        from ..icon_set import current_icons

        char = current_icons().rule
    if style is None:
        from ..palette import current_palette

        style = current_palette().muted
    return Block.text(char * width, style, width=width)


def fit_to_width(block: Block, width: int) -> Block:
    """Resize a block to EXACTLY ``width`` columns.

    Truncate (with ellipsis) if wider, pad with spaces on the right if narrower,
    identity if already exact. The block-level realization of painted's width
    contract — a passed width is exact (see docs/PRIMITIVES.md). Height is
    unchanged: this is a horizontal-only fit, so it clips rather than reflows. To
    grow height instead of clipping, wrap the content first via
    ``Block.text(..., width=width, wrap=...)`` (which pads each wrapped row to
    width), then this is a no-op. Dissolves to ``compose(truncate, pad)``.
    """
    if width < 0:
        width = 0
    if block.width == width:
        return block
    if block.width > width:
        return truncate(block, width)
    return pad(block, right=width - block.width)


class BudgetFit(NamedTuple):
    """Result of fitting labelled fields into a width budget (``budget_fields``).

    ``text`` is the kept fields, each truncated to fit, joined by the separator.
    ``dropped`` is the number of display columns of field *content* that did not
    appear — from both per-field truncation and whole-field drops, separators
    excluded. The caller turns it into an overflow hint (e.g. ``[+Nc]``) and owns
    that badge's layout; this owns only the allocation.
    """

    text: str
    dropped: int


def budget_fields(
    fields: Sequence[str],
    width: int,
    *,
    min_field: int = 12,
    sep: str = " · ",
) -> BudgetFit:
    """Fit ordered labelled fields into a ``width`` budget, shrink-then-drop.

    A trailing-slot allocator. Render the longest contiguous *prefix* of the
    (non-empty) fields such that each one either fits whole or truncates to at
    least ``min_field`` display columns: the first field claims the full budget,
    each later field pays the separator cost, then takes whatever remains. The
    cutoff is the first field that can be shown as neither — order *is* priority,
    so once a field can't be shown, every field after it drops too (the dropped
    tail becomes the caller's overflow hint instead). ``min_field`` is a *nub*
    floor: it gates truncation only — a field that fits whole is always kept,
    even into a slot narrower than ``min_field`` (a complete short value is not a
    nub). Empty fields are skipped. Width is display columns (wcwidth), so the
    fit is correct for wide/combining characters — counting ``len()`` would
    mis-budget CJK and emoji.

    This is the *shrink-then-drop* track-sizer. It is deliberately distinct from
    ``resolve_column_widths`` (the table sizer): that one keeps every column and
    distributes slack to ``Fill`` columns proportionally, clamping (never
    dropping) at ``min_width`` and never shrinking over-budget content; this one
    keeps an ordered *prefix* of fields, shrinks each to fit, and drops the rest.
    They share only separator accounting — two contracts, not one. (When a second
    drop-style consumer appears, or ``resolve_column_widths`` grows its
    controlled-shrink follow-up, the two may unify under one prioritized
    track-sizer; today the policies are genuinely different.)

    Presentation stays with the caller: the overflow badge and any empty-field
    fallback (e.g. substitute the first non-label field) are the caller's, so
    this function pulls no palette/Style into a pure character-budget contract.

    Returns a :class:`BudgetFit`: ``text`` (kept fields joined by ``sep``) and
    ``dropped`` (Σ field columns − rendered columns; ``0`` iff every field fit
    whole — truncation and whole-field drops both contribute, separators excluded).
    """
    nonempty = [(f, w) for f in fields if (w := display_width(f)) > 0]
    total = sum(w for _, w in nonempty)
    sep_width = display_width(sep)
    parts: list[str] = []
    kept = 0
    remaining = width
    for field, field_width in nonempty:
        sep_cost = sep_width if parts else 0
        available = remaining - sep_cost
        if field_width <= available:
            rendered = field  # fits whole — kept even if available < min_field
        elif available >= min_field:
            rendered = truncate_ellipsis(field, available)  # room for a non-nub prefix
        else:
            break  # neither whole nor a ≥min_field truncation → drop this field and the rest
        rendered_width = display_width(rendered)
        parts.append(rendered)
        kept += rendered_width
        remaining -= sep_cost + rendered_width
    return BudgetFit(text=sep.join(parts), dropped=total - kept)


def vslice(block: Block, offset: int, height: int) -> Block:
    """Extract a vertical slice of rows [offset, offset+height) from a block.

    Clamps offset to [0, block.height]. If offset+height exceeds block height,
    returns fewer rows (no padding). If offset >= block height, returns an
    empty block preserving the original width.
    """
    offset = max(0, min(offset, block.height))
    end = min(offset + height, block.height)

    if offset >= end:
        return Block.empty(block.width, 0, ref=block.ref)

    rows = [list(block.row(r)) for r in range(offset, end)]
    if block._refs is None:
        return Block(rows, block.width, ref=block.ref)
    refs_rows = [list(block._refs[r]) for r in range(offset, end)]
    return Block(rows, block.width, refs=refs_rows)


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
