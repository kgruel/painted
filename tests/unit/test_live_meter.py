"""Laws for LiveMeter — the framework's delivery-cost gauge.

When an app opts in (run_cli(live_meter=True)), the live tiers measure
their own render+write cost and dress each frame with a cost_meter row.
The laws pin the gauge's contract:

  - the row is reserved (blank) from the first frame, so dressed height
    never shifts when samples arrive (pinned-window contract);
  - the budget is the *measured* median inter-frame period, not a
    declared fps;
  - dressed width is exactly the frame's width;
  - stop() without start() is a no-op (unmeasured frames are legal);
  - samples are capped (a trailing gauge, not a history).

Timing is driven by a fake clock, so every law is deterministic.
"""

from __future__ import annotations

import pytest

from painted import Block, Style
from painted.cli import live_meter
from painted.cli.live_meter import LiveMeter

from tests.helpers import block_to_text


class _Clock:
    """A perf_counter stand-in the test advances by hand (seconds)."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(live_meter, "perf_counter", c)
    return c


def _frame(meter: LiveMeter, clock: _Clock, *, start: float, cost: float) -> None:
    """Deliver one frame: start at `start`, finish `cost` later (seconds)."""
    clock.t = start
    meter.start()
    clock.t = start + cost
    meter.stop()


_BLOCK = Block.text("x" * 40, Style())


def test_dress_reserves_a_blank_row_before_samples() -> None:
    dressed = LiveMeter().dress(_BLOCK)
    assert dressed.width == _BLOCK.width
    assert dressed.height == _BLOCK.height + 1
    assert block_to_text(dressed).splitlines()[-1].strip() == ""


def test_dress_shows_the_gauge_once_observed(clock: _Clock) -> None:
    meter = LiveMeter()
    _frame(meter, clock, start=0.000, cost=0.007)
    _frame(meter, clock, start=0.033, cost=0.0075)
    text = block_to_text(meter.dress(_BLOCK))
    assert "cost" in text and "7.5ms" in text and "33ms budget" in text


def test_height_is_stable_across_the_gauge_filling_in(clock: _Clock) -> None:
    meter = LiveMeter()
    before = meter.dress(_BLOCK)
    _frame(meter, clock, start=0.0, cost=0.005)
    _frame(meter, clock, start=0.1, cost=0.005)
    after = meter.dress(_BLOCK)
    assert before.height == after.height
    assert before.width == after.width


def test_budget_is_the_measured_median_period(clock: _Clock) -> None:
    meter = LiveMeter()
    # Periods 20ms, 100ms, 20ms — the median (20) is the budget, so one
    # stall (a pause, a slow fetch) cannot recalibrate the gauge.
    for start in (0.000, 0.020, 0.120, 0.140):
        _frame(meter, clock, start=start, cost=0.004)
    assert "20ms budget" in block_to_text(meter.dress(_BLOCK))


def test_stop_without_start_is_a_noop(clock: _Clock) -> None:
    meter = LiveMeter()
    meter.stop()  # e.g. a flush whose render carried no state
    dressed = meter.dress(_BLOCK)
    assert block_to_text(dressed).splitlines()[-1].strip() == ""


def test_dressed_width_is_exact_even_when_the_gauge_is_wider(clock: _Clock) -> None:
    # A frame narrower than the gauge's natural width: dress truncates,
    # never widens — the frame's window must not jitter.
    narrow = Block.text("0123456789", Style())
    meter = LiveMeter()
    _frame(meter, clock, start=0.00, cost=0.005)
    _frame(meter, clock, start=0.05, cost=0.005)
    assert meter.dress(narrow).width == narrow.width


def test_samples_are_capped_to_a_trailing_window(clock: _Clock) -> None:
    meter = LiveMeter()
    for i in range(100):
        _frame(meter, clock, start=i * 0.01, cost=0.001)
    assert len(meter._costs) == live_meter._CAP
    assert len(meter._periods) == live_meter._CAP


def test_inplace_live_frames_carry_the_gauge(monkeypatch) -> None:
    """The ephemeral tier dresses too — any fetch_stream app gets the gauge."""
    import io

    import painted.inplace as inplace_mod
    from painted.cli.runner import CliRunner
    from painted.cli.types import CliContext, Fidelity, OutputMode, Zoom

    # InPlaceRenderer's default stream binds the real stdout at import time;
    # route this run into a buffer instead of fighting pytest's capture.
    out = io.StringIO()
    real = inplace_mod.InPlaceRenderer
    monkeypatch.setattr(inplace_mod, "InPlaceRenderer", lambda: real(stream=out))

    async def stream():
        for s in ("a", "b", "c"):
            yield s.ljust(64, ".")

    ctx = CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=OutputMode.LIVE,
        use_ansi=True,
        is_tty=True,
        width=80,
        height=24,
    )
    runner = CliRunner(
        renderer=lambda s, fidelity, width: Block.text(str(s), Style()),
        fetch=lambda: None,
        fetch_stream=stream,
        live_meter=True,
    )
    assert runner._run_live(ctx) == 0
    assert "budget" in out.getvalue()


def test_inplace_live_is_undressed_by_default(monkeypatch) -> None:
    """No opt-in, no gauge — the knob is the author's, never implied."""
    import io

    import painted.inplace as inplace_mod
    from painted.cli.runner import CliRunner
    from painted.cli.types import CliContext, Fidelity, OutputMode, Zoom

    out = io.StringIO()
    real = inplace_mod.InPlaceRenderer
    monkeypatch.setattr(inplace_mod, "InPlaceRenderer", lambda: real(stream=out))

    async def stream():
        for s in ("a", "b", "c"):
            yield s.ljust(64, ".")

    ctx = CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=OutputMode.LIVE,
        use_ansi=True,
        is_tty=True,
        width=80,
        height=24,
    )
    runner = CliRunner(
        renderer=lambda s, fidelity, width: Block.text(str(s), Style()),
        fetch=lambda: None,
        fetch_stream=stream,
    )
    assert runner._run_live(ctx) == 0
    assert "budget" not in out.getvalue() and "cost" not in out.getvalue()
