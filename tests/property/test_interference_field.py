"""The wave drawing's symmetry and bounds, independent of its raster."""

import math
from pathlib import Path

from hypothesis import given, strategies as st

from painted import Fidelity, Style
from painted.capabilities import Capabilities, use_capabilities

from tests.helpers import block_to_text
from tools.capture import import_module_by_path

_DEMO = Path(__file__).resolve().parents[2] / "demos" / "showcase" / "interference.py"
D = import_module_by_path(_DEMO, module_name="_interference_laws")


@given(
    x=st.floats(-20, 20),
    y=st.floats(-20, 20),
    frame=st.integers(-10000, 10000),
    phase=st.sampled_from(("together", "opposed")),
)
def test_superposition_is_bounded_and_has_the_declared_symmetry(x, y, frame, phase):
    field = D._fetch(frame, phase)
    value = D._value(x, y, field)
    assert -1 <= value <= 1
    reflection = D._value(-x, y, field)
    sign = 1 if phase == "together" else -1
    assert math.isclose(value, sign * reflection, abs_tol=1e-12)
    assert math.isclose(value, D._value(x, -y, field), abs_tol=1e-12)


@given(y=st.floats(-20, 20), frame=st.integers(-10000, 10000))
def test_opposed_sources_cancel_on_the_entire_bisector(y, frame):
    assert abs(D._value(0, y, D._fetch(frame, "opposed"))) < 1e-12


@given(
    x=st.floats(-20, 20),
    y=st.floats(-20, 20),
    frame=st.integers(-10000, 10000),
    phase=st.sampled_from(("together", "opposed")),
)
def test_field_repeats_after_48_frames(x, y, frame, phase):
    # Trig argument reduction accumulates roundoff over this frame range;
    # absolute tolerance also covers the cancellation nodes near zero.
    assert math.isclose(
        D._value(x, y, D._fetch(frame, phase)),
        D._value(x, y, D._fetch(frame + 48, phase)),
        rel_tol=0,
        abs_tol=1e-12,
    )


@given(
    x=st.floats(-20, 20),
    y=st.floats(-20, 20),
    frame=st.integers(-10000, 10000),
    phase=st.sampled_from(("together", "opposed")),
)
def test_field_negates_after_24_frames(x, y, frame, phase):
    assert math.isclose(
        D._value(x, y, D._fetch(frame, phase)),
        -D._value(x, y, D._fetch(frame + 24, phase)),
        rel_tol=0,
        abs_tol=1e-12,
    )


@given(
    width=st.one_of(st.none(), st.integers(0, 160)),
    depth=st.integers(0, 3),
    tags=st.sets(st.sampled_from(("note", "stats"))).map(frozenset),
    color=st.booleans(),
    glyph=st.booleans(),
    phase=st.sampled_from(("together", "opposed")),
)
def test_render_honors_width_at_every_fidelity_and_capability(
    width, depth, tags, color, glyph, phase
):
    with use_capabilities(Capabilities(color=color, glyph=glyph)):
        block = D._render(D._fetch(phase=phase), Fidelity(depth=depth, visible=tags), width)
    assert block.width == (D._COLUMNS + 2 if width is None else width)
    assert block.height > 0
    assert all(len(block.row(y)) == block.width for y in range(block.height))


@given(value=st.floats(min_value=0.045, max_value=1), glyph=st.booleans())
def test_colorless_picture_preserves_sign_even_without_unicode(value, glyph):
    # The stronger of each pair survives; averaging these pairs would lose its sign.
    samples = ((value, -value, 0.0), (-value / 2, value / 2, 0.0))
    with use_capabilities(Capabilities(color=False, glyph=glyph)):
        picture = D._picture(samples)
    positive, negative, quiet = picture.row(0)
    assert positive.char in ".oO@"
    assert negative.char in ",-x#"
    assert quiet.char == " "
    assert all(cell.style == Style() for cell in picture.row(0))


@given(
    frame=st.integers(-10000, 10000),
    phase=st.sampled_from(("together", "opposed")),
)
def test_disclosure_and_named_facets_show_measurements_and_signed_note(frame, phase):
    field = D._fetch(frame, phase)
    summary = D._render(field, Fidelity(depth=1), None)
    detailed = D._render(field, Fidelity(depth=2), None)
    full = D._render(field, Fidelity(depth=3), None)
    stats = D._render(field, Fidelity(depth=1, visible=frozenset({"stats"})), None)
    note = D._render(field, Fidelity(depth=1, visible=frozenset({"note"})), None)
    assert summary.height < detailed.height < full.height
    assert stats.height > summary.height
    assert note.height > summary.height
    for block in (summary, detailed, note):
        assert " / RMS " not in block_to_text(block)
    for block in (full, stats):
        text = block_to_text(block)
        assert "samples 2628 / RMS " in text
        assert " / near zero " in text
    for block in (summary, detailed, full, stats):
        assert "The shape of a cancellation" not in block_to_text(block)
        assert "Astra" not in block_to_text(block)
    note_text = block_to_text(note)
    assert "The shape of a cancellation" in note_text
    assert "Each source makes rings." in note_text
    assert "— Astra" in note_text
