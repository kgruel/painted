"""Diff-render invariant — "Surface diff-renders: only changed cells written."

This is the single most important correctness promise of the TUI subsystem, and
until now it lived only in docs. `TestSurface._render_and_capture` computes
`frame.writes = buf.diff(prev)` — the same diff core `Surface._flush` uses to
decide what reaches the terminal — so we can hold the loop to the law:

  * a frame that changes nothing visible writes **nothing**, and
  * a frame writes **exactly** the cells that changed since the previous frame —
    no full repaint (over-write), no missed cell (under-write), and each write
    carries the *new* cell value.

The ground-truth changed set is recomputed here cell-by-cell via `Buffer.get`,
independently of `Buffer.diff` — so this test is a real check on the diff path,
not a tautology against it. (Teeth confirmed by mutation: forcing `Buffer.diff`
to full-repaint or to drop cells turns the exact-match tests red.)

Scope: this guards `Buffer.diff` (the diff core) through the harness, not the
`_flush` *wiring* around it. The scroll-optimized flush path deliberately repaints
whole lines (so "only changed cells" does not hold there) and is owned by
`test_scroll_optimization.py`; full-repaint-on-resize is owned by `test_resize.py`.
`PaintApp` is sized (height 4) so it never trips scroll optimization (which needs a
region height ≥ 6), keeping every frame here in the pure diff regime.
"""

from __future__ import annotations

from painted import Style
from painted.core.buffer import Buffer, Cell
from painted.tui import Surface, TestSurface

WIDTH, HEIGHT = 12, 4


class PaintApp(Surface):
    """Minimal Surface with two independently-addressable painted regions.

    `+` mutates one cell (the counter at 0,0); `L` mutates another (the label at
    5,1); `n` is a deliberate no-op; `q` quits. Each render fully repaints the
    buffer — so any over-writing must come from the *diff*, not from the app
    touching cells it didn't change.
    """

    def __init__(self) -> None:
        super().__init__()
        self.n = 0
        self.label = "."

    def render(self) -> None:
        self._buf.fill(0, 0, self._buf.width, self._buf.height, " ", Style())
        self._buf.put_text(0, 0, str(self.n), Style())
        self._buf.put_text(5, 1, self.label, Style())

    def on_key(self, key: str) -> None:
        if key == "+":
            self.n = (self.n + 1) % 10
        elif key == "L":
            self.label = "X"
        elif key == "n":
            pass  # no-op: state unchanged -> buffer unchanged -> zero writes
        elif key == "q":
            self.quit()


def _changed_cells(cur: Buffer, prev: Buffer) -> dict[tuple[int, int], Cell]:
    """Ground-truth diff: positions whose cell value changed, with the new cell.

    Computed independently of `Buffer.diff` so it can be the oracle that checks it.
    """
    changed: dict[tuple[int, int], Cell] = {}
    for y in range(cur.height):
        for x in range(cur.width):
            new = cur.get(x, y)
            if new != prev.get(x, y):
                changed[(x, y)] = new
    return changed


def _writes_as_dict(frame) -> dict[tuple[int, int], Cell]:
    return {(w.x, w.y): w.cell for w in frame.writes}


class TestDiffRenderInvariant:
    def test_no_visual_change_writes_nothing(self) -> None:
        """A no-op input re-renders an identical buffer and writes zero cells."""
        app = PaintApp()
        frames = TestSurface(
            app, width=WIDTH, height=HEIGHT, input_queue=["n", "q"]
        ).run_to_completion()

        assert len(frames) == 3  # initial + "n" + "q"
        # Independent check that "n"/"q" truly changed nothing visible...
        assert _changed_cells(frames[1].buffer, frames[0].buffer) == {}
        assert _changed_cells(frames[2].buffer, frames[1].buffer) == {}
        # ...so the diff path must have emitted no writes at all.
        assert frames[1].writes == ()
        assert frames[2].writes == ()

    def test_single_cell_change_writes_only_that_cell(self) -> None:
        """Changing one cell writes exactly that one cell, with its new value."""
        app = PaintApp()  # n=0 -> "0" at (0,0)
        frames = TestSurface(
            app, width=WIDTH, height=HEIGHT, input_queue=["+", "q"]
        ).run_to_completion()

        change = frames[1]  # after "+": n=1, only (0,0) flips "0" -> "1"
        assert len(change.writes) == 1
        assert _writes_as_dict(change) == {(0, 0): change.buffer.get(0, 0)}
        assert change.buffer.get(0, 0).char == "1"

    def test_writes_are_exactly_the_changed_cells_every_frame(self) -> None:
        """Across a mixed sequence, every frame's writes == the cells that changed."""
        app = PaintApp()
        harness = TestSurface(
            app,
            width=WIDTH,
            height=HEIGHT,
            input_queue=["+", "L", "n", "+", "q"],
        )
        frames = harness.run_to_completion()

        # The harness seeds the diff against a blank buffer for the first frame,
        # exactly as Surface.run() does (_prev = Buffer(w, h)).
        prev = Buffer(harness.width, harness.height)
        for i, frame in enumerate(frames):
            expected = _changed_cells(frame.buffer, prev)
            actual = _writes_as_dict(frame)
            assert actual == expected, (
                f"frame {i}: diff-render wrote {sorted(actual)} but only {sorted(expected)} changed"
            )
            # Every emitted write must carry the post-render value at its cell.
            for (x, y), cell in actual.items():
                assert cell == frame.buffer.get(x, y)
            prev = frame.buffer
