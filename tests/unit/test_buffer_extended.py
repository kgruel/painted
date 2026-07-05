"""Extended tests for Buffer and BufferView — covering scroll, clone, hit, views."""

from painted.core.buffer import Buffer, BufferView, CellWrite
from painted.core._text_width import display_width
from painted.core.cell import EMPTY_CELL, Cell, Style

S = Style()
S_RED = Style(fg="red")


# -- Buffer: get/put out-of-bounds ------------------------------------------


class TestBufferBounds:
    def test_get_out_of_bounds_returns_empty(self):
        buf = Buffer(3, 2)
        assert buf.get(-1, 0) == EMPTY_CELL
        assert buf.get(3, 0) == EMPTY_CELL
        assert buf.get(0, -1) == EMPTY_CELL
        assert buf.get(0, 2) == EMPTY_CELL

    def test_put_out_of_bounds_ignored(self):
        buf = Buffer(3, 2)
        buf.put(-1, 0, "x", S)  # should not raise
        buf.put(3, 0, "x", S)
        buf.put(0, 2, "x", S)
        # buffer should remain empty
        for y in range(2):
            for x in range(3):
                assert buf.get(x, y) == EMPTY_CELL

    def test_put_ref_out_of_bounds_ignored(self):
        buf = Buffer(3, 2)
        buf.put_ref(-1, 0, "x", S, "ref1")  # should not raise
        buf.put_ref(3, 0, "x", S, "ref1")
        buf.put_ref(0, 2, "x", S, "ref1")
        # no cells changed
        assert buf.get(0, 0) == EMPTY_CELL


# -- Buffer: put_text wide and special chars --------------------------------


class TestBufferPutText:
    def test_put_text_basic(self):
        buf = Buffer(5, 1)
        buf.put_text(0, 0, "hi", S)
        assert buf.get(0, 0) == Cell("h", S)
        assert buf.get(1, 0) == Cell("i", S)
        assert buf.get(2, 0) == EMPTY_CELL

    def test_put_text_wide_char(self):
        """Wide characters (e.g. CJK) occupy 2 cells."""
        buf = Buffer(6, 1)
        buf.put_text(0, 0, "\u4e16", S)  # '世' is width-2
        assert buf.get(0, 0) == Cell("\u4e16", S)
        assert buf.get(1, 0) == Cell(" ", S)  # placeholder

    def test_put_text_wide_char_does_not_overflow_narrow_buffer(self):
        """A narrow target must not end up containing a half-rendered wide glyph."""
        buf = Buffer(1, 1)
        buf.put_text(0, 0, "\u4e16", S)
        rendered = "".join(buf.get(x, 0).char for x in range(buf.width))
        assert display_width(rendered) <= buf.width

    def test_put_text_skips_non_printable(self):
        """Control characters (wcwidth < 0) are skipped."""
        buf = Buffer(5, 1)
        buf.put_text(0, 0, "a\x01b", S)
        assert buf.get(0, 0) == Cell("a", S)
        assert buf.get(1, 0) == Cell("b", S)

    def test_put_text_skips_zero_width(self):
        """Combining characters (wcwidth == 0) are skipped."""
        buf = Buffer(5, 1)
        buf.put_text(0, 0, "a\u0301b", S)  # \u0301 is combining acute accent
        assert buf.get(0, 0) == Cell("a", S)
        assert buf.get(1, 0) == Cell("b", S)

    def test_put_text_clears_refs(self):
        """put_text clears refs on cells it writes to when _refs is initialized."""
        buf = Buffer(5, 1)
        buf.put_ref(0, 0, "A", S, "tag")
        assert buf.hit(0, 0) == "tag"
        buf.put_text(0, 0, "x", S)
        assert buf.hit(0, 0) is None

    def test_put_text_wide_char_clears_refs_on_both_cells(self):
        """Wide char placeholder also clears refs."""
        buf = Buffer(5, 1)
        buf.put_ref(0, 0, "A", S, "t1")
        buf.put_ref(1, 0, "B", S, "t2")
        buf.put_text(0, 0, "\u4e16", S)  # width-2
        assert buf.hit(0, 0) is None
        assert buf.hit(1, 0) is None


