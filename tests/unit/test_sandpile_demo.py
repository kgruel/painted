"""Laws the Sandpile showcase claims: order-independence, conservation, carriers."""

import json
from pathlib import Path

import pytest

from painted import Fidelity, Style
from painted._demo_discovery import discover_demos
from painted.capabilities import Capabilities, use_capabilities
from tests.helpers import block_to_text
from tools.capture import import_module_by_path

_ROOT = Path(__file__).resolve().parents[2]
D = import_module_by_path(
    _ROOT / "demos" / "showcase" / "sandpile.py", module_name="_sandpile_demo"
)


def test_checkout_invocations_reach_discovery_and_catalog():
    entry = next(d for d in discover_demos() if d.group == "showcase" and d.name == "sandpile")
    expected = tuple(
        f"uv run demos/showcase/sandpile.py {args}"
        for args in ("--live", "--frame 2000", "-v", "--stats", "--note", "--json")
    )
    assert entry.invocations == expected
    catalog = json.loads((_ROOT / "web/src/generated/catalog.json").read_text())
    published = next(d for d in catalog["demos"] if d["id"] == "showcase/sandpile")
    assert published["invocations"] == list(expected)


def test_still_equals_animation_cell_for_cell():
    # The abelian law, and the demo's whole claim: a grain at a time from
    # empty lands on the bulk settle — heights, spill, and odometer alike.
    pile = D.settle(0)
    for _ in range(700):  # past the frame where the three piles merge
        pile = D.step(pile)
    bulk = D.settle(700)
    assert (pile.heights, pile.spilled, pile.toppled) == (bulk.heights, bulk.spilled, bulk.toppled)
    # ...and _fetch reconstructs the history the animation carried, too.
    assert D._fetch(700) == pile


@pytest.mark.parametrize("frame", [0, 1, 300, 2000])
def test_ledger_balances_and_pile_is_at_rest(frame):
    pile = D.settle(frame)
    assert pile.dropped == pile.resting + pile.spilled
    assert all(0 <= h < 4 for row in pile.heights for h in row)
    # frame 2000 must actually exercise the edge, or the spill term is untested
    assert (pile.spilled > 0) == (frame == 2000)


def test_mirror_symmetric_sites_make_a_mirror_symmetric_pile():
    assert all(row == row[::-1] for row in D.settle(900).heights)


def test_half_blocks_carry_top_foreground_and_bottom_background_samples():
    heights = ((0, 1, 2, 3), (3, 2, 1, 0), (1, 1, 0, 2), (2, 0, 3, 3))
    with use_capabilities(Capabilities(color=True, glyph=True)):
        picture = D._picture(heights)
    assert (picture.width, picture.height) == (4, 2)
    for y in range(2):
        for x, cell in enumerate(picture.row(y)):
            assert cell.char == "▀"
            assert cell.style == Style(
                fg=D._INK[heights[2 * y][x]], bg=D._INK[heights[2 * y + 1][x]]
            )


@pytest.mark.parametrize("color", [False, True])
def test_without_half_blocks_the_taller_sample_is_marked(color):
    heights = ((0, 1, 3, 0), (0, 2, 1, 3))
    with use_capabilities(Capabilities(color=color, glyph=False)):
        picture = D._picture(heights)
    assert "".join(cell.char for cell in picture.row(0)) == " o##"
    for cell, h in zip(picture.row(0), (0, 2, 3, 3)):
        assert cell.style == (Style(fg=D._INK[h]) if color and h else Style())


def test_narrow_delivery_windows_the_centre_and_says_so():
    pile = D._fetch(300)
    wide = block_to_text(D._render(pile, Fidelity(), None))
    block = D._render(pile, Fidelity(), 41)
    narrow = block_to_text(block)
    assert "columns shown" not in wide
    assert "centre 39 of 73 columns shown" in narrow
    assert block.width == 41


@pytest.mark.parametrize("depth", range(4))
@pytest.mark.parametrize("stats", [False, True])
def test_ledger_is_shown_at_vv_or_when_named(depth, stats):
    fidelity = Fidelity(depth=depth, visible=frozenset({"stats"}) if stats else frozenset())
    text = block_to_text(D._render(D._fetch(300), fidelity, None))
    assert ("dropped 900 = resting 900 + spilled 0" in text) == (stats or depth == 3)
