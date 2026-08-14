"""Property tier — wrap-engine row-count laws.

Born from the wrap-engine-unification review arc: three of its five findings
were one bug class — a wrap boundary meeting a zero-width or unrepresentable
char producing a *phantom blank row* (or, inverted, a crash when a measure
disagreed with materialization). Examples were pinned in the unit tier; these
laws pin the class.

The bounds: for newline-free content wrapped at ``width >= 1``,

- every emitted row carries at least one display column, so
  ``height <= max(1, W_repr)`` where ``W_repr`` sums the widths of chars that
  are representable at this width (``0 < char_width(ch) <= width``) — a
  phantom blank row breaks this ceiling;
- a row holds at most ``width`` columns, so ``height >= ceil(W_kept / width)``
  (with ``W_kept`` the representable width that mode never drops: everything
  for CHAR, non-space content for WORD, whose wrap points drop break spaces)
  — lost content breaks this floor.
"""

from __future__ import annotations

from math import ceil

from hypothesis import given
from hypothesis import strategies as st

from painted import Block, Line, Span, Style, Wrap
from painted.core._text_width import char_width

from tests.property.strategies import styles, text_st, wide_text_st


def _w_repr(text: str, width: int) -> int:
    """Total representable display columns at this width."""
    return sum(cw for cw in map(char_width, text) if 0 < cw <= width)


def _w_nonspace(text: str, width: int) -> int:
    """Representable columns excluding spaces (WORD may drop break spaces)."""
    return sum(cw for ch in text if ch != " " and 0 < (cw := char_width(ch)) <= width)


def _assert_bounds(block: Block, text: str, width: int, *, floor_w: int) -> None:
    assert block.width == width
    assert block.height >= max(1, ceil(floor_w / width))
    assert block.height <= max(1, _w_repr(text, width))


@given(text=text_st(), width=st.integers(min_value=1, max_value=7), style=styles())
def test_char_wrap_row_count_bounds(text: str, width: int, style: Style) -> None:
    block = Block.text(text, style, width=width, wrap=Wrap.CHAR)
    _assert_bounds(block, text, width, floor_w=_w_repr(text, width))


@given(text=text_st(), width=st.integers(min_value=1, max_value=7), style=styles())
def test_word_wrap_row_count_bounds(text: str, width: int, style: Style) -> None:
    block = Block.text(text, style, width=width, wrap=Wrap.WORD)
    _assert_bounds(block, text, width, floor_w=_w_nonspace(text, width))


@given(text=wide_text_st(), width=st.integers(min_value=1, max_value=3), style=styles())
def test_char_wrap_row_count_bounds_wide_stress(text: str, width: int, style: Style) -> None:
    block = Block.text(text, style, width=width, wrap=Wrap.CHAR)
    _assert_bounds(block, text, width, floor_w=_w_repr(text, width))


@given(
    texts=st.lists(text_st(max_size=10), min_size=1, max_size=4),
    width=st.integers(min_value=1, max_value=7),
    style=styles(),
)
def test_styled_char_wrap_row_count_bounds(texts: list[str], width: int, style: Style) -> None:
    """The same ceiling holds one rung up in style richness — a Line of spans."""
    line = Line(tuple(Span(t, style if i % 2 else Style()) for i, t in enumerate(texts)))
    block = line.wrap(width, wrap=Wrap.CHAR)
    joined = "".join(texts)
    _assert_bounds(block, joined, width, floor_w=_w_repr(joined, width))
