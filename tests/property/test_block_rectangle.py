"""Property tier — the Block rectangle contract and wide-char safety.

The Block contract is "every row has exactly block.width cells". The SLOW
constructor enforces it; the FAST `Block._create` bypasses it. `Block.text`'s
Wrap.NONE / Wrap.ELLIPSIS / width=None paths go through `_create`, so a
rectangularity assertion there has real teeth. On the slow-constructor paths
(Wrap.CHAR / Wrap.WORD / Block.column) rectangularity is constructor-guaranteed,
so the law WITH teeth is "no orphaned wide char" — which the constructor does
NOT check.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted import Block, Wrap
from painted.core._row_ops import row_visible_text
from painted.core._text_width import display_width

from tests.property.strategies import (
    has_orphan_wide,
    styles,
    text_st,
    wide_text_st,
    word_text_st,
)


@given(text=text_st(), style=styles())
def test_text_no_width_cellcount_equals_display_width(text: str, style) -> None:
    """Block.text(text, style) (width=None): a 1-row block sized to display width."""
    b = Block.text(text, style)
    assert b.height == 1
    assert b.width == display_width(text)
    assert len(b.row(0)) == b.width


@given(text=text_st(max_size=30), w=st.integers(min_value=1, max_value=40), style=styles())
def test_text_wrap_none_is_rectangular_and_fits(text: str, w: int, style) -> None:
    """Wrap.NONE (via _create): exactly w cells, one row, no orphaned wide char."""
    b = Block.text(text, style, width=w, wrap=Wrap.NONE)
    assert b.height == 1
    assert b.width == w
    assert len(b.row(0)) == w
    assert not has_orphan_wide(b.row(0))


@given(text=text_st(max_size=40), w=st.integers(min_value=1, max_value=30), style=styles())
def test_text_wrap_ellipsis_is_rectangular_and_bounded(text: str, w: int, style) -> None:
    """Wrap.ELLIPSIS (via _create): rectangular, visible width <= w, ellipsis when cut."""
    b = Block.text(text, style, width=w, wrap=Wrap.ELLIPSIS)
    assert b.height == 1
    assert b.width == w
    assert len(b.row(0)) == w
    assert not has_orphan_wide(b.row(0))
    assert display_width(row_visible_text(b.row(0))) <= w
    if display_width(text) > w:
        assert any(c.char == "…" for c in b.row(0))


@given(text=wide_text_st(max_size=30), w=st.integers(min_value=1, max_value=10), style=styles())
def test_text_wrap_char_no_orphaned_wide_char(text: str, w: int, style) -> None:
    """Wrap.CHAR never splits a wide char across rows (slow ctor => rows_ok is free)."""
    b = Block.text(text, style, width=w, wrap=Wrap.CHAR)
    assert b.width == w
    for y in range(b.height):
        assert not has_orphan_wide(b.row(y))


@given(text=word_text_st(), w=st.integers(min_value=3, max_value=20), style=styles())
def test_text_wrap_word_rows_fit_width(text: str, w: int, style) -> None:
    """Wrap.WORD: every row fits w columns and splits no wide char."""
    b = Block.text(text, style, width=w, wrap=Wrap.WORD)
    for y in range(b.height):
        assert not has_orphan_wide(b.row(y))
        assert display_width(row_visible_text(b.row(y))) <= w


@given(rows=st.lists(st.tuples(text_st(max_size=12), styles()), min_size=1, max_size=6))
def test_column_rectangular_and_inferred_width(rows) -> None:
    """Block.column: height == len(rows), width == max label display width, rows fit."""
    b = Block.column(rows)
    assert b.height == len(rows)
    assert b.width == max(display_width(text) for text, _ in rows)
    for y in range(b.height):
        assert len(b.row(y)) == b.width
        assert not has_orphan_wide(b.row(y))
