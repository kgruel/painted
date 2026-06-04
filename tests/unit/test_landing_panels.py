"""Gate the landing front-door panels — the PANELS catalog is otherwise ungated.

Companion to `test_reference_panels.py`. The landing hero + door cards render only
via `outputgen --emit-panels` (the committed site fragments), so a broken specimen
would rot silently: the gate stays green while the site ships a stale or empty
front door. The shared `test_panel_renders_nonempty_html` (in the reference module,
parametrized over *all* PANELS) already renders these; here we lock the landing
specimens in lockstep with their PANELS entries and assert each is non-degenerate.
"""

from __future__ import annotations

import pytest

import tools.landing_specimens as _landing
from painted import Block
from tools.landing_specimens import LANDING
from tools.outputgen import PANELS

_LANDING_PANELS = {
    name: spec for name, spec in PANELS.items() if spec.demo_path.endswith("landing_specimens.py")
}


def test_landing_panels_match_registry() -> None:
    """Landing PANELS and the specimen registry stay 1:1.

    PANELS *generates* its landing entries from LANDING (outputgen `_module_panel`),
    so this set-equality guards that the generation wired up at all, that the
    reference/monitor panels stay classified separately (their demo_path isn't
    landing_specimens.py), and that every data_attr resolves to a real constant.
    """
    assert set(_LANDING_PANELS) == set(LANDING), (
        "landing PANELS names must match tools.landing_specimens.LANDING exactly"
    )
    for spec in _LANDING_PANELS.values():
        assert hasattr(_landing, spec.data_attr), (
            f"PANELS data_attr {spec.data_attr!r} has no matching constant in landing_specimens"
        )


@pytest.mark.parametrize("name", sorted(LANDING))
def test_landing_specimen_is_nondegenerate(name: str) -> None:
    """A specimen that collapses to nothing is a broken panel, not a real one."""
    block = LANDING[name]
    assert isinstance(block, Block)
    assert block.width > 0 and block.height > 0, f"specimen {name!r} is degenerate"
