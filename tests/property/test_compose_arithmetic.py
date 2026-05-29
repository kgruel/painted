"""Property tier — composition arithmetic and fast-path rectangularity.

This is the highest-value file. join_horizontal / join_vertical / pad / border
take `Block._create` on their no-ids fast paths, BYPASSING the constructor's
row-width validation. A compose arithmetic bug (off-by-one gap, wrong align
offset, title overrun) produces a ragged block the slow constructor would have
rejected — so re-checking "every row has block.width cells" on the _create
output catches exactly those bugs. The strategies generate NO-ID blocks to stay
on that fast path (an id/ids on any input flips the op to the slow constructor).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted import Align
from painted.core.compose import (
    border,
    join_horizontal,
    join_responsive,
    join_vertical,
    pad,
    truncate,
    vslice,
)

from tests.property.strategies import (
    has_orphan_wide,
    no_id_blocks,
    styles,
    text_st,
)


def _rectangular(block) -> bool:
    return all(len(block.row(y)) == block.width for y in range(block.height))


@given(
    blocks=st.lists(no_id_blocks(), min_size=1, max_size=5),
    gap=st.integers(min_value=0, max_value=3),
    align=st.sampled_from(list(Align)),
)
def test_join_horizontal_dimensions_and_rectangular(blocks, gap: int, align: Align) -> None:
    r = join_horizontal(*blocks, gap=gap, align=align)
    assert r.width == sum(b.width for b in blocks) + gap * (len(blocks) - 1)
    assert r.height == max(b.height for b in blocks)
    assert _rectangular(r)


@given(
    blocks=st.lists(no_id_blocks(), min_size=1, max_size=5),
    gap=st.integers(min_value=0, max_value=3),
    align=st.sampled_from(list(Align)),
)
def test_join_vertical_dimensions_and_rectangular(blocks, gap: int, align: Align) -> None:
    r = join_vertical(*blocks, gap=gap, align=align)
    assert r.width == max(b.width for b in blocks)
    assert r.height == sum(b.height for b in blocks) + gap * (len(blocks) - 1)
    assert _rectangular(r)


@given(
    block=no_id_blocks(),
    left=st.integers(min_value=0, max_value=5),
    right=st.integers(min_value=0, max_value=5),
    top=st.integers(min_value=0, max_value=5),
    bottom=st.integers(min_value=0, max_value=5),
    style=styles(),
)
def test_pad_dimensions_and_rectangular(block, left, right, top, bottom, style) -> None:
    r = pad(block, left=left, right=right, top=top, bottom=bottom, style=style)
    assert r.width == block.width + left + right
    assert r.height == block.height + top + bottom
    assert _rectangular(r)


@given(
    block=no_id_blocks(min_w=1),
    title=st.one_of(st.none(), text_st(max_size=20)),
    use_title_style=st.booleans(),
)
def test_border_dimensions_and_rectangular_with_titles(block, title, use_title_style) -> None:
    from painted import Style

    r = border(block, title=title, title_style=(Style(bold=True) if use_title_style else None))
    assert r.width == block.width + 2
    assert r.height == block.height + 2
    assert _rectangular(r)
    for y in range(r.height):
        assert not has_orphan_wide(r.row(y))


@given(
    block=no_id_blocks(min_w=2),
    w=st.integers(min_value=0, max_value=40),
    ell=st.sampled_from(["…", "..", "世"]),
)
def test_truncate_rectangular_no_wide_split(block, w: int, ell: str) -> None:
    r = truncate(block, w, ellipsis=ell)
    if w >= block.width:
        assert r is block
        return
    assert r.width == w
    assert r.height == block.height
    assert _rectangular(r)
    for y in range(r.height):
        assert not has_orphan_wide(r.row(y))


@given(
    blocks=st.lists(no_id_blocks(), min_size=2, max_size=5),
    gap=st.integers(min_value=1, max_value=3),
)
def test_gap_inserted_between_not_after(blocks, gap: int) -> None:
    n = len(blocks)
    assert join_horizontal(*blocks, gap=gap).width == sum(b.width for b in blocks) + gap * (n - 1)
    assert join_vertical(*blocks, gap=gap).height == sum(b.height for b in blocks) + gap * (n - 1)


@given(
    block=no_id_blocks(),
    offset=st.integers(min_value=-5, max_value=30),
    height=st.integers(min_value=0, max_value=30),
)
def test_vslice_dimensions_clamped(block, offset: int, height: int) -> None:
    r = vslice(block, offset, height)
    assert r.width == block.width
    clamped = max(0, min(offset, block.height))
    end = min(clamped + height, block.height)
    assert r.height == max(0, end - clamped)
    assert _rectangular(r)


@given(
    blocks=st.lists(no_id_blocks(), min_size=1, max_size=4),
    aw=st.integers(min_value=1, max_value=80),
    gap=st.integers(min_value=0, max_value=2),
)
def test_join_responsive_matches_chosen_mode(blocks, aw: int, gap: int) -> None:
    total = sum(b.width for b in blocks) + gap * (len(blocks) - 1)
    r = join_responsive(*blocks, available_width=aw, gap=gap)
    expected = join_horizontal(*blocks, gap=gap) if total <= aw else join_vertical(*blocks, gap=gap)
    assert (r.width, r.height) == (expected.width, expected.height)
    assert _rectangular(r)
