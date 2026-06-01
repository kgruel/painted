"""Behavioral unit tests for the live.py demo's stream + status path.

The golden test (tests/golden/test_demo_live.py) only snapshots the STATIC
render via `_fetch()` — the fully-resolved report with no spinners. This file
exercises the LIVE path the static golden never reaches:

  - `_fetch_stream()`: the async fan-out that yields HealthReport snapshots as
    checks resolve. We assert that progress advances (completed count rises,
    pending count falls) over successive snapshots.
  - `_status_icon()`: the PENDING -> spinner vs resolved -> icon branch.
  - spinner-frame progression: a PENDING status renders DOTS frame[frame % N].

Assertions are on STATE / return values (status enums, counts, the glyph the
returned Block carries), not on stripped frame text.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from painted.views.components.spinner import DOTS, SpinnerState, spinner

# Import the demo without sys.path mutation (mirrors the golden harness).
_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_live_stream",
    _PROJECT / "demos" / "patterns" / "live.py",
)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

Status = _mod.Status
HealthReport = _mod.HealthReport
_fetch_stream = _mod._fetch_stream
_status_icon = _mod._status_icon
_counts = _mod._counts


def _glyph(block) -> str:
    """The single character the 1x1 status/spinner Block carries."""
    return "".join(c.char for c in block.row(0))


# --- _status_icon: PENDING renders a spinner frame, resolved renders its icon ---


def test_status_icon_pending_renders_spinner_frame():
    """A PENDING status delegates to the spinner; the glyph is the DOTS frame
    at the given index. Pin against the spinner component's own output so the
    two stay in lockstep."""
    for frame in range(len(DOTS.frames) + 2):  # cover a wrap-around
        icon = _status_icon(Status.PENDING, frame)
        expected = spinner(SpinnerState(frame=frame))
        assert _glyph(icon) == _glyph(expected)
        # And it is exactly the DOTS frame the component indexes.
        assert _glyph(icon) == DOTS.frames[frame % len(DOTS.frames)]


def test_status_icon_spinner_frame_progresses():
    """Successive frames produce successive DOTS glyphs (and differ until wrap)."""
    glyphs = [_glyph(_status_icon(Status.PENDING, f)) for f in range(len(DOTS.frames))]
    assert glyphs == list(DOTS.frames)
    # One full period later we wrap back to the start.
    assert _glyph(_status_icon(Status.PENDING, len(DOTS.frames))) == DOTS.frames[0]


def test_status_icon_resolved_does_not_render_spinner_frame():
    """Resolved statuses ignore the frame and render a fixed (non-DOTS) glyph."""
    for status in (Status.HEALTHY, Status.DEGRADED, Status.DOWN):
        glyph_a = _glyph(_status_icon(status, frame=0))
        glyph_b = _glyph(_status_icon(status, frame=3))
        # Frame-independent.
        assert glyph_a == glyph_b
        # Not a spinner frame.
        assert glyph_a not in DOTS.frames


def test_status_icon_degraded_is_bang():
    """DEGRADED is rendered as a literal '!' (no icon-set glyph)."""
    assert _glyph(_status_icon(Status.DEGRADED, frame=0)) == "!"


# --- _fetch_stream: stepping the stream advances progress over time ---


@pytest.fixture(scope="module")
def stream_snapshots() -> list[HealthReport]:
    """Drain the live stream to completion ONCE, shared across the stream tests.

    `_fetch_stream` uses real `asyncio.sleep` (resolution delays up to ~1.8s), so
    draining per-test would multiply that wall time by the number of stream tests.
    Module scope drains once; each test asserts a different property of the same
    snapshot sequence.
    """

    async def _collect() -> list[HealthReport]:
        return [report async for report in _fetch_stream()]

    return asyncio.run(_collect())


def test_fetch_stream_first_snapshot_all_pending(stream_snapshots):
    """The stream opens with an all-pending snapshot at frame 0."""
    first = stream_snapshots[0]
    assert first.spinner_frame == 0
    assert first.elapsed_ms == 0.0
    counts = _counts(first.checks)
    total = len(first.checks)
    assert counts[Status.PENDING] == total
    assert total > 0


def test_fetch_stream_resolves_all_by_final_snapshot(stream_snapshots):
    """By the last snapshot every check has left PENDING."""
    final = stream_snapshots[-1]
    assert _counts(final.checks)[Status.PENDING] == 0
    # The static fan-out and the stream agree on the resolved statuses.
    resolved = {c.name: c.status for c in final.checks}
    static = {c.name: c.status for c in _mod._fetch().checks}
    assert resolved == static


def test_fetch_stream_progress_is_monotonic(stream_snapshots):
    """Pending count never rises and completed-count never falls across snapshots;
    by the end pending has strictly decreased from the opening snapshot."""
    pending = [_counts(s.checks)[Status.PENDING] for s in stream_snapshots]
    total = len(stream_snapshots[0].checks)

    # Pending is non-increasing (monotonic) snapshot to snapshot.
    for earlier, later in zip(pending, pending[1:]):
        assert later <= earlier

    # Completed fraction (the progress bar's input) is non-decreasing.
    fractions = [(total - p) / total for p in pending]
    for earlier, later in zip(fractions, fractions[1:]):
        assert later >= earlier

    # Progress actually moved: starts empty, ends full.
    assert fractions[0] == 0.0
    assert fractions[-1] == 1.0
    assert pending[-1] < pending[0]


def test_fetch_stream_spinner_frame_increments_per_step(stream_snapshots):
    """Each post-initial snapshot bumps spinner_frame by exactly one, so the
    spinner animates as checks land."""
    frames = [s.spinner_frame for s in stream_snapshots]
    # First snapshot is frame 0, then tick increments once per await-wait loop.
    assert frames[0] == 0
    for earlier, later in zip(frames, frames[1:]):
        assert later == earlier + 1
