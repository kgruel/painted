"""Host viewport adapter laws — the omitted arm over all inputs (HOST_RUNG §6).

The unit tests pin named branches; these pin invariants over *any* content,
frame height ``F ≥ 0``, offset, and ref layout — and, per the review (P3b), pin
**observables** (what a caller sees in the frame / the return value) rather than
re-deriving the adapter's internal scan/clamp:

  * frame exactness — the frame is exactly ``F`` rows of the content's width;
  * re-slice reuse — a height-only re-slice reuses the cached Block and the top
    visible row is the numerically clamped offset (read off the rendered frame);
  * intent survival — a following view stays at the bottom; a cursor stays
    visible — across arbitrary growth and resizes;
  * anchor observable — when a ref in the old window carries into the new Block,
    a carried ref is *visible on screen* after re-render (not an offset formula);
  * ticketed publication — forked and out-of-order publishes are rejected;
  * frame-token staleness — a mapping change (a scroll) makes the old token stale.
"""

from __future__ import annotations

from collections.abc import Sequence

from hypothesis import given
from hypothesis import strategies as st

from painted.core.block import Block
from painted.core.cell import Style
from painted.core.compose import join_vertical
from painted.host import RenderKey, ViewportAdapter

_KEY = RenderKey("doc", "v1", 10)


def _row_char(i: int) -> str:
    return chr(ord("A") + (i % 26))


def _content(n: int, width: int = 6) -> Block:
    """``n`` content rows, each a distinct repeated char (row identity)."""
    if n == 0:
        return Block.empty(width, 0)
    return Block.column([(_row_char(i) * width, Style()) for i in range(n)], width=width)


def _from_refs(refs: Sequence[str | None], width: int = 6) -> Block:
    if not refs:
        return Block.empty(width, 0)
    return join_vertical(*(Block.text("r" * width, Style(), width=width, ref=r) for r in refs))


def _publish(a: ViewportAdapter, block: Block, key: RenderKey, **kw) -> ViewportAdapter:
    result = a.publish(block, a.plan(key), **kw)
    assert result is not None
    return result


def _capacity(f: int, h: int) -> int:
    if f <= 0:
        return 0
    return f if h <= f else f - 1


def _top_visible_row(frame_block: Block, content: Block) -> int | None:
    """The content-row index shown at the top of the frame, by row identity."""
    if frame_block.height == 0 or content.height == 0:
        return None
    top_char = frame_block.row(0)[0].char
    for i in range(content.height):
        if content.row(i)[0].char == top_char:
            return i
    return None


def _refs_in_frame(frame_block: Block) -> set[str]:
    seen: set[str] = set()
    for y in range(frame_block.height):
        for x in range(frame_block.width):
            r = frame_block.cell_ref(x, y)
            if r is not None:
                seen.add(r)
    return seen


heights = st.integers(min_value=0, max_value=40)
frames = st.integers(min_value=0, max_value=40)
offsets = st.integers(min_value=-5, max_value=60)


class TestFrameExactness:
    @given(h=heights, f=frames, off=offsets)
    def test_frame_is_exactly_f_rows(self, h, f, off):
        content = _content(h)
        a = _publish(ViewportAdapter(frame_height=f), content, _KEY).scroll_to(off)
        block = a.frame().block
        assert block.height == f
        assert block.width == content.width


class TestReSliceReuse:
    @given(h=st.integers(min_value=1, max_value=40), f0=frames, f1=frames, off=offsets)
    def test_reslice_reuses_block_and_clamps_offset(self, h, f0, f1, off):
        """Height-only re-slice reuses the cached Block; for a plain top-anchored
        view the top visible row is the numerically clamped offset — read off the
        rendered frame, not recomputed from the adapter."""
        content = _content(h)
        a = _publish(ViewportAdapter(frame_height=f0), content, _KEY).scroll_to(off)
        pre_offset = a.viewport.offset

        resliced = a.resize(f1)
        assert resliced.content is content  # renderer not called (always)

        # The numeric-clamp branch applies only when not following (scroll_to may
        # have landed at the bottom, engaging follow — a different, tested branch).
        if not a.following and _capacity(f1, h) >= 1:
            top = _top_visible_row(resliced.frame().block, content)
            new_max = max(0, h - _capacity(f1, h))
            assert top == max(0, min(pre_offset, new_max))


