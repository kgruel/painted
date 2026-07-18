"""Flame lens: proportional horizontal segments (flame graph style)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity

from ...core._text_width import display_width, truncate, truncate_ellipsis
from ...core.block import Block
from ...core.cell import Style
from ...core.compose import fit_to_width, join_horizontal, join_vertical
from ...palette import series_index


def _flame_color_for_label(label: str, prev_idx: int, palette: tuple[Style, ...]) -> int:
    """Stable ramp index for a segment label, with adjacent-collision avoidance.

    Routes through the shared ``series_index`` digest (the categorical-ramp
    assignment that consumes ``Palette.series``) so a label lands on the same
    color in every process — builtin ``hash()`` was ``PYTHONHASHSEED``-randomized.
    The adjacent-sibling avoidance stays local: it is a flame-shaped concern (two
    touching segments shouldn't share a color), not part of the ramp mapping.
    """
    idx = series_index(label, len(palette))
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
    # An empty ramp degrades to the bare Style — the same §5 contract as
    # Palette.series_for, never an IndexError from indexing into ().
    if not palette:
        palette = (Style(),)
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


def _flame_row_layout(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
) -> tuple[list[int], tuple[int, int] | None]:
    """Partition a row into rendered segment widths + an optional tail remainder.

    RENDER_MODEL law 6: a positive-valued segment allocated zero cells vanishes,
    and the viewer cannot tell a zero from a below-raster value — worse, the
    label sort silently decides *which* tail segment disappears. Such dropped
    positives merge into a single REMAINDER segment at the tail of the row; the
    aggregate IS the evidence, preserving the chart's proportional shape rather
    than an added row.

    Returns ``(widths, remainder)``:

    - ``widths`` — cell width per segment, parallel to ``segments`` (0 for a
      segment merged into the remainder, or an honestly-absent zero/negative).
    - ``remainder`` — ``(width, count)`` for the tail aggregate: its reserved
      cells and the number of positive segments folded in. ``None`` when every
      positive segment renders — then the layout is byte-identical to pre-0.14
      (no remainder without loss).

    Allocation reasoning: the remainder's footprint is the proportional share its
    merged members' combined value earns under the lens's existing arithmetic
    (``int(width * merged_value / total)``, floored to >= 1 as the minimal
    evidence cell). It is reserved off the top, so survivors allocate into the
    rest and surrender no more than that combined share. Determination is a fixed
    point: reserve the current remainder, allocate survivors, and fold any
    positive survivor still starved of a cell into the remainder — repeating
    until the partition is stable (each round folds >= 1 segment, so it
    terminates). Membership is taken over the label-sorted segment order
    (``_flame_extract``), so it never depends on dict/iteration order.
    Zero/negative segments owe nothing — their absence is the proportional truth.
    """
    n = len(segments)
    values = [_seg_value(v) for _, v in segments]
    merged: list[int] = []
    merged_set: set[int] = set()

    while True:
        keep = [i for i in range(n) if i not in merged_set]
        if merged:
            rem_value = sum(values[i] for i in merged)
            rem_w = max(1, int(width * rem_value / total)) if total > 0 else 1
            rem_w = min(rem_w, width)
        else:
            rem_w = 0
        avail = width - rem_w

        if keep and avail > 0:
            alloc = _flame_allocate_widths([segments[i] for i in keep], total, avail)
        else:
            alloc = [0] * len(keep)

        # Mirror the render clamp: earlier segments consume the available width.
        cells = [0] * len(keep)
        used = 0
        for j, w in enumerate(alloc):
            c = max(0, min(w, avail - used))
            cells[j] = c
            used += c

        newly = [keep[j] for j in range(len(keep)) if cells[j] <= 0 and values[keep[j]] > 0]
        if newly:
            merged.extend(newly)
            merged_set.update(newly)
            continue

        widths = [0] * n
        for j, i in enumerate(keep):
            widths[i] = cells[j]
        remainder = (rem_w, len(merged)) if merged else None
        return widths, remainder


def _flame_fit_label(label: str, width: int) -> str:
    """Fit a segment label to ``width`` cells, marking the cut with the ambient
    ellipsis where the segment is wider than one cell (RENDER_MODEL law 6); at
    one cell the physical-space waiver stands (no room for content + mark)."""
    if display_width(label) <= width:
        return label
    return truncate_ellipsis(label, width) if width > 1 else truncate(label, width)


def _flame_remainder_text(count: int, width: int) -> str:
    """The remainder marker: ``+N`` where the cells can spell it, else the ambient
    ellipsis as the minimal resolution-loss mark (physical-space waiver)."""
    from ...icon_set import current_icons

    label = f"+{count}"
    if display_width(label) <= width:
        return label
    ellipsis = current_icons().ellipsis
    if display_width(ellipsis) <= width:
        return ellipsis
    return truncate(ellipsis, width)


def _flame_remainder_block(count: int, width: int) -> Block:
    """A muted tail segment marking the merged positives — evidence, not data
    (its own ``muted`` role, never a series color)."""
    from ...palette import current_palette

    text = _flame_remainder_text(count, width)
    text = text + " " * max(0, width - display_width(text))
    return Block.text(text, current_palette().muted)


def _flame_build_row(
    segments: list[tuple[str, Any]],
    widths: list[int],
    remainder: tuple[int, int] | None,
    width: int,
    palette: tuple[Style, ...],
) -> Block:
    """Assemble one flame row from a computed layout (segments + optional remainder)."""
    blocks: list[Block] = []
    prev_color_idx = -1
    for (label, _v), seg_w in zip(segments, widths):
        if seg_w <= 0:
            continue
        color_idx = _flame_color_for_label(label, prev_color_idx, palette)
        prev_color_idx = color_idx
        style = palette[color_idx].merge(Style(reverse=True))
        text = _flame_fit_label(label, seg_w)
        text = text + " " * max(0, seg_w - display_width(text))
        blocks.append(Block.text(text, style))

    if remainder is not None:
        blocks.append(_flame_remainder_block(remainder[1], remainder[0]))

    if not blocks:
        return Block.empty(width, 1)
    return join_horizontal(*blocks)


def _flame_render_row(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
    palette: tuple[Style, ...],
) -> Block:
    """Build one row of proportional segments with per-label coloring.

    Positive segments starved of a cell merge into a muted tail remainder
    (``_flame_row_layout``); labels wider than their segment ellipsize.
    """
    if width <= 0:
        return Block.empty(0, 1)

    widths, remainder = _flame_row_layout(segments, total, width)
    return _flame_build_row(segments, widths, remainder, width, palette)


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

    # Render this level. The same layout drives the child expansion below, so a
    # parent folded into the remainder is skipped consistently in both rows.
    widths, remainder = _flame_row_layout(segments, total, width)
    rows.append(_flame_build_row(segments, widths, remainder, width, palette))

    if remaining_zoom <= 1:
        return

    # Expand children: each rendered parent's children occupy that parent's width.
    child_blocks: list[Block] = []
    prev_color_idx = -1

    for (label, v), seg_w in zip(segments, widths):
        if seg_w <= 0:
            continue

        if isinstance(v, dict) and v:
            child_segments = sorted([(str(ck), cv) for ck, cv in v.items()], key=lambda x: x[0])
            child_total = _flame_total(child_segments)
            # Fit to the parent's exact footprint: a child row can floor narrower
            # than seg_w (e.g. a trailing zero-valued child), and an unfitted band
            # would shift every later parent's columns left.
            child_blocks.append(
                fit_to_width(
                    _flame_render_row(child_segments, child_total, seg_w, palette=palette), seg_w
                )
            )
        else:
            # Leaf at this level — per-label color
            color_idx = _flame_color_for_label(label, prev_color_idx, palette)
            prev_color_idx = color_idx
            child_style = palette[color_idx].merge(Style(reverse=True))
            text = _flame_fit_label(label, seg_w)
            text = text + " " * max(0, seg_w - display_width(text))
            child_blocks.append(Block.text(text, child_style))

    # The remainder holds no children — reserve its tail columns to stay aligned.
    if remainder is not None:
        child_blocks.append(Block.empty(remainder[0], 1))

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
    """Render every level below the child row, one row per depth.

    Each rendered parent's subtree is expanded to its full remaining depth
    (``sub_rows[1:]`` — every row *below* the child row already emitted at the
    caller's level, not just the first). The per-parent depth lists are then
    composed side by side, depth by depth, under each parent's footprint —
    padding a parent that bottoms out early with blank columns and reserving the
    remainder's tail columns — so a deeply-nested branch (and any remainder it
    carries at that depth) renders instead of being discarded after one level.
    """
    # Same deterministic layout as the level row, so deeper rows stay aligned and
    # a remainder-folded parent is skipped here too.
    widths, remainder = _flame_row_layout(segments, total, width)

    # For each rendered parent, collect its rows below the child row (depths >= 2
    # relative to this level). Leaves and childless branches contribute nothing.
    per_parent: list[tuple[int, list[Block]]] = []
    for (_label, v), seg_w in zip(segments, widths):
        if seg_w <= 0:
            continue

        deeper: list[Block] = []
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
                # Skip the child row (already rendered at this level); keep every
                # row below it so the full remaining depth reaches the output.
                deeper = sub_rows[1:]
        per_parent.append((seg_w, deeper))

    rem_w = remainder[0] if remainder is not None else 0
    depth = max((len(d) for _, d in per_parent), default=0)

    for di in range(depth):
        row_blocks: list[Block] = []
        for seg_w, deeper in per_parent:
            # Present branch at this depth, or blank columns for an absent one.
            # Fit every present recursive row to its parent's exact footprint:
            # proportional flooring can leave it narrower, and an unfitted row
            # would shift every later parent's columns left (the outer fit only
            # pads the right edge — it cannot restore an internal boundary).
            if di < len(deeper):
                row_blocks.append(fit_to_width(deeper[di], seg_w))
            else:
                row_blocks.append(Block.empty(seg_w, 1))
        # Reserve the remainder's tail columns at every depth for alignment.
        if rem_w:
            row_blocks.append(Block.empty(rem_w, 1))
        if row_blocks:
            rows.append(join_horizontal(*row_blocks))


def _flame_render_vertical(
    segments: list[tuple[str, Any]],
    total: float,
    width: int,
    height: int,
    zoom: int,
    palette: tuple[Style, ...],
) -> Block:
    """Render segments as vertical columns (height = cost).

    Columns are equal-width, so vanishing here is a *seating* loss: when there
    are more segments than the width can seat at >= 1 column each, the dropped
    positives merge into a muted remainder column at the tail (RENDER_MODEL law
    6, the same ruling as the horizontal row). Dropped zeros owe nothing.
    """
    n = len(segments)
    if n == 0 or height <= 0:
        return Block.empty(width, 1)

    # Column specs: (label, value, is_remainder, count). A tail remainder appears
    # only when the segments cannot all be seated (n > width, so col_width == 1
    # cannot hold them). Membership follows the label-sorted order, deterministic.
    if n <= width:
        specs: list[tuple[str, float, bool, int]] = [
            (label, _seg_value(v), False, 0) for label, v in segments
        ]
    else:
        shown = segments[: width - 1]
        tail = segments[width - 1 :]
        merged_positive = [(label, _seg_value(v)) for label, v in tail if _seg_value(v) > 0]
        if merged_positive:
            specs = [(label, _seg_value(v), False, 0) for label, v in shown]
            rem_value = sum(val for _, val in merged_positive)
            specs.append(("", rem_value, True, len(merged_positive)))
        else:
            # The unseatable tail is all zero — honest absence, no remainder.
            specs = [(label, _seg_value(v), False, 0) for label, v in segments[:width]]

    m = len(specs)
    col_width = max(1, width // m)
    chart_height = max(1, height - 1)  # reserve 1 row for labels
    max_value = max((val for _, val, _, _ in specs), default=0.0)
    if max_value <= 0:
        max_value = 1.0

    columns: list[Block] = []
    prev_color_idx = -1

    for i, (label, val, is_rem, count) in enumerate(specs):
        # Actual column width — last column absorbs remainder
        cw = col_width if i < m - 1 else width - col_width * (m - 1)
        if cw <= 0:
            continue

        bar_height = max(1, round(val / max_value * chart_height))
        empty_height = chart_height - bar_height

        if is_rem:
            from ...palette import current_palette

            muted = current_palette().muted
            bar_style = muted
            label_style = muted
            label_text = _flame_remainder_text(count, cw)
        else:
            color_idx = _flame_color_for_label(label, prev_color_idx, palette)
            prev_color_idx = color_idx
            bar_style = palette[color_idx].merge(Style(reverse=True))
            label_style = Style(dim=True)
            label_text = _flame_fit_label(label, cw)

        # Label row (bottom)
        if display_width(label_text) == len(label_text):
            label_centered = label_text.center(cw)[:cw]
        else:
            pad_total = max(0, cw - display_width(label_text))
            left = pad_total // 2
            right = pad_total - left
            label_centered = " " * left + label_text + " " * right
        label_block = Block.text(label_centered, label_style, width=cw)

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
