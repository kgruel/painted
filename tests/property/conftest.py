"""Hypothesis configuration for painted's property tier.

A single registered profile keeps runs deterministic-ish and CI-stable:
- `deadline=None` because the same suite runs under coverage instrumentation
  (`./dev cov`), which slows execution enough to trip per-example deadlines on
  block construction — a timing flake, not a real failure.
- `max_examples` is modest so the property tier stays a fast gate step, not a
  fuzzing campaign. Bump via HYPOTHESIS_PROFILE=thorough for a deeper sweep.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

# Ambient state (palette/icons/borders) is reset around every test by the
# suite-wide `_reset_ambient_state` fixture in the root `tests/conftest.py`.
# The width laws here assume the DEFAULT glyph set, so that reset is what keeps
# them order-independent — it just lives one level up now. Note that reset is
# per-test, not per-Hypothesis-example: a @given body must not leave ambient
# state mutated across examples — wrap any such mutation in a `with use_*(...)`.


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
settings.register_profile(
    "thorough",
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
# Honor HYPOTHESIS_PROFILE so the documented `thorough` sweep is actually reachable
# (it was registered but never loaded — load_profile was hardcoded to "painted").
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "painted"))
