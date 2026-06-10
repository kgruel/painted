"""Contract tests for the cost_meter component.

The meter graduated out of the animated pattern demos (life, donut, plasma)
once a third caller wanted it; these pin the contract that made it portable —
dress observed data only, judge the latest cost against the budget, and keep
the row width stable so bordered windows never breathe.
"""

from __future__ import annotations

from painted import Style
from painted.palette import DEFAULT_PALETTE
from painted.views import cost_meter
from tests.helpers import block_to_text


def test_no_samples_renders_no_meter() -> None:
    # The live dress follows the data, not a flag: empty history -> None.
    assert cost_meter((), 60, budget_ms=33.0) is None


def test_latest_cost_and_budget_are_legible() -> None:
    block = cost_meter((5.0, 6.0, 7.5), 60, budget_ms=1000 / 15)
    text = block_to_text(block)
    assert "cost" in text and "7.5ms" in text and "67ms budget" in text


def test_role_tracks_headroom() -> None:
    p = DEFAULT_PALETTE

    def role_of(cost: float) -> Style:
        block = cost_meter((cost,), 60, budget_ms=100.0, palette=p)
        # The cost figure carries the role; find its cell style.
        text = block_to_text(block)
        col = text.index("ms")
        return block.row(0)[col].style

    assert role_of(10.0).fg == p.success.fg  # < 50% of budget
    assert role_of(60.0).fg == p.warning.fg  # 50-90%
    assert role_of(99.0).fg == p.error.fg  # >= 90%
    assert role_of(250.0).fg == p.error.fg  # over budget


def test_row_width_is_stable_across_frames() -> None:
    # Fixed-format cost + padded sparkline: one sample and a full history
    # occupy identical width, so a window built around the meter never moves.
    one = cost_meter((4.2,), 60, budget_ms=33.0)
    many = cost_meter(tuple(float(i % 13) + 1 for i in range(60)), 60, budget_ms=33.0)
    assert one.width == many.width
    assert one.height == many.height == 1


def test_custom_label_replaces_the_lead() -> None:
    text = block_to_text(cost_meter((3.0,), 60, budget_ms=33.0, label="write"))
    assert text.startswith("write ")
    assert "cost" not in text
