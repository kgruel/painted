"""Narrow regressions for Interference's declared carriers and registration."""

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
    _ROOT / "demos" / "showcase" / "interference.py", module_name="_interference_demo"
)


def test_checkout_invocations_reach_discovery_and_catalog():
    entry = next(d for d in discover_demos() if d.group == "showcase" and d.name == "interference")
    expected = tuple(
        f"uv run demos/showcase/interference.py {args}"
        for args in ("--live", "--phase opposed", "-v", "--stats", "--note", "--json")
    )
    assert entry.invocations == expected
    catalog = json.loads((_ROOT / "web/src/generated/catalog.json").read_text())
    published = next(d for d in catalog["demos"] if d["id"] == "showcase/interference")
    assert published["invocations"] == list(expected)


@pytest.mark.parametrize("value", [0.25, 0.5, 1.0])
def test_color_encodes_positive_cyan_and_negative_amber(value):
    def rgb(color):
        return tuple(int(color[i : i + 2], 16) for i in (1, 3, 5))

    positive = rgb(D._color(value))
    negative = rgb(D._color(-value))
    assert positive[2] > positive[0]
    assert negative[0] > negative[2]
    assert D._color(0.0) == "#060d19"


def test_half_blocks_carry_top_foreground_and_bottom_background_samples():
    samples = ((0.75, -0.5, 0.0), (-0.25, 1.0, 0.5), (0.2, 0.4, -0.8), (0.0, -0.6, 0.1))
    with use_capabilities(Capabilities(color=True, glyph=True)):
        picture = D._picture(samples)
    assert (picture.width, picture.height) == (3, 2)
    for y in range(picture.height):
        for x, cell in enumerate(picture.row(y)):
            assert cell.char == "▀"
            assert cell.style == Style(
                fg=D._color(samples[2 * y][x]), bg=D._color(samples[2 * y + 1][x])
            )


def test_color_without_glyph_uses_colored_strongest_signed_ascii_sample():
    # Exercise both top and bottom winners, opposite signs, quiet, and a tie.
    samples = ((0.75, 0.25, 0.0, -0.5), (-0.25, -0.75, 0.0, 0.5))
    with use_capabilities(Capabilities(color=True, glyph=False)):
        picture = D._picture(samples)
    assert (picture.width, picture.height) == (4, 1)
    for cell, value, mark in zip(picture.row(0), (0.75, -0.75, 0.0, -0.5), ("@", "#", " ", "x")):
        assert cell.char == mark
        assert cell.style == Style(fg=D._color(value))


@pytest.mark.parametrize("depth", range(4))
@pytest.mark.parametrize("stats", [False, True])
def test_stats_text_matches_the_default_score_sampling(depth, stats):
    fidelity = Fidelity(depth=depth, visible=frozenset({"stats"}) if stats else frozenset())
    text = block_to_text(D._render(D._fetch(), fidelity, None))
    expected = "samples 2628 / RMS 0.425 / near zero 9.1%"
    assert (expected in text) == (stats or depth == 3)
    if not stats and depth < 3:
        assert "RMS" not in text


def test_time_changes_nonzero_displacement():
    # The two time laws alone would also pass an identically zero field.
    assert abs(D._value(1.0, 2.0, D._fetch(0))) > 0.1
    assert D._value(1.0, 2.0, D._fetch(0)) != pytest.approx(
        D._value(1.0, 2.0, D._fetch(1)), abs=1e-12
    )