# -- Buffer: fill with refs tracking ----------------------------------------


class TestBufferFill:
    def test_fill_clears_refs(self):
        buf = Buffer(4, 2)
        buf.put_ref(1, 0, "A", S, "tag")
        assert buf.hit(1, 0) == "tag"
        buf.fill(0, 0, 4, 2, ".", S)
        assert buf.hit(1, 0) is None


# -- Buffer: hit with no refs initialized -----------------------------------


class TestBufferHit:
    def test_hit_no_refs_returns_none(self):
        buf = Buffer(3, 2)
        assert buf.hit(0, 0) is None

    def test_hit_out_of_bounds_returns_none(self):
        buf = Buffer(3, 2)
        assert buf.hit(-1, 0) is None
        assert buf.hit(3, 0) is None

    def test_hit_with_refs(self):
        buf = Buffer(3, 2)
        buf.put_ref(1, 1, "X", S, "btn")
        assert buf.hit(1, 1) == "btn"
        assert buf.hit(0, 0) is None  # no ref assigned


# -- Buffer: clone ----------------------------------------------------------


class TestBufferClone:
    def test_clone_copies_cells(self):
        buf = Buffer(3, 2)
        buf.put(0, 0, "A", S)
        cloned = buf.clone()
        assert cloned.get(0, 0) == Cell("A", S)
        assert cloned.width == 3
        assert cloned.height == 2

    def test_clone_is_independent(self):
        buf = Buffer(3, 2)
        buf.put(0, 0, "A", S)
        cloned = buf.clone()
        cloned.put(0, 0, "B", S)
        assert buf.get(0, 0) == Cell("A", S)
        assert cloned.get(0, 0) == Cell("B", S)

    def test_clone_copies_refs(self):
        buf = Buffer(3, 2)
        buf.put_ref(1, 0, "X", S, "tag")
        cloned = buf.clone()
        assert cloned.hit(1, 0) == "tag"
        # modifying clone refs doesn't affect original
        cloned.put_ref(1, 0, "Y", S, "other")
        assert buf.hit(1, 0) == "tag"


# -- Buffer: diff -----------------------------------------------------------


class TestBufferDiff:
    def test_diff_identical_buffers(self):
        a = Buffer(3, 2)
        b = a.clone()
        assert a.diff(b) == []

    def test_diff_single_change(self):
        a = Buffer(3, 2)
        a.put(1, 0, "X", S)
        b = Buffer(3, 2)
        writes = a.diff(b)
        assert len(writes) == 1
        assert writes[0].x == 1
        assert writes[0].y == 0
        assert writes[0].cell == Cell("X", S)

    def test_diff_multiple_changes(self):
        a = Buffer(3, 2)
        a.put(0, 0, "A", S)
        a.put(2, 1, "B", S_RED)
        b = Buffer(3, 2)
        writes = a.diff(b)
        assert len(writes) == 2

    def test_cellwrite_ref_defaults_none(self):
        # The new field is additive: a plain write carries no ref.
        assert CellWrite(0, 0, Cell("a", S)).ref is None

    def test_diff_same_glyph_different_ref_emits_write_with_new_ref(self):
        # Same char + style, only the ref changed: the stale-hyperlink blind spot.
        # The write must be emitted, carrying the NEW buffer's ref.
        new = Buffer(1, 1)
        new.put_ref(0, 0, "a", S, "fact:x")
        old = Buffer(1, 1)
        old.put_ref(0, 0, "a", S, "fact:y")
        writes = new.diff(old)
        assert len(writes) == 1
        assert writes[0].cell == Cell("a", S)
        assert writes[0].ref == "fact:x"

    def test_diff_ref_only_change_repaints_without_any_resolver(self):
        # diff is resolver-agnostic — it is a buffer-layer concern. A ref-only
        # change repaints even though no RefScheme is declared anywhere.
        new = Buffer(1, 1)
        new.put_ref(0, 0, "a", S, "fact:x")
        old = Buffer(1, 1)
        old.put(0, 0, "a", S)  # no ref grid on the old side
        writes = new.diff(old)
        assert len(writes) == 1
        assert writes[0].ref == "fact:x"

    def test_diff_ref_cleared_emits_write_with_none(self):
        new = Buffer(1, 1)
        new.put(0, 0, "a", S)  # ref cleared
        old = Buffer(1, 1)
        old.put_ref(0, 0, "a", S, "fact:x")
        writes = new.diff(old)
        assert len(writes) == 1
        assert writes[0].ref is None

    def test_diff_identical_cells_and_refs_is_empty(self):
        new = Buffer(1, 1)
        new.put_ref(0, 0, "a", S, "fact:x")
        old = Buffer(1, 1)
        old.put_ref(0, 0, "a", S, "fact:x")
        assert new.diff(old) == []

    def test_diff_ref_less_common_case_stays_empty(self):
        # Neither side allocated a ref grid: the fast list-equality short-circuit.
        a = Buffer(3, 2)
        a.put(0, 0, "A", S)
        b = a.clone()
        assert a.diff(b) == []

    def test_diff_dimension_mismatch_carries_new_refs(self):
        new = Buffer(1, 1)
        new.put_ref(0, 0, "a", S, "fact:x")
        old = Buffer(2, 1)  # full-repaint path
        writes = new.diff(old)
        assert len(writes) == 1
        assert writes[0].ref == "fact:x"