class TestIntentSurvival:
    @given(
        h0=st.integers(min_value=1, max_value=30),
        f=st.integers(min_value=1, max_value=20),
        grow=st.integers(min_value=0, max_value=30),
        f2=st.integers(min_value=1, max_value=20),
    )
    def test_at_bottom_stays_at_bottom(self, h0, f, grow, f2):
        a = _publish(ViewportAdapter(frame_height=f), _content(h0), _KEY).end()
        assert a.viewport.is_at_bottom
        grown = _publish(a, _content(h0 + grow), _KEY)
        assert grown.following and grown.viewport.is_at_bottom
        resized = grown.resize(f2)
        assert resized.following and resized.viewport.is_at_bottom
        total = h0 + grow
        cap = _capacity(f2, total)
        if total > f2 and cap >= 1:  # overflow: bottom content row is the last row
            assert resized.frame().block.row(cap - 1)[0].char == _row_char(total - 1)

    @given(
        h=st.integers(min_value=1, max_value=30),
        f=st.integers(min_value=1, max_value=15),
        idx=st.integers(min_value=0, max_value=29),
        f2=st.integers(min_value=1, max_value=15),
    )
    def test_cursor_stays_visible(self, h, f, idx, f2):
        """A retained cursor is visible in the frame across a resize (P2a)."""
        cursor = min(idx, h - 1)
        a = _publish(ViewportAdapter(frame_height=f), _content(h), _KEY).scroll_into_view(cursor)
        resized = a.resize(f2)
        assert resized.cursor == cursor
        if _capacity(f2, h) >= 1:
            vis = {resized.frame().block.row(y)[0].char for y in range(_capacity(f2, h))}
            assert _row_char(cursor) in vis


# --- Anchor precedence, pinned observably ------------------------------------
#
# These build a genuinely non-following, overflowing old view (offset strictly
# below the bottom) so the ref / numeric / reset branches — not follow — are
# exercised, without filtering examples away.


@st.composite
def _overflow_case(draw):
    """(frame height, old content height, mid-scroll offset) — overflow, not at
    the bottom, so the view is not following."""
    f = draw(st.integers(min_value=2, max_value=6))
    old_n = draw(st.integers(min_value=f + 2, max_value=15))  # overflow guaranteed
    max_off = old_n - (f - 1)  # capacity is f-1 on overflow
    off = draw(st.integers(min_value=0, max_value=max_off - 1))  # strictly above bottom
    return f, old_n, off


class TestAnchorObservables:
    @given(case=_overflow_case(), data=st.data())
    def test_carried_ref_stays_on_screen(self, case, data):
        """When a ref visible in the old window also exists in the new Block, a
        carried ref is visible on screen after re-render — the observable of
        "a semantic ref re-anchors the view", not the offset formula. All rows
        carry a ref and the new Block is a permutation, so a carry always exists
        (a mix of scheme-ful and scheme-less refs — both anchor, P2b)."""
        f, old_n, off = case
        refs = [(f"fact:{i}" if i % 2 else f"plain{i}") for i in range(old_n)]
        old = _from_refs(refs)
        new = _from_refs(list(data.draw(st.permutations(refs))))  # same set, reflowed
        a = _publish(ViewportAdapter(frame_height=f), old, _KEY).scroll_to(off)
        assert not a.following  # construction guarantees this

        window = range(a.viewport.offset, a.viewport.offset + a.viewport.visible)
        carried = {refs[y] for y in window}
        out = _publish(a, new, RenderKey("doc", "v1", 99))  # width change → re-render
        assert _refs_in_frame(out.frame().block) & carried  # a carried ref stayed visible

    @given(case=_overflow_case(), new_h=st.integers(min_value=1, max_value=20))
    def test_no_carried_ref_holds_numeric(self, case, new_h):
        """No ref carries over and same identity ⇒ the numeric offset holds,
        clamped (top visible row read off the frame, not recomputed internally)."""
        f, old_n, off = case
        old = _content(old_n)  # distinct chars, NO refs → nothing carries
        new = _content(new_h)
        a = _publish(ViewportAdapter(frame_height=f), old, _KEY).scroll_to(off)
        assert not a.following

        out = _publish(a, new, RenderKey("doc", "v1", 99))
        top = _top_visible_row(out.frame().block, new)
        if _capacity(f, new_h) >= 1:
            new_max = max(0, new_h - _capacity(f, new_h))
            assert top == max(0, min(off, new_max))  # numeric hold, not a reset

    @given(case=_overflow_case(), new_h=st.integers(min_value=1, max_value=20))
    def test_new_identity_resets_to_top(self, case, new_h):
        f, old_n, off = case
        a = _publish(ViewportAdapter(frame_height=f), _content(old_n), _KEY).scroll_to(off)
        assert not a.following
        out = _publish(a, _content(new_h), RenderKey("other", "v1", 10))  # new id, no refs
        assert out.viewport.offset == 0

    @given(
        follow_h=st.integers(min_value=1, max_value=20), f=st.integers(min_value=1, max_value=10)
    )
    def test_follow_dominates(self, follow_h, f):
        a = _publish(ViewportAdapter(frame_height=f), _content(10), _KEY).end()
        out = _publish(a, _from_refs([f"fact:{i}" for i in range(follow_h)]), _KEY)
        assert out.viewport.is_at_bottom  # follow beats any ref


