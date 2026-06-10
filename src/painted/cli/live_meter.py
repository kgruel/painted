"""LiveMeter — the framework's delivery-cost gauge for live frames.

Both live tiers (in-place scrollback and alt-screen surface) measure
their own render+write cost per frame and dress each delivered frame
with a ``cost_meter`` row. The demo/app never measures: only the
delivery mechanism knows what delivery costs, and since the surface
tier decoupled stream consumption from repainting, the old trick of
timing the stream's yield boundary reads ~0 there.

The budget is not declared, it is *measured*: the median inter-frame
period. "Did delivery fit inside the frame it was delivering?" is the
only question the gauge asks, and the answer self-calibrates to any
cadence — a 30fps animation gets a ~33ms budget, a deploy script
yielding every 2s gets ~2000ms.

The gauge row is reserved (blank) from the very first frame so the
dressed height never shifts when samples start filling it in — the
pinned-window contract, kept by the framework this time.
"""

from __future__ import annotations

from statistics import median
from time import perf_counter
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.block import Block

# Trailing samples kept — enough to ride out one bad frame, short enough
# to track a changing scene.
_CAP = 60


class LiveMeter:
    """Rolling render+write gauge. One instance per live run.

    ``start()`` when delivery of a frame begins (render about to run),
    ``stop()`` when the bytes have been handed to the terminal,
    ``dress(block)`` to append the gauge row to an outgoing frame.
    ``stop()`` without a matching ``start()`` is a no-op, so callers can
    skip measuring frames that carry no state.
    """

    def __init__(self) -> None:
        self._costs: list[float] = []  # ms per delivery, trailing _CAP
        self._periods: list[float] = []  # ms between delivery starts
        self._last_start: float | None = None
        self._t0: float | None = None

    def start(self) -> None:
        """Mark the start of one frame's delivery."""
        now = perf_counter()
        if self._last_start is not None:
            self._periods.append((now - self._last_start) * 1000)
            del self._periods[:-_CAP]
        self._last_start = now
        self._t0 = now

    def stop(self) -> None:
        """Mark the frame delivered; records the cost sample."""
        if self._t0 is None:
            return
        self._costs.append((perf_counter() - self._t0) * 1000)
        del self._costs[:-_CAP]
        self._t0 = None

    def dress(self, block: Block) -> Block:
        """The frame plus its gauge row, exactly the frame's width.

        Until both a cost and a period exist the row is blank — present
        so the height is stable from frame one, silent because there is
        nothing honest to show yet.
        """
        from ..core.block import Block as _Block
        from ..core.compose import join_vertical, truncate
        from ..views import cost_meter

        meter = None
        if self._costs and self._periods:
            meter = cost_meter(tuple(self._costs), block.width, budget_ms=median(self._periods))
        if meter is None:
            return join_vertical(block, _Block.empty(block.width, 1))
        return join_vertical(block, truncate(meter, block.width))
