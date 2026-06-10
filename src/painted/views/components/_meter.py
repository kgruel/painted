"""Cost meter: observed per-frame cost gauged against a time budget.

A single-row gauge for live-rendering loops: a sparkline of recent frame
costs, the latest cost, and the budget it is judged against. The role
encodes headroom — success under half the budget, warning under 90%,
error at or beyond it.

Born duplicated in the animated pattern demos (life, donut) and graduated
to a component when a third pattern wanted the same row. The contract
that made it portable: the meter dresses *observed data only* — no
samples (static output) means no meter, so callers render honest static
frames without threading a flag.

Usage:
    from painted.views import cost_meter

    meter = cost_meter(frame_ms, width=60, budget_ms=1000 / 30)
    if meter is not None:
        rows.append(meter)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ...core.block import Block
from ...core.cell import Style
from ...core.compose import join_horizontal
from ._sparkline import sparkline

if TYPE_CHECKING:
    from ...palette import Palette


def cost_meter(
    samples_ms: Sequence[float],
    width: int,
    *,
    budget_ms: float,
    label: str = "cost",
    palette: Palette | None = None,
) -> Block | None:
    """Render observed costs against a budget; None when nothing was observed.

    Args:
        samples_ms: Observed costs in milliseconds, oldest first.
        width: Exact row width; the sparkline absorbs what the labels don't use
            (floored at 8 columns, so very narrow widths overflow rather than
            collapse the gauge).
        budget_ms: The per-sample budget the latest cost is judged against.
        label: Leading label text.
        palette: Optional Palette override (uses ambient if None).

    Returns:
        A single-row Block, or None when ``samples_ms`` is empty — the live
        dress follows the data, not a flag.

    The row's width is stable across frames for a fixed ``width``: the cost
    field is fixed-format and the sparkline pads until its history fills, so
    a bordered window built around the meter never breathes.
    """
    if not samples_ms:
        return None

    from ...palette import current_palette

    p = palette or current_palette()
    cost = samples_ms[-1]
    role = p.success if cost < budget_ms * 0.5 else p.warning if cost < budget_ms * 0.9 else p.error
    lead = f"{label} "
    tail = f" {cost:5.1f}ms "
    suffix = f"/ {budget_ms:.0f}ms budget"
    spark_w = max(8, width - len(lead) - len(tail) - len(suffix))
    return join_horizontal(
        Block.text(lead, Style(dim=True)),
        sparkline(list(samples_ms), spark_w, style=role),
        Block.text(tail, role),
        Block.text(suffix, Style(dim=True)),
    )
