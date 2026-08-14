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

It deliberately INCLUDES the zero-width joiner (U+200D). This alphabet once
excluded it because ``display_width`` used sequence-aware ``wcswidth``, whose
emoji-ZWJ-join heuristic measured "x\\u200dy" as one glyph while painted keeps
x and y as two cells — making ``len(cells) == display_width`` falsely fail.
The wrap-engine-unification arc inverted that: ``display_width`` now measures
in the cell model (per-char, summed), the exact divergence that once forced
the exclusion is the P1 bug class these laws exist to catch (a sequence-aware
measure under-counting the per-char grid crashed the wrap engine on ZWJ
emoji), so the joiner is load-bearing here, not a quirk to dodge.

`no_ref_blocks()` — Blocks with NO ``ref`` and NO ``refs``. This is what forces the
compose ops (join/pad/border) onto their ``Block._create`` fast path, which SKIPS
the constructor's row-width validation. A "every row has block.width cells"
assertion only has teeth there; on the slow-constructor (refs-present) path a
ragged-row bug raises ValueError inside the op instead.
"""

from __future__ import annotations

from hypothesis import strategies as st

from painted import Block, Style, Wrap
from painted.core._text_width import char_width
from painted.core.cell import Cell

# ASCII + width-1 non-ASCII + wide CJK + wide emoji + combining marks + ZWJ.
_ASCII = "ab Z9.#"
_NARROW_NONASCII = "—→±"  # — → ±
_WIDE = "世界日本\U0001f600\U0001f389"  # 世 界 日 本 😀 🎉
_COMBINING = "́̈"  # combining acute, combining diaeresis
_JOINER = "‍"  # ZWJ — zero-width, splices emoji into clusters
MIXED_ALPHABET = _ASCII + _NARROW_NONASCII + _WIDE + _COMBINING + _JOINER

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
def no_ref_blocks(
    draw: st.DrawFn,
    *,
    min_w: int = 1,
    max_w: int = 20,
    max_h: int = 6,
) -> Block:
    """A Block with no ref/refs, built so compose ops take the _create fast path.

    Stacks single-row ``Block.text`` blocks (all the same width, no ref) with
    ``join_vertical`` — itself a no-ref _create path — yielding a multi-row block
    of known width whose rows carry real wide-char content.
    """
    from painted.core.compose import join_vertical

    w = draw(st.integers(min_value=min_w, max_value=max_w))
    n = draw(st.integers(min_value=1, max_value=max_h))
    style = draw(styles())
    lines = draw(st.lists(text_st(max_size=max_w + 4), min_size=n, max_size=n))
    parts = [Block.text(line, style, width=w, wrap=Wrap.NONE) for line in lines]
    block = join_vertical(*parts)
    assert block.ref is None and block._refs is None  # invariant of this strategy
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
