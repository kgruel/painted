"""Hypothesis configuration for painted's property tier.

A single registered profile keeps runs deterministic-ish and CI-stable:
- `deadline=None` because the same suite runs under coverage instrumentation
  (`./dev cov`), which slows execution enough to trip per-example deadlines on
  block construction — a timing flake, not a real failure.
- `max_examples` is modest so the property tier stays a fast gate step, not a
  fuzzing campaign. Bump via HYPOTHESIS_PROFILE=thorough for a deeper sweep.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, settings

from painted import reset_borders, reset_icons, reset_palette


@pytest.fixture(autouse=True)
def _default_ambient_state():
    """Pin palette/icons/borders to their defaults around every property test.

    The width laws here are stated for the DEFAULT glyph set; a wide custom icon
    or border could legitimately change a lens's output width. Without this, a
    golden/unit test that sets ambient state globally and forgets to reset it
    would make these properties order-dependent in a single-process run.
    """
    reset_palette()
    reset_icons()
    reset_borders()
    yield
    reset_palette()
    reset_icons()
    reset_borders()


settings.register_profile(
    "painted",
    max_examples=150,
    deadline=None,
    # derandomize: the gate must be reproducible — same inputs every run, so a
    # property cannot pass in CI today and fail tomorrow on a new random draw.
    # The `thorough` profile stays exploratory for periodic deeper sweeps.
    derandomize=True,
    # Composite block strategies can be a touch slow to draw; that's expected,
    # not a sign of a broken strategy.
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("thorough", max_examples=1000, deadline=None)
settings.load_profile("painted")
