"""Wide-character display-width correctness tests.

These tests assert that display-critical code paths use wcwidth/wcswidth
semantics (terminal columns), not code-point counts.
"""

from __future__ import annotations

from painted import Block, Style, Wrap, border
from painted.views import TextInputState, text_input
from painted.core._text_width import display_width
from painted.core.block import _word_wrap_runs


def _row_chars(block: Block, y: int = 0) -> list[str]:
    return [c.char for c in block.row(y)]


class TestBlockTextWide:
    def test_width_none_uses_display_width(self):
        content = "A世界B"  # widths: 1 + 4 + 1 = 6
        b = Block.text(content, Style())
        assert b.width == 6
        assert len(b.row(0)) == 6

    def test_wrap_none_truncates_by_columns(self):
        content = "A世B"  # widths: 1 + 2 + 1 = 4
        b = Block.text(content, Style(), width=3, wrap=Wrap.NONE)
        assert b.width == 3
        assert b.height == 1
        assert _row_chars(b)[:2] == ["A", "世"]

    def test_wrap_ellipsis_truncates_by_columns(self):
        content = "A世界B"  # width 6
        b = Block.text(content, Style(), width=4, wrap=Wrap.ELLIPSIS)
        assert b.width == 4
        row = _row_chars(b)
        assert "…" in row

    def test_wrap_char_breaks_on_wide_boundary(self):
        content = "A世B"
        b = Block.text(content, Style(), width=3, wrap=Wrap.CHAR)
        assert b.width == 3
        assert b.height == 2
        assert _row_chars(b, 0)[:2] == ["A", "世"]
        assert _row_chars(b, 1)[0] == "B"

    def test_wrap_word_respects_display_width(self):
        text = "hello 世界 there"
        b = Block.text(text, Style(), width=6, wrap=Wrap.WORD)
        assert b.width == 6
        assert b.height == 3


class TestWordWrapWide:
    def test_word_wrap_wide_words(self):
        lines = self._wrap("hello 世界 there", 6)
        assert lines == ["hello", "世界", "there"]
        assert all(display_width(line) <= 6 for line in lines)

    def test_word_wrap_breaks_long_wide_word(self):
        lines = self._wrap("世界世界", 3)
        assert lines == ["世", "界", "世", "界"]
        assert all(display_width(line) <= 3 for line in lines)

    @staticmethod
    def _wrap(text: str, width: int) -> list[str]:
        runs: list[tuple[str, Style, str | None]] = [(text, Style(), None)]
        return ["".join(t for t, _s, _r in line) for line in _word_wrap_runs(runs, width)]


class TestBorderTitleWide:
    def test_title_painted_with_wide_chars(self):
        b = Block.empty(7, 1)
        framed = border(b, title="世界")
        top = _row_chars(framed, 0)
        assert top[3] == "世"
        assert top[5] == "界"

    def test_title_guard_uses_display_width(self):
        # One column short of the both-spaces full fit (title_width + 3 == 7):
        # since 0.14 S5 (law 6), border() ellipsizes rather than omitting, and
        # display_width correctly finds the title still fits without the
        # trailing chrome space — no mark, since nothing was cut.
        b = Block.empty(6, 1)
        framed = border(b, title="世界")
        top = _row_chars(framed, 0)
        assert top[3] == "世"
        assert top[5] == "界"

    def test_title_guard_fits_with_no_chrome_by_display_width(self):
        # capacity (block.width - 1 == 4) == title_width (4): the complete
        # title fits with no chrome space at all — still no mark, since
        # nothing was cut. display_width (not code-point count) drives this.
        b = Block.empty(5, 1)
        framed = border(b, title="世界")
        top = _row_chars(framed, 0)
        assert top[2] == "世"
        assert top[4] == "界"

    def test_title_guard_ellipsizes_wide_chars_by_display_width(self):
        # One column narrower still: capacity (3) < title_width (4) — the
        # title itself must be cut. truncate_ellipsis must respect the
        # 2-column char boundary rather than code-point counting.
        b = Block.empty(4, 1)
        framed = border(b, title="世界")
        top = _row_chars(framed, 0)
        assert "".join(top) == "╭─世 …╮"


class TestTextInputWide:
    def test_set_text_end_cursor_scrolls_by_columns(self):
        state = TextInputState().set_text("A世界B")
        state = state._ensure_visible(4)
        assert state.scroll_offset == 2  # start at "界"

        block = text_input(state, 4, focused=True)
        assert block.width == 4
        last = block.row(0)[-1]
        assert last.char == " "
        assert last.style.reverse is True

    def test_cursor_on_wide_char_styles_both_cells(self):
        state = TextInputState(text="A世界B", cursor=1, scroll_offset=0)
        block = text_input(state, 4, focused=True)
        row = block.row(0)
        # cursor at index 1 points at "世" (2 columns)
        assert row[1].char == "世"
        assert row[1].style.reverse is True
        assert row[2].char == " "
        assert row[2].style.reverse is True