# -- Buffer: line_hashes ---------------------------------------------------


class TestBufferLineHashes:
    def test_line_hashes_length(self):
        buf = Buffer(4, 3)
        hashes = buf.line_hashes()
        assert len(hashes) == 3

    def test_identical_rows_same_hash(self):
        buf = Buffer(4, 2)
        # both rows are empty -> same hash
        hashes = buf.line_hashes()
        assert hashes[0] == hashes[1]

    def test_different_rows_different_hash(self):
        buf = Buffer(4, 2)
        buf.put(0, 0, "X", S)
        hashes = buf.line_hashes()
        assert hashes[0] != hashes[1]

    def test_include_style_false(self):
        buf = Buffer(4, 2)
        buf.put(0, 0, "X", S)
        buf.put(0, 1, "X", S_RED)
        hashes_with = buf.line_hashes(include_style=True)
        hashes_without = buf.line_hashes(include_style=False)
        # with style: different because styles differ
        assert hashes_with[0] != hashes_with[1]
        # without style: same because chars are the same
        assert hashes_without[0] == hashes_without[1]


# -- Buffer: scroll_region_in_place ----------------------------------------


class TestBufferScroll:
    def _row_chars(self, buf: Buffer, y: int) -> str:
        return "".join(buf.get(x, y).char for x in range(buf.width))

    def _setup_labeled(self) -> Buffer:
        """Create a 3x4 buffer with rows labeled 'aaa', 'bbb', 'ccc', 'ddd'."""
        buf = Buffer(3, 4)
        for y, ch in enumerate("abcd"):
            buf.put_text(0, y, ch * 3, S)
        return buf

    def test_scroll_up_by_1(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, 1)
        assert self._row_chars(buf, 0) == "bbb"
        assert self._row_chars(buf, 1) == "ccc"
        assert self._row_chars(buf, 2) == "ddd"
        assert self._row_chars(buf, 3) == "   "  # filled with EMPTY_CELL

    def test_scroll_down_by_1(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, -1)
        assert self._row_chars(buf, 0) == "   "
        assert self._row_chars(buf, 1) == "aaa"
        assert self._row_chars(buf, 2) == "bbb"
        assert self._row_chars(buf, 3) == "ccc"

    def test_scroll_up_by_2(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, 2)
        assert self._row_chars(buf, 0) == "ccc"
        assert self._row_chars(buf, 1) == "ddd"
        assert self._row_chars(buf, 2) == "   "
        assert self._row_chars(buf, 3) == "   "

    def test_scroll_down_by_2(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, -2)
        assert self._row_chars(buf, 0) == "   "
        assert self._row_chars(buf, 1) == "   "
        assert self._row_chars(buf, 2) == "aaa"
        assert self._row_chars(buf, 3) == "bbb"

    def test_scroll_noop_when_n_is_zero(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, 0)
        assert self._row_chars(buf, 0) == "aaa"
        assert self._row_chars(buf, 3) == "ddd"

    def test_scroll_clears_all_when_n_exceeds_region(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, 10)
        for y in range(4):
            assert self._row_chars(buf, y) == "   "

    def test_scroll_clears_all_negative_exceeds_region(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(0, 3, -10)
        for y in range(4):
            assert self._row_chars(buf, y) == "   "

    def test_scroll_sub_region(self):
        """Scroll only middle rows, leaving top and bottom untouched."""
        buf = self._setup_labeled()
        buf.scroll_region_in_place(1, 2, 1)  # scroll rows 1-2 up by 1
        assert self._row_chars(buf, 0) == "aaa"  # untouched
        assert self._row_chars(buf, 1) == "ccc"  # was row 2
        assert self._row_chars(buf, 2) == "   "  # cleared
        assert self._row_chars(buf, 3) == "ddd"  # untouched

    def test_scroll_with_custom_fill(self):
        buf = self._setup_labeled()
        fill_cell = Cell(".", S_RED)
        buf.scroll_region_in_place(0, 3, 1, fill=fill_cell)
        assert buf.get(0, 3) == fill_cell

    def test_scroll_top_greater_than_bottom_noop(self):
        buf = self._setup_labeled()
        buf.scroll_region_in_place(3, 0, 1)  # top > bottom -> noop
        assert self._row_chars(buf, 0) == "aaa"
        assert self._row_chars(buf, 3) == "ddd"

    def test_scroll_clamps_top_bottom(self):
        buf = self._setup_labeled()
        # top=-5, bottom=100 should be clamped to 0..3
        buf.scroll_region_in_place(-5, 100, 1)
        assert self._row_chars(buf, 0) == "bbb"
        assert self._row_chars(buf, 3) == "   "

    def test_scroll_moves_hit_refs_with_cells(self):
        buf = Buffer(2, 3)
        for y, tag in enumerate(("a", "b", "c")):
            buf.put_ref(0, y, tag.upper(), S, tag)

        buf.scroll_region_in_place(0, 2, 1)

        assert buf.get(0, 0) == Cell("B", S)
        assert buf.hit(0, 0) == "b"
        assert buf.get(0, 1) == Cell("C", S)
        assert buf.hit(0, 1) == "c"
        assert buf.hit(0, 2) is None


# -- BufferView: coordinate translation & clipping --------------------------


class TestBufferView:
    def test_view_put_translates_coords(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 3, 5, 4)
        view.put(0, 0, "A", S)
        assert buf.get(2, 3) == Cell("A", S)

    def test_view_put_clips_out_of_bounds(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 3, 5, 4)
        view.put(-1, 0, "X", S)  # should be clipped
        view.put(5, 0, "X", S)  # should be clipped
        view.put(0, -1, "X", S)  # should be clipped
        view.put(0, 4, "X", S)  # should be clipped
        # entire buffer at offset region should be empty
        assert buf.get(2, 3) == EMPTY_CELL

    def test_view_put_ref(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 3, 5, 4)
        view.put_ref(1, 1, "B", S, "btn")
        assert buf.get(3, 4) == Cell("B", S)
        assert buf.hit(3, 4) == "btn"

    def test_view_put_ref_clips_out_of_bounds(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 3, 5, 4)
        view.put_ref(-1, 0, "X", S, "the-ref")  # clipped
        view.put_ref(5, 0, "X", S, "the-ref")  # clipped
        assert buf.get(2, 3) == EMPTY_CELL

    def test_view_put_text(self):
        buf = Buffer(10, 10)
        view = buf.region(1, 1, 5, 3)
        view.put_text(0, 0, "hi", S)
        assert buf.get(1, 1) == Cell("h", S)
        assert buf.get(2, 1) == Cell("i", S)

    def test_view_put_text_clips(self):
        """Text running past view width is clipped."""
        buf = Buffer(10, 10)
        view = buf.region(0, 0, 3, 1)
        view.put_text(0, 0, "abcde", S)
        assert buf.get(0, 0) == Cell("a", S)
        assert buf.get(1, 0) == Cell("b", S)
        assert buf.get(2, 0) == Cell("c", S)
        assert buf.get(3, 0) == EMPTY_CELL  # outside view

    def test_view_put_text_wide_char(self):
        buf = Buffer(10, 10)
        view = buf.region(1, 0, 6, 1)
        view.put_text(0, 0, "\u4e16", S)  # width-2
        assert buf.get(1, 0) == Cell("\u4e16", S)
        assert buf.get(2, 0) == Cell(" ", S)  # placeholder

    def test_view_put_text_wide_char_fully_clips_at_edge(self):
        """A wide char that cannot fit in the view should be skipped entirely."""
        buf = Buffer(10, 10)
        view = buf.region(0, 0, 2, 1)
        # Place a wide char at the last visible column.
        view.put_text(1, 0, "\u4e16", S)
        assert buf.get(1, 0) == EMPTY_CELL
        assert buf.get(2, 0) == EMPTY_CELL  # placeholder clipped

    def test_view_put_text_skips_non_printable(self):
        """BufferView.put_text skips control chars (wcwidth < 0)."""
        buf = Buffer(10, 10)
        view = buf.region(0, 0, 5, 1)
        view.put_text(0, 0, "a\x01b", S)
        assert buf.get(0, 0) == Cell("a", S)
        assert buf.get(1, 0) == Cell("b", S)

    def test_view_put_text_skips_zero_width(self):
        """BufferView.put_text skips combining marks (wcwidth == 0)."""
        buf = Buffer(10, 10)
        view = buf.region(0, 0, 5, 1)
        view.put_text(0, 0, "a\u0301b", S)
        assert buf.get(0, 0) == Cell("a", S)
        assert buf.get(1, 0) == Cell("b", S)

    def test_view_fill(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 2, 3, 3)
        view.fill(0, 0, 2, 2, ".", S_RED)
        assert buf.get(2, 2) == Cell(".", S_RED)
        assert buf.get(3, 2) == Cell(".", S_RED)
        assert buf.get(2, 3) == Cell(".", S_RED)
        assert buf.get(3, 3) == Cell(".", S_RED)
        assert buf.get(4, 2) == EMPTY_CELL  # outside filled region

    def test_view_fill_clips(self):
        buf = Buffer(10, 10)
        view = buf.region(0, 0, 2, 2)
        view.fill(0, 0, 5, 5, ".", S)  # larger than view
        assert buf.get(0, 0) == Cell(".", S)
        assert buf.get(1, 1) == Cell(".", S)
        assert buf.get(2, 0) == EMPTY_CELL  # outside view
        assert buf.get(0, 2) == EMPTY_CELL  # outside view

    def test_view_hit(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 2, 5, 5)
        buf.put_ref(3, 3, "X", S, "item")
        assert view.hit(1, 1) == "item"

    def test_view_hit_out_of_bounds(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 2, 5, 5)
        assert view.hit(-1, 0) is None
        assert view.hit(5, 0) is None

    def test_view_dimensions(self):
        buf = Buffer(10, 10)
        view = buf.region(2, 3, 5, 4)
        assert view.width == 5
        assert view.height == 4


# -- CellWrite dataclass ---------------------------------------------------


class TestCellWrite:
    def test_cellwrite_fields(self):
        cw = CellWrite(x=1, y=2, cell=Cell("A", S))
        assert cw.x == 1
        assert cw.y == 2
        assert cw.cell == Cell("A", S)
