"""Chart lens: text-based visualizations for numeric data."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..._sparkline_core import sparkline_text
from ...core._text_width import display_width, truncate_ellipsis, truncate
from ...core.block import Block
from ...core.cell import Style
from ...core.compose import join_vertical

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity
    from ...icon_set import IconSet


def _get_chart_icons(icons: IconSet | None) -> tuple[str | tuple[str, ...], str, str]:
    """Get chart characters from icons or ambient defaults."""
    from ...icon_set import current_icons

    ic = icons or current_icons()
    return ic.sparkline, ic.bar_fill, ic.bar_empty


def chart_lens(
    data: Any,
    zoom: int,
    width: int,
    *,
    icons: IconSet | None = None,
    fidelity: Fidelity | None = None,
) -> Block:
    """Render numeric data as text-based charts.

    Supports:
    - List of numbers: sequence chart (sparkline or bars)
    - Dict {label: number}: labeled bar chart
    - Single number: inline bar (requires max_value hint or uses 100)

    Zoom levels:
    - 0: Summary stats (count, range)
    - 1: Inline sparkline
    - 2: Stats + sparkline
    - 3+: Labeled horizontal bars

    Args:
        data: Numeric data in supported format.
        zoom: Zoom level (0-3).
        width: Available width in characters.
        icons: Optional IconSet override (uses ambient if None).

    Returns:
        Block with rendered chart.
    """
    if width <= 0:
        return Block.empty(0, 1)

    values, labels = _chart_extract(data)
    spark_chars, bar_filled, bar_empty = _get_chart_icons(icons)

    if not values:
        return Block.text("(no data)", Style(), width=width)

    if zoom <= 0:
        # Stats only
        return _chart_stats(values, width)

    if zoom == 1:
        # Sparkline only
        return _chart_sparkline_themed(values, width, spark_chars)

    if zoom == 2:
        # Stats + sparkline
        stats = _chart_stats(values, width)
        sparkline = _chart_sparkline_themed(values, width, spark_chars)
        return join_vertical(stats, sparkline)

    # zoom >= 3: labeled bars
    return _chart_bars_themed(values, labels, width, bar_filled, bar_empty)


def _chart_extract(data: Any) -> tuple[list[float], list[str] | None]:
    """Extract (values, labels) from various data formats."""
    # Dict with numeric values
    if isinstance(data, dict):
        labels = []
        values = []
        for k, v in data.items():
            if isinstance(v, (int, float)):
                labels.append(str(k))
                values.append(float(v))
        return values, labels if labels else None

    # List/tuple of numbers
    if isinstance(data, (list, tuple)):
        values = []
        for item in data:
            if isinstance(item, (int, float)):
                values.append(float(item))
        return values, None

    # Single number
    if isinstance(data, (int, float)):
        return [float(data)], None

    return [], None


def _chart_stats(values: list[float], width: int) -> Block:
    """Render summary statistics."""
    n = len(values)
    lo = min(values)
    hi = max(values)

    if lo == hi:
        text = f"[{n} values, all {lo:.4g}]"
    else:
        text = f"[{n} values, {lo:.4g}\u2013{hi:.4g}]"

    return Block.text(_truncate_ellipsis(text, width), Style(), width=width)


def _chart_sparkline_themed(values: list[float], width: int, spark_chars: Sequence[str]) -> Block:
    """Render an inline sparkline with themed characters."""
    if not values:
        return Block.empty(width, 1)

    text = sparkline_text(
        values,
        width,
        chars=spark_chars,
        sampling="uniform",
        pad_left=False,
        pad_char=" ",
    )
    return Block.text(text, Style(), width=width)


def _chart_bars_themed(
    values: list[float],
    labels: list[str] | None,
    width: int,
    bar_filled: str,
    bar_empty: str,
) -> Block:
    """Render horizontal bars with themed characters."""
    if not values:
        return Block.empty(width, 1)

    # Generate labels if not provided
    if labels is None:
        labels = [str(i) for i in range(len(values))]

    # Calculate column widths
    max_label = max(len(lbl) for lbl in labels)
    label_col = min(max_label + 1, width // 3)  # cap at 1/3 of width

    # Value suffix: " XXX%" or " XXX.X" — reserve 6 chars
    value_col = 6
    bar_width = width - label_col - value_col

    if bar_width < 2:
        # Not enough room for bars, just show values
        rows = []
        for lbl, val in zip(labels, values):
            text = f"{lbl}: {val:.4g}"
            rows.append(Block.text(_truncate_ellipsis(text, width), Style(), width=width))
        return join_vertical(*rows)

    lo = min(values)
    hi = max(values)
    span = hi - lo if hi > lo else 1.0

    # Determine if values look like percentages (0-100 range)
    is_percent = lo >= 0 and hi <= 100

    rows = []
    for lbl, val in zip(labels, values):
        # Label column (right-padded)
        lbl_text = _truncate_ellipsis(lbl, label_col - 1).ljust(label_col)

        # Bar
        if span > 0:
            ratio = (val - lo) / span
        else:
            ratio = 1.0
        filled_count = int(ratio * bar_width)
        filled_count = max(0, min(bar_width, filled_count))
        bar = bar_filled * filled_count + bar_empty * (bar_width - filled_count)

        # Value suffix
        if is_percent:
            val_text = f"{val:3.0f}%".rjust(value_col)
        else:
            val_text = f"{val:.4g}".rjust(value_col)

        row_text = lbl_text + bar + val_text
        rows.append(Block.text(row_text[:width], Style(), width=width))

    return join_vertical(*rows)


def _truncate_ellipsis(text: str, width: int) -> str:
    """Truncate text with ellipsis if it exceeds width."""
    return truncate_ellipsis(text, width) if width > 1 else truncate(text, width)
