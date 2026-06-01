"""Surface-frame laws — the rendered frame is dimension-exact and column-valid.

The Block-level width/rectangularity/no-orphan-wide laws live in
`test_block_rectangle.py` / `test_text_width.py`, but those guard *Block
construction*. A TestSurface frame travels a different path: `Buffer.put_text`
writing directly into a 2D cell grid, composited and snapshotted by the harness.
This tier holds that path to the same contract, fuzzed over size and content:

  * every captured frame's buffer is exactly width x height (no drift under
    render), and
  * no orphaned wide character: a display-width-2 glyph never sits in the last
    column (it would overflow), and a wide lead is always followed by its space
    placeholder — `Buffer.put_text` must blank the overlap when a wide glyph
    straddles the right edge rather than leaving a half-written cell.

This is the Surface-stage analogue of the Block no-orphan-wide law — different
code (`buffer.py:put_text`), same invariant. Pinned `@example`s force the
straddle corner that a derandomized sample would otherwise rarely draw.
"""

from __future__ import annotations

from hypothesis import example, given
from hypothesis import strategies as st

from painted import Style
from painted.core._text_width import char_width
from painted.tui import Surface, TestSurface

# A,<wide>,B,<wide>,C and pure-wide / narrow-nonascii / empty — spans the regimes.
_STRINGS = ("A世B界C", "世界", "x", "→±—", "")


class _WideTextApp(Surface):
    """Fills with spaces, then writes one mixed-width string per row at an offset.

    A single put_text per row keeps the no-orphan law unambiguous: the only way a
    wide lead loses its placeholder is a put_text bug, not a legitimate later
    overwrite.
    """

    def __init__(self, offset: int, idx: int) -> None:
        super().__init__()
        self._offset = offset
        self._idx = idx

    def render(self) -> None:
        s = _STRINGS[self._idx % len(_STRINGS)]
        buf = self._buf
        buf.fill(0, 0, buf.width, buf.height, " ", Style())
        for y in range(buf.height):
            buf.put_text(self._offset, y, s, Style())


@given(
    width=st.integers(min_value=1, max_value=40),
    height=st.integers(min_value=1, max_value=12),
    offset=st.integers(min_value=0, max_value=42),
    idx=st.integers(min_value=0, max_value=len(_STRINGS) - 1),
)
# Straddle corner: a 2-wide app surface with the wide lead pushed against the
# right edge — the exact case put_text must blank rather than orphan.
@example(width=2, height=1, offset=1, idx=0)
@example(width=3, height=1, offset=2, idx=1)
def test_surface_frame_is_dimension_exact_and_column_valid(
    width: int, height: int, offset: int, idx: int
) -> None:
    app = _WideTextApp(offset, idx)
    frames = TestSurface(app, width=width, height=height).run_to_completion()
    assert frames, "no frame captured"

    for frame in frames:
        buf = frame.buffer
        assert buf.width == width
        assert buf.height == height
        assert len(buf._cells) == width * height, "buffer cell count drifted from w*h"

        for y in range(height):
            row = [buf.get(x, y) for x in range(width)]
            assert len(row) == width  # rectangular
            for x, cell in enumerate(row):
                if char_width(cell.char) == 2:
                    assert x < width - 1, (
                        f"wide-char lead at last column ({x},{y}) — orphaned overflow"
                    )
                    assert row[x + 1].char == " ", (
                        f"wide-char lead at ({x},{y}) without space placeholder"
                    )
