"""Gate the site's real-output panels — the PANELS catalog is otherwise ungated.

`scripts/check.sh` runs `outputgen --check`, which walks only the doc-sentinel
MANIFEST path (`docs/guides`). The PANELS set — the committed site fragments,
including every `/reference` specimen — renders only via `--emit-panels`, so a
broken specimen would rot *silently*: the gate is green, the site build ships a
stale or empty card. This tier renders the whole catalog through the real
outputgen path and asserts it is non-empty painted HTML, and that the reference
specimens stay in lockstep with their PANELS entries.
"""

from __future__ import annotations

import pytest

import tools.reference_specimens as _specimens
from painted import Block
from tools.outputgen import PANELS, _generate_output, _repo_root
from tools.reference_specimens import CATALOG

_REFERENCE_PANELS = {
    name: spec for name, spec in PANELS.items() if spec.demo_path.endswith("reference_specimens.py")
}


@pytest.mark.parametrize("name", sorted(PANELS))
def test_panel_renders_nonempty_html(name: str) -> None:
    """Every committed site panel renders through outputgen without raising."""
    html = _generate_output(repo_root=_repo_root(), spec=PANELS[name])
    assert html.strip(), f"panel {name!r} produced empty output"
    assert "painted-output" in html, f"panel {name!r} is not painted HTML"


def test_reference_panels_match_catalog() -> None:
    """Reference PANELS and the specimen registry stay 1:1.

    PANELS now *generates* its reference entries from CATALOG (outputgen
    `_reference_spec`), so this set-equality can't drift — it's a guard that the
    generation wired up at all, that the monitor panels stay classified separately
    (their demo_path isn't reference_specimens.py), and that every data_attr below
    resolves. The render check above is the load-bearing one.
    """
    assert set(_REFERENCE_PANELS) == set(CATALOG), (
        "reference PANELS names must match tools.reference_specimens.CATALOG exactly"
    )
    for spec in _REFERENCE_PANELS.values():
        assert hasattr(_specimens, spec.data_attr), (
            f"PANELS data_attr {spec.data_attr!r} has no matching constant in reference_specimens"
        )


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_specimen_is_nondegenerate(name: str) -> None:
    """A specimen that collapses to nothing is a broken card, not a real one."""
    block = CATALOG[name]
    assert isinstance(block, Block)
    assert block.width > 0 and block.height > 0, f"specimen {name!r} is degenerate"