# --- Ticketed publication + token staleness (P1a/P1b) ------------------------


class TestPublicationTickets:
    @given(
        h0=st.integers(min_value=1, max_value=20),
        ha=st.integers(min_value=1, max_value=20),
        hb=st.integers(min_value=1, max_value=20),
        f=st.integers(min_value=1, max_value=15),
    )
    def test_pure_fork_tokens_do_not_cross_resolve(self, h0, ha, hb, f):
        """Two plans from the SAME frozen base, both published *from that base*, are
        both accepted (they share a ticket base) — yet each branch's token resolves
        only against its own state; against the sibling it is stale. A counter
        identity would give equal-geometry branches the same token and let A's
        token resolve against B's content — this is the collision that fix closes."""
        base = _publish(ViewportAdapter(frame_height=f), _content(h0), _KEY)
        plan_a = base.plan(RenderKey("doc", "vA", 10))
        plan_b = base.plan(RenderKey("doc", "vB", 10))
        a = base.publish(_content(ha), plan_a)
        b = base.publish(_content(hb), plan_b)
        assert a is not None and b is not None  # both forks accepted

        ta, tb = a.frame().token, b.frame().token
        # Own token resolves; sibling's token is stale (dropped), never cross-resolved.
        assert not a.resolve(0, 0, ta).stale
        assert not b.resolve(0, 0, tb).stale
        assert a.resolve(0, 0, tb).stale
        assert b.resolve(0, 0, ta).stale

    @given(
        h0=st.integers(min_value=1, max_value=20),
        hnew=st.integers(min_value=1, max_value=20),
        hstale=st.integers(min_value=1, max_value=20),
    )
    def test_out_of_order_publish_is_rejected(self, h0, hnew, hstale):
        a1 = _publish(ViewportAdapter(frame_height=5), _content(h0), RenderKey("d", "v1", 10))
        stale_plan = a1.plan(RenderKey("d", "v2", 10))  # base = gen 0
        newer = _publish(a1, _content(hnew), RenderKey("d", "v3", 10))  # → gen 1
        assert newer.publish(_content(hstale), stale_plan) is None
        assert newer.content is not None and newer.content.height == hnew  # untouched

    @given(
        h=st.integers(min_value=2, max_value=40),
        f=st.integers(min_value=1, max_value=20),
        delta=st.integers(min_value=-30, max_value=30),
    )
    def test_scroll_makes_prior_token_stale(self, h, f, delta):
        a = _publish(ViewportAdapter(frame_height=f), _content(h), _KEY)
        old = a.frame()
        scrolled = a.scroll(delta)
        if scrolled.viewport.offset != a.viewport.offset:  # the mapping actually changed
            assert scrolled.resolve(0, 0, old.token).stale
        # A state always resolves its own current token without staleness.
        assert not scrolled.resolve(0, 0, scrolled.frame().token).stale
        # The frozen state that produced ``old`` still resolves it.
        assert not a.resolve(0, 0, old.token).stale
