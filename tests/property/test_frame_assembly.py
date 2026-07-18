"""Frame-assembly laws — the F-conditional algorithm over all inputs (§6).

The unit tests pin the named branches; these pin the invariants that must hold
for *any* content height, offset, and frame height ``F ≥ 0``:

  * the exactness law: the assembled frame has exactly ``F`` rows and exactly the
    content's width — the frame builder honors its allocation and never perturbs
    width (a row, never a rail),
  * the evidence law: an evidence row appears iff content overflows the frame
    (``content.height > F``) *and* ``F ≥ 1`` (evidence is waived at F=0), and
  * the slice law: the content rows shown are exactly the window the offset
    selects — derived independently of the implementation, so an ignored or
    wrong in-range offset is caught.

Each content row carries a *distinct* payload (a unique leading char per row), so
the shown window is identifiable — identical rows would make a wrong offset
invisible. The evidence row is detected by a sentinel ref: content rows carry
none, so a last row bearing the passed ``ref`` is the evidence row.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.core.block import Block
from painted.core.cell import Style

from painted.views import assemble_frame

_EV_REF = "evidence:sentinel"

# Content widths kept small but nonzero; a zero-width frame is a separate
# degenerate handled by the unit tier. Max height (40) stays below the distinct
# per-row alphabet below.
widths = st.integers(min_value=1, max_value=12)
heights = st.integers(min_value=0, max_value=40)
offsets = st.integers(min_value=-5, max_value=60)
frames = st.integers(min_value=0, max_value=40)


def _row_char(i: int) -> str:
    """A distinct single-width ASCII glyph identifying content row ``i``."""
    return chr(ord("A") + i)  # A.. — unique and single-column for i < ~50


def _content(n: int, width: int) -> Block:
    """``n`` ref-less content rows, each a distinct repeated char (row identity)."""
    if n == 0:
        return Block.empty(width, 0)
    return Block.column([(_row_char(i) * width, Style()) for i in range(n)], width=width)


def _last_row_is_evidence(frame: Block) -> bool:
    """True iff the frame's last row carries the sentinel evidence ref."""
    if frame.height == 0:
        return False
    return frame.cell_ref(0, frame.height - 1) == _EV_REF


def _expected_offset(h: int, f: int, offset: int) -> int:
    """The clamped top-of-window the overflow branch must show — derived here,
    independently of ``assemble_frame``, so a mis-clamp is detectable."""
    shown = f - 1
    return max(0, min(offset, h - shown))


class TestFrameAssemblyLaws:
    @given(h=heights, width=widths, offset=offsets, f=frames)
    def test_frame_is_exactly_f_rows_of_content_width(self, h, width, offset, f):
        frame = assemble_frame(_content(h, width), f, offset, ref=_EV_REF)
        assert frame.height == f
        assert frame.width == width

    @given(h=heights, width=widths, offset=offsets, f=frames)
    def test_evidence_appears_iff_overflow_and_room(self, h, width, offset, f):
        frame = assemble_frame(_content(h, width), f, offset, ref=_EV_REF)
        overflows = h > f
        expect_evidence = overflows and f >= 1
        assert _last_row_is_evidence(frame) == expect_evidence

    @given(h=heights, width=widths, offset=offsets, f=frames)
    def test_shown_rows_are_the_offset_window(self, h, width, offset, f):
        """The content rows shown are exactly the slice the (clamped) offset
        selects — proven against distinct per-row identities."""
        frame = assemble_frame(_content(h, width), f, offset, ref=_EV_REF)
        has_evidence = _last_row_is_evidence(frame)
        shown = frame.height - (1 if has_evidence else 0)

        if has_evidence:
            # Overflow: F-1 content rows starting at the independently-clamped top.
            top = _expected_offset(h, f, offset)
        else:
            # Fits (or F=0): content is top-anchored from row 0, offset ignored.
            top = 0

        for y in range(shown):
            first_char = frame.row(y)[0].char if width else " "
            content_idx = top + y
            if content_idx < h:
                assert first_char == _row_char(content_idx), (
                    f"row {y} shows {first_char!r}, expected content row {content_idx}"
                )
            else:
                # Beyond content — bottom padding (only reachable in the fits case).
                assert not has_evidence
                assert frame.row(y)[0].char == " " if width else True
