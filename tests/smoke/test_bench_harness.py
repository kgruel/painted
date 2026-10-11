"""The scenario baseline harness stays runnable (tools/bench.py, roadmap M8).

Timings are informational and never gated, but a scenario that raises would
silently drop out of the next baseline. Every scenario sets up and runs once.
"""

from __future__ import annotations

import pytest

from tools.bench import SCENARIOS


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s.name)
def test_scenario_runs(scenario) -> None:
    counters = scenario.setup()()
    assert counters, f"{scenario.name} reported no counters"
