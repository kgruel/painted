"""Law tests for the mandelbrot showcase demo.

The demo's claim is epistemic, not cosmetic: every cell is proved to escape,
proved to belong, or admitted as unknown, and the third is not the first two
with the lights off. Liveness can't catch a classifier that lies. So the laws
here are about what the three statuses are allowed to mean — the closed-form
proofs against brute-force iteration, monotone resolution under budget, the
one status that no budget can retire — plus the honesty pins the carrier owes
(the marked unknown survives a pipe) and the declaration ratchet (a status the
vocabulary doesn't declare cannot be rendered). No pose cosmetics are pinned.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

from painted import Fidelity, Zoom, use_vocabularies
from painted.capabilities import Capabilities, use_capabilities
from tests.helpers import block_to_text

_DEMO = Path(__file__).resolve().parent.parent.parent / "demos" / "showcase" / "mandelbrot.py"


def _load():
    spec = importlib.util.spec_from_file_location("_mandelbrot_demo", _DEMO)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_mandelbrot_demo"] = mod
    spec.loader.exec_module(mod)
    return mod


mb = _load()

# A deterministic lattice over the interesting region: the set lives inside
# |c| < 2, and this spans it densely enough to catch a sign flip anywhere.
_PROBES = [(-2.2 + 0.05 * i, -1.25 + 0.05 * j) for i in range(61) for j in range(51)]
_DEEP = 4000  # "long enough that a wrong proof would have been caught"


# --- Proof laws: the closed forms mean what they claim ---


def test_proved_interior_never_escapes() -> None:
    """The load-bearing law: a proof of membership is not a guess.

    The cardioid and bulb tests are the only places this demo asserts
    membership, and a sign flip in either would produce a renderer that
    paints escaping cells as proved. Brute force is the referee.
    """
    proved = 0
    for x, y in _PROBES:
        if not mb.proved_interior(x, y):
            continue
        proved += 1
        assert mb.classify(x, y, _DEEP)[0] == mb.INTERIOR
        # And directly: the orbit stays bounded for as long as we care to look.
        zx = zy = 0.0
        for _ in range(_DEEP):
            zx, zy = zx * zx - zy * zy + x, 2.0 * zx * zy + y
            assert zx * zx + zy * zy <= 4.0, f"proved-interior point escaped: {(x, y)}"
    assert proved > 100, "probe lattice never exercised the proof"


def test_the_proof_is_incomplete_and_the_demo_depends_on_it() -> None:
    """Points in the set that the closed form cannot reach stay unresolved.

    This is the demo's subject, so it is pinned rather than left to chance:
    the period-3 bulb's center is in the set (it is a superattracting cycle),
    no closed form here covers it, and therefore no budget resolves it.
    """
    c = (-0.12256117, 0.74486177)  # period-3 bulb center
    assert not mb.proved_interior(*c)
    for budget in (mb._LIVE_BUDGET, mb._SETTLE_BUDGET, _DEEP):
        assert mb.classify(*c, budget)[0] == mb.UNRESOLVED


def test_escape_is_proved_not_presumed() -> None:
    """Any cell called escaped really does pass the bailout radius."""
    for x, y in _PROBES:
        status, nu = mb.classify(x, y, 200)
        if status != mb.ESCAPED:
            continue
        zx = zy = 0.0
        for _ in range(int(nu) + 1):
            zx, zy = zx * zx - zy * zy + x, 2.0 * zx * zy + y
        assert zx * zx + zy * zy > mb._BAILOUT, f"escaped cell never left the disk: {(x, y)}"


def test_points_outside_the_escape_radius_escape_immediately() -> None:
    for x, y in _PROBES:
        if x * x + y * y > 4.0:
            assert mb.classify(x, y, 80)[0] == mb.ESCAPED


def test_smooth_escape_time_refines_its_step() -> None:
    """`nu` is a coordinate inside the escaping step, not a separate number.

    Pinning nu in [k, k+1) is what lets the gradient be continuous without
    the color drifting off the iteration it is reporting.
    """
    for x, y in _PROBES:
        status, nu = mb.classify(x, y, 200)
        if status != mb.ESCAPED:
            continue
        k = int(nu)
        assert k <= nu < k + 1.0


# --- Budget laws: what spending more can and cannot buy ---


def test_resolution_is_monotone_in_budget() -> None:
    """A bigger budget only ever moves cells out of `unresolved`.

    The whole live-then-settle arc rests on this: the settle must never
    un-know something the live frame had proved.
    """
    for x, y in _PROBES:
        small, _ = mb.classify(x, y, 40)
        large, _ = mb.classify(x, y, 400)
        if small != mb.UNRESOLVED:
            assert large == small, f"status changed under a larger budget at {(x, y)}"


def test_no_budget_empties_the_unknown() -> None:
    """Membership is semi-decidable, so the unresolved set never closes.

    The demo's central claim, stated as a test: raising the budget shrinks
    the unknown and never eliminates it, because the filaments and minor
    bulbs have no proof available at any budget.
    """
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    counts = mb.trace(view).counts
    assert counts[mb.UNRESOLVED] > 0
    # And directly, far past any budget the demo would ever spend:
    c = (-0.12256117, 0.74486177)
    assert mb.classify(*c, 20_000)[0] == mb.UNRESOLVED


def test_the_settle_spends_more_than_the_live_frame() -> None:
    live = mb.View(frame=300, settled=False)
    settled = mb.View(frame=300, settled=True)
    assert mb.budget_of(settled) > mb.budget_of(live)
    assert mb.trace(settled).counts[mb.UNRESOLVED] < mb.trace(live).counts[mb.UNRESOLVED]


def test_the_descent_is_a_pure_function_of_the_frame() -> None:
    """Any pose is reachable without replaying the ones before it."""
    assert mb.window_at(500) == mb.window_at(500)
    spans = [mb.window_at(f)[2] for f in range(0, 900, 50)]
    assert all(b < a for a, b in zip(spans, spans[1:])), "the descent must always descend"


def test_conjugate_symmetry_of_the_classifier() -> None:
    """The set is symmetric about the real axis; the classifier must be too.

    Probed on the classifier, not on a frame: the descent targets an
    off-axis point, so no rendered pose is symmetric.
    """
    for x, y in _PROBES:
        assert mb.classify(x, y, 120)[0] == mb.classify(x, -y, 120)[0]


# --- Carrier laws: the claims survive the delivery ---


def _render(view, zoom: Zoom, width: int = 80, **flags: bool):
    fidelity = Fidelity(depth=int(zoom), visible=frozenset(k for k, v in flags.items() if v))
    return mb._render(view, fidelity, width)


def test_the_unknown_is_marked_in_a_pipe() -> None:
    """No color, no glyphs: the picture degrades, the admission does not."""
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    with use_capabilities(Capabilities(color=False, glyph=False)):
        text = block_to_text(_render(view, Zoom.DETAILED))
    assert mb._GLYPH_UNRESOLVED in text, "the unresolved marker vanished without color"
    assert mb._GLYPH_INTERIOR in text
    grid = [ln for ln in text.splitlines() if mb._GLYPH_UNRESOLVED in ln]
    assert grid, "no rendered row carried the marker"


def test_the_colorless_grid_is_ascii_only() -> None:
    """The glyph-free carrier may not smuggle in a non-ASCII glyph.

    The grid is reached under `_render`, which is where the demo scopes its
    vocabulary, so the declaration has to be supplied here too — marking
    with an undeclared name raises, by design.
    """
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    with use_vocabularies(mb.MEMBERSHIP), use_capabilities(Capabilities(color=False, glyph=False)):
        grid = block_to_text(mb._grid_glyphs(view, mb._W, False))
    assert grid.isascii(), "the ASCII carrier emitted a non-ASCII glyph"


def test_every_status_is_a_declared_value() -> None:
    """The ratchet: a status the vocabulary doesn't declare cannot be marked.

    `mark_style` raises on an undeclared value, so this fails loudly the
    moment a fourth status is added to the classifier without being
    declared alongside the other three — the drift this demo is about.
    """
    from painted import mark_style

    assert set(mb._STATUS_NAMES) == set(mb.MEMBERSHIP.values)
    assert len(mb._STATUS_NAMES) == 3
    with use_vocabularies(mb.MEMBERSHIP):
        for status in (mb.ESCAPED, mb.INTERIOR, mb.UNRESOLVED):
            assert mark_style("membership", mb._STATUS_NAMES[status]) is not None


def test_proof_lens_changes_output_in_every_carrier() -> None:
    """A declared facet must change output — the honesty rule, as a test.

    Both carriers, because the first version of this demo honored `--proof`
    only in color: piped, the flag was in `--help`, compiled into the
    fidelity, and changed not one cell. A declared capability that does
    nothing is the failure this demo is about, so the pin covers the carrier
    where it hid.
    """
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    for caps in (
        Capabilities(color=True, glyph=True),
        Capabilities(color=False, glyph=False),
        Capabilities(color=False, glyph=True),
    ):
        with use_capabilities(caps):
            plain = _render(view, Zoom.SUMMARY)
            proof = _render(view, Zoom.SUMMARY, proof=True)
        assert plain.width == proof.width
        assert plain != proof, f"--proof changed nothing under {caps}"


def test_proof_lens_withholds_escape_time_not_status() -> None:
    """The flat lens drops the gradient's information, keeps the statuses."""
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    with use_vocabularies(mb.MEMBERSHIP), use_capabilities(Capabilities(color=False, glyph=False)):
        flat = block_to_text(mb._grid_glyphs(view, mb._W, True))
    drawn = set(flat) - {"\n"}
    assert drawn <= {mb._GLYPH_ESCAPED, mb._GLYPH_INTERIOR, mb._GLYPH_UNRESOLVED}
    assert mb._GLYPH_UNRESOLVED in drawn, "the admission did not survive the flat lens"


