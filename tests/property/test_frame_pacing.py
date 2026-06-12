"""Frame-pacing laws — the sleep after a frame compensates for frame work.

`Surface.run` paces with ``frame_sleep(elapsed, fps_cap, active=...)``. Before
compensation the loop slept the full ``1/fps_cap`` *after* a blocking render,
so every frame cost render_time + period (a 30fps cap delivered ~23fps in the
raymarch field test). These laws pin the pure pacing function:

  * the frame budget law: for an idle frame, sleep + elapsed >= period, with
    equality whenever the render fits inside the period (no over-sleep), and
  * the floor law: the result never drops below MIN_YIELD (the loop always
    yields), even when a render overruns its entire period, and
  * the active law: input flowing or a queued re-render yields minimally,
    regardless of elapsed time — draining input is never throttled.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.tui.surface import MIN_YIELD, frame_sleep

fps_caps = st.integers(min_value=1, max_value=240)
elapsed_times = st.floats(min_value=0.0, max_value=5.0, allow_nan=False)


class TestFrameSleepLaws:
    @given(elapsed=elapsed_times, fps_cap=fps_caps)
    def test_idle_frame_sleeps_exactly_the_remainder(self, elapsed, fps_cap):
        remainder = 1.0 / fps_cap - elapsed
        sleep = frame_sleep(elapsed, fps_cap, active=False)
        if remainder >= MIN_YIELD:
            assert sleep == remainder
        else:
            assert sleep == MIN_YIELD

    @given(elapsed=elapsed_times, fps_cap=fps_caps)
    def test_sleep_never_below_min_yield(self, elapsed, fps_cap):
        assert frame_sleep(elapsed, fps_cap, active=False) >= MIN_YIELD

    @given(elapsed=elapsed_times, fps_cap=fps_caps)
    def test_active_frame_yields_minimally(self, elapsed, fps_cap):
        assert frame_sleep(elapsed, fps_cap, active=True) == MIN_YIELD
