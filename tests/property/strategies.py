"""Shared Hypothesis strategies for painted's property tier.

Two cornerstones, both load-bearing — see the invariant-audit arc:

`mixed_printable` / `text_st()` — an alphabet that is *heavily non-ASCII* so the
width-aware slow paths actually run. Pure-ASCII text never reaches the wide-char
or combining-mark logic (those paths are gated on ``text.isascii()``), so a
default ``st.text()`` would silently skip the very code these properties guard.

The alphabet deliberately spans every display-width regime painted handles:
ASCII (width 1) · width-1 non-ASCII (em-dash, arrow) · wide CJK/emoji (width 2,
stored as lead cell + space placeholder) · combining marks (width 0, *dropped*
when building cells).

It deliberately EXCLUDES the zero-width joiner (U+200D). Empirically, this
``wcwidth`` build applies an emoji-ZWJ-join heuristic: ``wcswidth("x‍y")``
returns 1, while painted drops the ZWJ and keeps x and y as two cells. That makes
``len(cells) == display_width`` *falsely* fail — but the divergence is a wcswidth
quirk, not a painted invariant. Excluding ZWJ keeps the alphabet in the regime
where ``display_width(s) == sum(char_width(c) for c in s)``.

`no_id_blocks()` — Blocks with NO ``id`` and NO ``ids``. This is what forces the
compose ops (join/pad/border) onto their ``Block._create`` fast path, which SKIPS
the constructor's row-width validation. A "every row has block.width cells"
assertion only has teeth there; on the slow-constructor (ids-present) path a
ragged-row bug raises ValueError inside the op instead.
"""

from __future__ import annotations

from hypothesis import strategies as st

from painted import Block, Style, Wrap
from painted.core._text_width import char_width
from painted.core.cell import Cell

# ASCII + width-1 non-ASCII + wide CJK + wide emoji + combining marks (NO ZWJ).
_ASCII = "ab Z9.#"
_NARROW_NONASCII = "—→±"  # — → ±
_WIDE = "世界日本\U0001f600\U0001f389"  # 世 界 日 本 😀 🎉
_COMBINING = "́̈"  # combining acute, combining diaeresis
MIXED_ALPHABET = _ASCII + _NARROW_NONASCII + _WIDE + _COMBINING

# Wide-heavy alphabet: forces 2-column chars against small width boundaries.
WIDE_ALPHABET = "ab世界\U0001f600"  # a b 世 界 😀


def text_st(*, max_size: int = 30) -> st.SearchStrategy[str]:
    """Text drawn from the mixed (heavily non-ASCII) alphabet."""
    return st.text(alphabet=MIXED_ALPHABET, max_size=max_size)


def wide_text_st(*, max_size: int = 30) -> st.SearchStrategy[str]:
    """Text biased toward wide chars, to stress small-width boundaries."""
    return st.text(alphabet=WIDE_ALPHABET, max_size=max_size)


def word_text_st(*, max_words: int = 6, max_word: int = 8) -> st.SearchStrategy[str]:
    """Space-separated words for exercising Wrap.WORD."""
    return st.lists(
        st.text(alphabet=MIXED_ALPHABET, min_size=1, max_size=max_word),
        min_size=1,
        max_size=max_words,
    ).map(" ".join)


def styles() -> st.SearchStrategy[Style]:
    """Small but varied Style space (color + a couple of attribute flags)."""
    return st.builds(
        Style,
        fg=st.sampled_from([None, "red", "green", "blue"]),
        bold=st.booleans(),
        italic=st.booleans(),
    )


@st.composite
def no_id_blocks(
    draw: st.DrawFn,
    *,
    min_w: int = 1,
    max_w: int = 20,
    max_h: int = 6,
) -> Block:
    """A Block with no id/ids, built so compose ops take the _create fast path.

    Stacks single-row ``Block.text`` blocks (all the same width, no id) with
    ``join_vertical`` — itself a no-id _create path — yielding a multi-row block
    of known width whose rows carry real wide-char content.
    """
    from painted.core.compose import join_vertical

    w = draw(st.integers(min_value=min_w, max_value=max_w))
    n = draw(st.integers(min_value=1, max_value=max_h))
    style = draw(styles())
    lines = draw(st.lists(text_st(max_size=max_w + 4), min_size=n, max_size=n))
    parts = [Block.text(line, style, width=w, wrap=Wrap.NONE) for line in lines]
    block = join_vertical(*parts)
    assert block.id is None and block._ids is None  # invariant of this strategy
    return block


def has_orphan_wide(row: tuple[Cell, ...]) -> bool:
    """True if any wide (2-column) cell lacks a following placeholder in the row.

    The cell-buffer model stores a display-width-2 glyph as the lead cell plus a
    trailing space placeholder. A truncation/composition bug that cuts between
    them leaves an "orphan" wide lead — which `iter_row_spans` cannot pair, so
    the glyph mis-renders. This is the wide-char-safety invariant the public
    constructor does NOT check.
    """
    for i, cell in enumerate(row):
        if char_width(cell.char) == 2:
            if i + 1 >= len(row) or row[i + 1].char != " ":
                return True
    return False