def test_the_note_is_a_named_facet_at_every_depth() -> None:
    """Authorship is not depth, so the note answers only to its own name.

    The pin is the shape of the claim: `--note` adds the note at any depth
    including MINIMAL, and no depth alone ever produces it.
    """
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    for zoom in Zoom:
        without = _render(view, zoom, 80)
        with_note = _render(view, zoom, 80, note=True)
        assert with_note != without, f"--note changed nothing at {zoom.name}"
        assert "Why the third color" in block_to_text(with_note)
        assert "Why the third color" not in block_to_text(without), (
            f"depth {zoom.name} produced the note without being asked"
        )


def test_a_note_too_narrow_to_render_says_so() -> None:
    """Content dropped for want of room owes evidence (RENDER_MODEL law 6)."""
    narrow = block_to_text(mb._note(20))
    assert "note withheld" in narrow
    assert len(narrow.splitlines()) == 1


def test_render_honors_the_offered_width_at_every_zoom() -> None:
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    for zoom in Zoom:
        for width in (40, 64, 80):
            assert _render(view, zoom, width).width <= width


def test_census_keeps_the_unresolved_share_when_width_is_tight() -> None:
    """The one figure that must never be the thing that gets ellipsized."""
    view = mb.View(frame=mb.DEFAULT_FRAME, settled=True)
    text = block_to_text(_render(view, Zoom.MINIMAL, mb._W))
    assert "unresolved" in text
    assert "%" in text


# --- Stream law ---


def test_the_stream_settles_on_its_last_yield() -> None:
    async def collect():
        return [v async for v in mb._fetch_stream(start=0, frames=3)]

    views = asyncio.run(collect())
    assert [v.settled for v in views] == [False, False, False, True]
    assert views[-1].frame == views[-2].frame, "the settle re-renders the pose it ended on"
