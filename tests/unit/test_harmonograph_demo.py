"""Law tests for the harmonograph showcase.

The lesson is a frozen mechanical score rasterized into terminal-native
subpixels. These tests pin the oscillator envelope, connected raster, honest
Braille/ASCII/color carriers, allocation, and fidelity facets without freezing
one decorative pose.
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
import sys
from pathlib import Path

from painted import Fidelity, Zoom
from painted.capabilities import Capabilities, use_capabilities
from painted.cli import implied_visible
from tests.helpers import block_to_text

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "showcase" / "harmonograph.py"


def _load():
    spec = importlib.util.spec_from_file_location("_harmonograph_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_harmonograph_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


hm = _load()


# --- Mechanical score ---


def test_axis_stays_inside_its_damped_envelope() -> None:
    for voices in (hm.SCORE.x, hm.SCORE.y):
        for frame in (0, 180, 700):
            for t in (0.0, 7.5, 40.0, hm._T_END):
                envelope = sum(p.amplitude * math.exp(-p.damping * t) for p in voices)
                assert abs(hm._axis(voices, t, frame)) <= envelope + 1e-12


def test_score_has_two_near_tuned_pendulums_per_axis() -> None:
    assert len(hm.SCORE.x) == len(hm.SCORE.y) == 2
    for voices in (hm.SCORE.x, hm.SCORE.y):
        assert 0.0 < abs(voices[0].frequency - voices[1].frequency) < 0.05
        assert all(p.damping > 0 for p in voices)


def test_phase_drift_actually_moves_the_curve() -> None:
    assert hm._curve(hm._fetch(0)) != hm._curve(hm._fetch(30))


def test_same_performance_produces_the_same_curve() -> None:
    performance = hm._fetch(123)
    assert hm._curve(performance) == hm._curve(performance)


# --- Raster laws ---


def test_line_raster_is_connected_and_keeps_endpoints() -> None:
    pixels = hm._line_pixels(2, 9, 15, 3)
    assert pixels[0] == (2, 9)
    assert pixels[-1] == (15, 3)
    assert all(max(abs(b[0] - a[0]), abs(b[1] - a[1])) == 1 for a, b in zip(pixels, pixels[1:]))


def test_raster_dimensions_and_masks_match_braille_cells() -> None:
    raster = hm._raster(hm._fetch(), columns=37, rows=13)
    assert len(raster.masks) == len(raster.shades) == 13
    assert all(len(row) == 37 for row in raster.masks)
    assert all(0 <= mask <= 0xFF for row in raster.masks for mask in row)
    assert all(0 <= shade < hm._INK_SHADES for row in raster.shades for shade in row)


def test_plotted_count_is_the_number_of_unique_lit_dots() -> None:
    raster = hm._raster(hm._fetch(), columns=48)
    assert raster.plotted == sum(mask.bit_count() for row in raster.masks for mask in row)
    assert raster.plotted > 500
    assert raster.collisions > 0, "the finished drawing should contain crossings"


# --- Destination carriers ---


def test_braille_carrier_uses_only_spaces_and_braille() -> None:
    with use_capabilities(Capabilities(color=False, glyph=True, link=False)):
        text = block_to_text(hm.render_plate(hm._fetch(), 48))
    assert all(ch in " \n" or 0x2800 < ord(ch) <= 0x28FF for ch in text)
    assert any(0x2800 < ord(ch) <= 0x28FF for ch in text)


def test_ascii_carrier_is_strict_ascii_and_non_degenerate() -> None:
    with use_capabilities(Capabilities(color=False, glyph=False, link=False)):
        text = block_to_text(hm.render_plate(hm._fetch(), 48))
    assert text.isascii()
    assert set(text) <= set(hm._ASCII_DENSITY) | {"\n"}
    assert any(ch not in " \n" for ch in text)


def test_truecolor_ink_comes_only_from_the_gradient() -> None:
    with use_capabilities(Capabilities(color=True, glyph=True, link=False)):
        block = hm.render_plate(hm._fetch(), 48)
    gradient = {style.fg for style in hm._INK_STYLES}
    seen = {
        block.row(y)[x].style.fg
        for y in range(block.height)
        for x in range(block.width)
        if block.row(y)[x].char != " "
    }
    assert seen <= gradient
    assert len(seen) > hm._INK_SHADES // 2


def test_gradient_reaches_both_declared_endpoints() -> None:
    assert hm._INK_STYLES[0].fg == hm._INK_ANCHORS[0]
    assert hm._INK_STYLES[-1].fg == hm._INK_ANCHORS[-1]


# --- Renderer contract, fidelity, and stream ---


def test_render_is_pure_at_every_zoom() -> None:
    performance = hm._fetch(240)
    for zoom in Zoom:
        fidelity = Fidelity(depth=int(zoom))
        assert block_to_text(hm._render(performance, fidelity, 80)) == block_to_text(
            hm._render(performance, fidelity, 80)
        )


def test_supplied_width_is_exact_even_at_tiny_allocations() -> None:
    performance = hm._fetch()
    for width in (0, 1, 2, 3, 8, 37, 80, 111):
        assert hm._render(performance, Fidelity(depth=int(Zoom.SUMMARY)), width).width == width


def test_natural_window_uses_the_compact_plate_width() -> None:
    block = hm._render(hm._fetch(), Fidelity(depth=int(Zoom.SUMMARY)), None)
    assert block.width == hm._NATURAL_COLUMNS + 2


def test_quiet_is_a_one_line_microplate() -> None:
    with use_capabilities(Capabilities(color=False, glyph=True, link=False)):
        block = hm._render(hm._fetch(), Fidelity(depth=int(Zoom.MINIMAL)), 80)
    text = block_to_text(block)
    assert block.height == 1
    assert "harmonograph" in text and "f180" in text
    assert any(0x2800 < ord(ch) <= 0x28FF for ch in text)
    assert len(set(ch for ch in text if 0x2800 < ord(ch) <= 0x28FF)) > 3


def test_summary_is_only_the_24_line_gallery_plate() -> None:
    block = hm._render(hm._fetch(), Fidelity(depth=int(Zoom.SUMMARY)), 80)
    text = block_to_text(block)
    assert block.height == 24  # 22 rows of ink + the border
    assert "harmonograph" in text
    assert "Why this one" not in text
    assert "frame 180" not in text


def test_the_signed_makers_note_answers_only_to_its_own_name() -> None:
    """Named-only, per the ruling NOTE_TAG carries (see tests/unit/test_plaque.py).

    The gallery register put wall text at -v. Depth is anonymous detail about
    the subject, though, and the maker is not more subject — so the note is
    asked for by name at any depth and implied at none.
    """
    for depth in range(4):
        plain = block_to_text(hm._render(hm._fetch(), Fidelity(depth=depth), 80))
        assert "— Sol" not in plain, f"depth {depth} produced the note without being asked"
        named = block_to_text(
            hm._render(hm._fetch(), Fidelity(depth=depth, visible=frozenset({"note"})), 80)
        )
        assert "Why this one" in named
        assert "eight-point plotter" in named
        assert "— Sol" in named


def test_full_adds_the_mechanical_and_raster_record() -> None:
    text = block_to_text(hm._render(hm._fetch(), Fidelity(depth=int(Zoom.FULL)), 80))
    assert "Score" in text and "3.013 Hz" in text
    assert "Raster" in text and "unique dots" in text and "carrier" in text


def test_annotation_moves_beside_the_plate_at_the_wide_breakpoint() -> None:
    # The layout law is unchanged; only how the annotation is *asked for* moved,
    # so the note is named here rather than implied by -v.
    detailed = Fidelity(depth=int(Zoom.DETAILED), visible=frozenset({"note"}))
    stacked = hm._render(hm._fetch(), detailed, hm._RESPONSIVE_BREAKPOINT - 1)
    beside = hm._render(hm._fetch(), detailed, hm._RESPONSIVE_BREAKPOINT)
    assert stacked.height > 24
    assert beside.height == 24
    assert "Why this one" in block_to_text(beside).splitlines()[0]


def test_narrow_verbose_output_marks_instead_of_exploding() -> None:
    for width in (0, 1, 2, 8, 20):
        block = hm._render(hm._fetch(), Fidelity(depth=int(Zoom.FULL)), width)
        assert block.width == width
        assert block.height <= 26


def test_named_facets_change_output_at_minimal_depth() -> None:
    performance = hm._fetch()
    base = block_to_text(hm._render(performance, Fidelity(depth=0), 80))
    note = block_to_text(
        hm._render(performance, Fidelity(depth=0, visible=frozenset({"note"})), 80)
    )
    score = block_to_text(
        hm._render(performance, Fidelity(depth=0, visible=frozenset({"score"})), 80)
    )
    stats = block_to_text(
        hm._render(performance, Fidelity(depth=0, visible=frozenset({"stats"})), 80)
    )
    assert "Hz" not in base and "ink " not in base and "Why this one" not in base
    assert "— Sol" in note
    assert "Hz" in score
    assert "ink " in stats and "carrier" in stats


def test_facet_implications_match_the_zoom_ladder() -> None:
    assert implied_visible(hm._TAGS, int(Zoom.SUMMARY)) == frozenset()
    # -v implies nothing since the note went named-only: the register's
    # annotation rung is now reached by --note/--score/--stats, not by depth.
    assert implied_visible(hm._TAGS, int(Zoom.DETAILED)) == frozenset()
    assert implied_visible(hm._TAGS, int(Zoom.FULL)) == frozenset({"score", "stats"})


def test_stream_advances_from_the_requested_frame() -> None:
    async def collect() -> list:
        return [performance async for performance in hm._fetch_stream(start=5, frames=3)]

    performances = asyncio.run(collect())
    assert [performance.frame for performance in performances] == [5, 6, 7]
    assert all(performance.score is hm.SCORE for performance in performances)
