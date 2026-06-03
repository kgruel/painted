"""Flame lens: proportional horizontal segments (flame graph style)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity

from ...core._text_width import display_width, truncate, truncate_ellipsis
from ...core.block import Block
from ...core.cell import Style
from ...core.compose import fit_to_width, join_horizontal, join_vertical


def _flame_color_for_label(label: str, prev_idx: int, palette: tuple[Style, ...]) -> int:
    """Stable ramp index for a segment label, with adjacent-collision avoidance.

    This is the categorical-ramp assignment that consumes ``Palette.series``
    (position -> style). It is the general form a reusable ramp helper would
    factor out, once a second lens needs categorical coloring.
    """
    idx = hash(label) % len(palette)
    if idx == prev_idx:
        idx = (idx + 1) % len(palette)
    return idx


def flame_lens(
    data: Any,
    zoom: int,
    width: int,
    *,
    height: int | None = None,
    colors: tuple[str, ...] | None = None,
    fidelity: Fidelity | None = None,
) -> Block:
    """Render hierarchical data as proportional segments (flame graph style).

    When height is None (default), renders horizontal rows where each depth
    level is a row with segments filling proportional width.

    When height is provided, renders vertical columns where each segment's
    bar height is proportional to its value.

    Supports:
    - Flat dicts {label: number}: single row/columns of proportional segments
    - Nested dicts {label: {child: number}}: multi-row flame chart (horizontal)

    Zoom levels:
    - 0: Root label + total value as one-liner
    - 1: Top-level segments only
    - 2+: Expand child segments (horizontal: one row per depth; vertical: flat only)

    Args:
        data: Hierarchical dict with numeric leaf values.
        zoom: Zoom level (0+).
        width: Available width in characters.
        height: When set, render vertical columns with this total height.
        colors: Optional per-call ramp as color strings (wrapped to Styles);
            defaults to the ambient palette's ``series`` categorical ramp.

    Returns:
        Block with rendered flame chart.
    """
    palette: tuple[Style, ...]
    if colors is not None:
        palette = tuple(Style(fg=c) for c in colors)
    else:
        from ...palette import current_palette

        palette = current_palette().series
    if width <= 0:
        return Block.empty(0, 1)

    segments = _flame_extract(data)
    if not segments:
        return Block.text("(no data)", Style(), width=width)

    total = _flame_total(segments)

    if zoom <= 0:
        text = f"flame: {total:.4g}"
        if display_width(text) > width:
            text = truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
        return Block.text(text, Style(), width=width)

    if height is not None:
        # Vertical orientation
        return fit_to_width(
            _flame_render_vertical(segments, total, width, height, zoom, palette), width
        )

    if zoom == 1:
        # Single row: top-level segments only. Floored proportional widths (and a
        # val<=0 last segment) can sum to < width, so fit to the exact contract width.
        return fit_to_width(_flame_render_row(segments, total, width, palette=palette), width)

    # zoom >= 2: expand children into additional rows
    rows: list[Block] = []
    _flame_render_levels(segments, total, width, zoom, rows=rows, palette=palette)
    if not rows:
        return Block.text("(no data)", Style(), width=width)
    # Per-row widths can drift below width (floored allocation, skipped 0-width
    # segments); fit the assembled rows to the exact contract width.
    return fit_to_width(join_vertical(*rows), width)


def _flame_extract(data: Any) -> list[tuple[str, Any]]:
    """Extract [(label, value_or_children)] from data.

    Leaf entries have numeric values. Branch entries have dict children.
    """
    if not isinstance(data, dict) or not data:
        return []
    result: list[tuple[str, Any]] = []
    for k, v in data.items():
        result.append((str(k), v))
    return sorted(result, key=lambda x: x[0])


def _flame_total(segments: list[tuple[str, Any]]) -> float:
    """Recursively sum all numeric leaf values in segments."""
    total = 0.0
    for _, v in segments:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += float(v)
        elif isinstance(v, dict):
            total += _flame_total([(str(ck), cv) for ck, cv in v.items()])
    return total


def _flame_allocate_widths(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
) -> list[int]:
    """Compute proportional widths for segments, fitting labels where possible.

    Two-pass algorithm:
    1. Assign proportional widths based on segment values.
    2. Redistribute surplus from large segments to small ones that can't
       fit their labels, stealing only from donors with excess.
    """
    n = len(segments)
    if n == 0:
        return []

    seg_widths = [0] * n

    # Pass 1: proportional widths
    for i, (_label, v) in enumerate(segments):
        val = _seg_value(v)
        if total <= 0:
            seg_widths[i] = width // n if i < n - 1 else width - sum(seg_widths[:i])
        elif val <= 0:
            seg_widths[i] = 1
        elif i < n - 1:
            seg_widths[i] = max(1, int(width * val / total))
        else:
            seg_widths[i] = width - sum(seg_widths[:i])

    # Pass 2: steal from large segments to fit labels
    for i, (label, _v) in enumerate(segments):
        label_w = display_width(label)
        if seg_widths[i] < label_w:
            deficit = label_w - seg_widths[i]
            donors = sorted(range(n), key=lambda j: seg_widths[j], reverse=True)
            for d in donors:
                if d == i:
                    continue
                give = min(deficit, seg_widths[d] - max(1, display_width(segments[d][0])))
                if give > 0:
                    seg_widths[d] -= give
                    seg_widths[i] += give
                    deficit -= give
                if deficit <= 0:
                    break

    return seg_widths


def _flame_render_row(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
    palette: tuple[Style, ...],
) -> Block:
    """Build one row of proportional segments with per-label coloring."""
    if width <= 0:
        return Block.empty(0, 1)

    seg_widths = _flame_allocate_widths(segments, total, width)

    # Build segment blocks with per-label color
    blocks: list[Block] = []
    prev_color_idx = -1
    used_width = 0
    for (label, _v), seg_w in zip(segments, seg_widths):
        seg_w = max(0, min(seg_w, width - used_width))
        used_width += seg_w
        if seg_w <= 0:
            continue
        color_idx = _flame_color_for_label(label, prev_color_idx, palette)
        prev_color_idx = color_idx
        style = palette[color_idx].merge(Style(reverse=True))
        text = truncate(label, seg_w) if display_width(label) > seg_w else label
        pad_needed = seg_w - display_width(text)
        text = text + " " * max(0, pad_needed)
        blocks.append(Block.text(text, style))

    if not blocks:
        return Block.empty(width, 1)
    return join_horizontal(*blocks)


def _flame_render_levels(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
    remaining_zoom: int,
    rows: list[Block],
    palette: tuple[Style, ...],
) -> None:
    """Recursively render flame rows, one per depth level."""
    if not segments or width <= 0:
        return

    # Render this level
    rows.append(_flame_render_row(segments, total, width, palette=palette))

    if remaining_zoom <= 1:
        return

    # Expand children: each parent's children occupy that parent's proportional width
    seg_widths = _flame_allocate_widths(segments, total, width)
    child_blocks: list[Block] = []
    used_width = 0
    prev_color_idx = -1

    for (label, v), seg_w in zip(segments, seg_widths):
        seg_w = max(0, min(seg_w, width - used_width))
        used_width += seg_w

        if seg_w <= 0:
            continue

        if isinstance(v, dict) and v:
            child_segments = sorted([(str(ck), cv) for ck, cv in v.items()], key=lambda x: x[0])
            child_total = _flame_total(child_segments)
            child_blocks.append(
                _flame_render_row(child_segments, child_total, seg_w, palette=palette)
            )
        else:
            # Leaf at this level — per-label color
            color_idx = _flame_color_for_label(label, prev_color_idx, palette)
            prev_color_idx = color_idx
            child_style = palette[color_idx].merge(Style(reverse=True))
            text = truncate(label, seg_w) if display_width(label) > seg_w else label
            pad_needed = seg_w - display_width(text)
            text = text + " " * max(0, pad_needed)
            child_blocks.append(Block.text(text, child_style))

    if child_blocks:
        rows.append(join_horizontal(*child_blocks))

    # Recurse deeper if zoom allows
    if remaining_zoom > 2:
        _flame_expand_deeper(segments, total, width, remaining_zoom, rows, palette=palette)


def _flame_expand_deeper(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
    remaining_zoom: int,
    rows: list[Block],
    palette: tuple[Style, ...],
) -> None:
    """Expand deeper levels for segments with grandchildren."""
    seg_widths = _flame_allocate_widths(segments, total, width)
    child_blocks: list[Block] = []
    used_width = 0
    has_content = False

    for (_label, v), seg_w in zip(segments, seg_widths):
        seg_w = max(0, min(seg_w, width - used_width))
        used_width += seg_w

        if seg_w <= 0:
            continue

        if isinstance(v, dict) and v:
            child_segments = sorted([(str(ck), cv) for ck, cv in v.items()], key=lambda x: x[0])
            child_total = _flame_total(child_segments)
            # Check if any children have dict grandchildren
            has_grandchildren = any(isinstance(cv, dict) and cv for _, cv in child_segments)
            if has_grandchildren:
                sub_rows: list[Block] = []
                _flame_render_levels(
                    child_segments,
                    child_total,
                    seg_w,
                    remaining_zoom - 1,
                    sub_rows,
                    palette=palette,
                )
                # Skip the first row (already rendered at this level); take the second
                if len(sub_rows) > 1:
                    has_content = True
                    child_blocks.append(sub_rows[1])
                else:
                    child_blocks.append(Block.empty(seg_w, 1))
            else:
                child_blocks.append(Block.empty(seg_w, 1))
        else:
            child_blocks.append(Block.empty(seg_w, 1))

    if has_content and child_blocks:
        rows.append(join_horizontal(*child_blocks))


def _flame_render_vertical(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
    height: int,
    zoom: int,
    palette: tuple[Style, ...],
) -> Block:
    """Render segments as vertical columns (height = cost)."""
    n = len(segments)
    if n == 0 or height <= 0:
        return Block.empty(width, 1)

    col_width = width // n
    if col_width < 1:
        col_width = 1

    chart_height = max(1, height - 1)  # reserve 1 row for labels
    max_value = max(_seg_value(v) for _, v in segments)
    if max_value <= 0:
        max_value = 1.0

    columns: list[Block] = []
    prev_color_idx = -1

    for i, (label, v) in enumerate(segments):
        # Actual column width — last column absorbs remainder
        cw = col_width if i < n - 1 else width - col_width * (n - 1)
        if cw <= 0:
            continue

        val = _seg_value(v)
        bar_height = max(1, round(val / max_value * chart_height))
        empty_height = chart_height - bar_height

        color_idx = _flame_color_for_label(label, prev_color_idx, palette)
        prev_color_idx = color_idx
        bar_style = palette[color_idx].merge(Style(reverse=True))

        # Label row (bottom)
        label_text = truncate(label, cw) if display_width(label) > cw else label
        if display_width(label_text) == len(label_text):
            label_centered = label_text.center(cw)[:cw]
        else:
            pad_total = max(0, cw - display_width(label_text))
            left = pad_total // 2
            right = pad_total - left
            label_centered = " " * left + label_text + " " * right
        label_block = Block.text(label_centered, Style(dim=True), width=cw)

        parts: list[Block] = []
        if empty_height > 0:
            parts.append(Block.empty(cw, empty_height))
        parts.append(Block.empty(cw, bar_height, bar_style))
        parts.append(label_block)

        columns.append(join_vertical(*parts))

    if not columns:
        return Block.empty(width, 1)
    return join_horizontal(*columns)


def _seg_value(v: Any) -> float:
    """Get numeric value of a segment (leaf or recursive total)."""
    if isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return _flame_total([(str(k), val) for k, val in v.items()])
    return 0.0
