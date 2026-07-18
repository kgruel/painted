"""Unit tests for the host viewport adapter (HOST_RUNG_DESIGN §6).

The named branches of the omitted-arm adapter: ticketed atomic publication
(forked / out-of-order rejection), each resize-matrix decision, the intent set
(follow / cursor / top-anchored) captured before geometry, each anchor-policy
fallback, frame identity (Block + token), and coordinate resolution per region
including a stale-token drop and the width bound on every region. Invariants
that must hold for *any* input live in ``tests/property/test_host_adapter.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from painted.core.block import Block
from painted.core.cell import Style
from painted.core.compose import join_vertical
from painted.core.errors import ContractError
from painted.host import (
    Frame,
    FrameRegion,
    Plan,
    RenderAction,
    RenderKey,
    ViewportAdapter,
)
from tests.helpers import row_text


def _rows(n: int, width: int = 24, ref_prefix: str | None = None) -> Block:
    """``n`` distinct content rows; each carries a ref if ``ref_prefix`` is set."""
    blocks = [
        Block.text(
            f"row{i}",
            Style(),
            width=width,
            ref=None if ref_prefix is None else f"{ref_prefix}:{i}",
        )
        for i in range(n)
    ]
    return join_vertical(*blocks)


def _from_refs(refs: Sequence[str | None], width: int = 8) -> Block:
    """A content Block whose row ``y`` carries ``refs[y]`` uniformly."""
    return join_vertical(*(Block.text("r" * width, Style(), width=width, ref=r) for r in refs))


def _publish(adapter: ViewportAdapter, block: Block, key: RenderKey, **kw) -> ViewportAdapter:
    """Plan + publish, asserting the ticket was accepted (the happy path)."""
    result = adapter.publish(block, adapter.plan(key), **kw)
    assert result is not None
    return result


def _gid(adapter: ViewportAdapter) -> object:
    """The current generation *identity*, observed through the public frame token."""
    return adapter.frame().token.generation


# --- Ticketed atomic publication (deliverables 1, P1b) -----------------------


class TestTicketedPublication:
    def test_publish_couples_block_with_its_key(self) -> None:
        block = _rows(3)
        key = RenderKey("doc", ("fidelity", 1), 10)
        a = _publish(ViewportAdapter(frame_height=5), block, key)
        assert a.content is block
        assert a.generation is not None and a.generation.key == key

    def test_first_publish_needs_a_null_base_ticket(self) -> None:
        a = ViewportAdapter(frame_height=5)
        plan = a.plan(RenderKey("doc", "v1", 10))
        assert plan.base is None  # no prior generation
        assert a.publish(_rows(3), plan) is not None

    def test_out_of_order_publish_is_rejected(self) -> None:
        """A plan whose base generation has been advanced past (a newer publish
        already landed) is rejected — a returned ``None``, not blessed with a
        later sequence."""
        a1 = _publish(ViewportAdapter(frame_height=5), _rows(3), RenderKey("doc", "v1", 10))
        stale_plan = a1.plan(RenderKey("doc", "v2", 20))  # base = gen 0
        newer = _publish(a1, _rows(9, width=20), RenderKey("doc", "v3", 20))  # advances gen 0
        assert newer.publish(_rows(4), stale_plan) is None
        # The newer state is untouched by the rejected publish.
        assert newer.content is not None and newer.content.height == 9

    def test_pure_fork_tokens_do_not_cross_resolve(self) -> None:
        """Two plans from the SAME frozen base, both published from that base, are
        both accepted (same ticket base) — but their generation identities differ,
        so a token from one branch is stale against the other, never a false
        content hit (the collision a counter identity would produce)."""
        base = _publish(ViewportAdapter(frame_height=5), _rows(10), RenderKey("doc", "v1", 10))
        plan_a = base.plan(RenderKey("doc", "vA", 10))
        plan_b = base.plan(RenderKey("doc", "vB", 10))
        # Distinct content per branch: a cross-resolve would surface the wrong ref.
        a = base.publish(_rows(10, ref_prefix="A"), plan_a)
        b = base.publish(_rows(10, ref_prefix="B"), plan_b)
        assert a is not None and b is not None

        ta, tb = a.frame().token, b.frame().token
        assert ta != tb  # distinct generation identities → distinct tokens
        assert _gid(a) is not _gid(b)
        # Each branch resolves only its own token…
        assert not a.resolve(0, 0, ta).stale
        assert not b.resolve(0, 0, tb).stale
        # …and the sibling's token is stale (dropped), not a wrong content hit.
        assert b.resolve(0, 0, ta).stale
        assert a.resolve(0, 0, tb).stale

    def test_generation_identity_provenance(self) -> None:
        """The generation identity changes on an accepted publish and is preserved
        across a re-slice and a scroll (same cached Block)."""
        a = _publish(ViewportAdapter(frame_height=5), _rows(3), RenderKey("d", "v1", 10))
        g0 = _gid(a)
        a = _publish(a, _rows(3), RenderKey("d", "v2", 10))
        g1 = _gid(a)
        assert g1 is not g0  # a new generation is a new identity
        assert a.generation is not None and a.generation.seq == 1  # seq still orders
        assert _gid(a.resize(4)) is g1  # re-slice keeps the identity
        assert _gid(a.scroll(1)) is g1  # scroll keeps the identity


# --- The resize matrix (deliverable 2) ---------------------------------------


class TestResizeMatrix:
    def _base(self) -> ViewportAdapter:
        return _publish(ViewportAdapter(frame_height=5), _rows(10), RenderKey("doc", "v1", 10))

    def test_width_change_is_re_render(self) -> None:
        assert self._base().plan(RenderKey("doc", "v1", 20)).action is RenderAction.RE_RENDER

    def test_input_change_is_re_render(self) -> None:
        assert self._base().plan(RenderKey("doc", "v2", 10)).action is RenderAction.RE_RENDER

    def test_content_identity_change_is_re_render(self) -> None:
        assert self._base().plan(RenderKey("doc2", "v1", 10)).action is RenderAction.RE_RENDER

    def test_height_only_is_re_slice(self) -> None:
        assert self._base().plan(RenderKey("doc", "v1", 10)).action is RenderAction.RE_SLICE

    def test_no_prior_frame_is_re_render(self) -> None:
        assert ViewportAdapter().plan(RenderKey("doc", "v1", 10)).action is RenderAction.RE_RENDER

    def test_re_slice_reuses_the_cached_block(self) -> None:
        a = self._base()
        resliced = a.resize(3)
        assert resliced.content is a.content  # renderer not called
        assert resliced.frame_height == 3

    def test_any_height_change_recomposes_the_frame(self) -> None:
        a = self._base()  # 10 rows, F=5 → 4 shown + evidence "6 more rows"
        assert a.frame().block.height == 5
        assert "6 more rows" in row_text(a.frame().block, 4)
        smaller = a.resize(3)  # F=3 → 2 shown + evidence "8 more rows"
        assert smaller.frame().block.height == 3
        assert "8 more rows" in row_text(smaller.frame().block, 2)


# --- Intent, then geometry (deliverables 3, P2a) -----------------------------


class TestIntentThenGeometry:
    def test_at_bottom_survives_content_growth(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(10), RenderKey("d", "v1", 10)).end()
        assert a.following and a.viewport.is_at_bottom
        grown = _publish(a, _rows(40), RenderKey("d", "v2", 10))  # same identity, taller
        assert grown.following and grown.viewport.is_at_bottom
        assert "row39" in row_text(grown.frame().block, 3)

    def test_at_bottom_survives_resize(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(20), RenderKey("d", "v1", 10)).end()
        assert a.resize(8).viewport.is_at_bottom
        assert a.resize(3).viewport.is_at_bottom

    def test_cursor_stays_visible_across_growth(self) -> None:
        """scroll_into_view retains a cursor anchor reapplied across a re-render."""
        a = _publish(ViewportAdapter(frame_height=5), _rows(10), RenderKey("d", "v1", 10))
        a = a.scroll_into_view(8)
        assert a.cursor == 8 and not a.following
        grown = _publish(a, _rows(40), RenderKey("d", "v2", 10))
        assert grown.cursor == 8
        assert any("row8" in row_text(grown.frame().block, y) for y in range(grown.frame_height))

    def test_cursor_stays_visible_across_resize(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(20), RenderKey("d", "v1", 10))
        a = a.scroll_into_view(14).resize(3)
        assert a.cursor == 14
        assert any("row14" in row_text(a.frame().block, y) for y in range(a.frame_height))

    def test_manual_scroll_clears_cursor(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(20), RenderKey("d", "v1", 10))
        a = a.scroll_into_view(14)
        assert a.cursor == 14
        assert a.scroll(1).cursor is None
        assert a.page_up().cursor is None
        assert a.home().cursor is None

    def test_terminal_shrink_keeps_offset_valid(self) -> None:
        a = _publish(ViewportAdapter(frame_height=6), _rows(20), RenderKey("d", "v1", 10))
        a = a.scroll_to(5)
        assert a.viewport.offset == 5 and not a.following
        assert a.resize(4).viewport.offset == 5  # max_offset grows; 5 still valid

    def test_content_shrink_forces_clamp(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(20), RenderKey("d", "v1", 10))
        a = a.scroll_to(14)
        shrunk = _publish(a, _rows(6), RenderKey("d", "v1", 10))  # same id, numeric hold
        assert shrunk.viewport.offset == shrunk.viewport.max_offset


# --- The width-reflow anchor policy (deliverables 4, P2b) --------------------


class TestAnchorPolicy:
    def _old(self, offset: int, prefix: str = "fact") -> ViewportAdapter:
        # 10 rows, refs <prefix>:0..9, F=5 (visible 4). Offset chosen mid-scroll.
        a = _publish(
            ViewportAdapter(frame_height=5),
            _rows(10, ref_prefix=prefix),
            RenderKey("doc", "v1", 10),
        )
        return a.scroll_to(offset)

    def test_follow_beats_ref(self) -> None:
        a = self._old(0).end()
        assert a.following
        new = _from_refs([f"fact:{i}" for i in range(12)])  # fact:0 present at row 0
        out = _publish(a, new, RenderKey("doc", "v1", 10))
        assert out.viewport.is_at_bottom  # bottom, not row 0

    def test_cursor_beats_ref(self) -> None:
        """A retained cursor takes precedence over ref re-anchoring."""
        a = self._old(0).scroll_into_view(6)  # cursor 6
        new = _from_refs([("fact:0" if i == 9 else f"noise:{i}") for i in range(12)])
        out = _publish(a, new, RenderKey("doc", "v1", 20))
        # cursor 6 stays visible; the view did not jump to fact:0's row 9.
        assert any("r" in row_text(out.frame().block, y) for y in range(out.frame_height))
        assert out.cursor == 6
        assert out.viewport.offset <= 6 < out.viewport.offset + out.viewport.visible

    def test_ref_reanchors_across_reflow(self) -> None:
        a = self._old(2)  # window rows 2..5 → topmost visible ref fact:2
        assert not a.following
        new = _from_refs([("fact:2" if i == 7 else f"noise:{i}") for i in range(12)])
        out = _publish(a, new, RenderKey("doc", "v1", 20))
        assert out.viewport.offset == 7  # fact:2's new row

    def test_scheme_less_refs_are_anchors(self) -> None:
        """A scheme-less ref is a denotation annotation and a valid anchor (P2b)."""
        a = _publish(
            ViewportAdapter(frame_height=5),
            _from_refs([f"plain{i}" for i in range(10)]),  # no colons
            RenderKey("doc", "v1", 10),
        ).scroll_to(2)  # topmost visible ref "plain2"
        new = _from_refs([("plain2" if i == 6 else f"other{i}") for i in range(12)])
        out = _publish(a, new, RenderKey("doc", "v1", 20))
        assert out.viewport.offset == 6  # re-anchored on the scheme-less ref

    def test_ref_anchors_to_first_occurrence_when_repeated(self) -> None:
        a = self._old(2)
        new = _from_refs([("fact:2" if i in (3, 7) else f"noise:{i}") for i in range(12)])
        out = _publish(a, new, RenderKey("doc", "v1", 20))
        assert out.viewport.offset == 3  # first occurrence

    def test_missing_ref_falls_through_to_numeric(self) -> None:
        a = self._old(2)
        new = _from_refs([f"noise:{i}" for i in range(12)])  # none of fact:*
        out = _publish(a, new, RenderKey("doc", "v1", 20))
        assert out.viewport.offset == 2  # numeric hold, not a reset

    def test_new_identity_resets_to_top(self) -> None:
        a = self._old(4)
        out = _publish(a, _rows(10), RenderKey("doc2", "v1", 10))  # no refs → no anchor
        assert out.viewport.offset == 0

    def test_new_identity_reanchors_on_a_shared_ref(self) -> None:
        """Precedence is literal (§6): a ref present in both Blocks re-anchors even
        across a new identity — reset is the last resort, not a short-circuit."""
        a = self._old(2)  # topmost visible ref fact:2
        new = _from_refs([("fact:2" if i == 6 else f"other:{i}") for i in range(12)])
        out = _publish(a, new, RenderKey("doc2", "v1", 10))  # new identity, shared ref
        assert out.viewport.offset == 6

    def test_first_publish_starts_at_top(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(10), RenderKey("doc", "v1", 10))
        assert a.viewport.offset == 0


# --- Frame production + identity (deliverables 5, P1a) -----------------------


class TestFrameProduction:
    def test_frame_bundles_block_and_token(self) -> None:
        a = _publish(ViewportAdapter(frame_height=7), _rows(3), RenderKey("d", "v1", 10))
        f = a.frame()
        assert isinstance(f, Frame)
        assert f.block.height == 7  # fitted + padded

    def test_scroll_mints_a_distinct_token(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(20), RenderKey("d", "v1", 10))
        assert a.frame().token != a.scroll(1).frame().token
        assert a.resize(6).frame().token != a.frame().token

    def test_evidence_waived_at_f0(self) -> None:
        a = _publish(ViewportAdapter(frame_height=0), _rows(10), RenderKey("d", "v1", 10))
        assert a.frame().block.height == 0

    def test_evidence_label_is_threaded(self) -> None:
        a = _publish(ViewportAdapter(frame_height=5), _rows(10), RenderKey("d", "v1", 10))
        text = row_text(a.frame(evidence_label="6 older ticks").block, 4)
        assert "6 older ticks" in text and "more rows" not in text

    def test_evidence_ref_is_threaded(self) -> None:
        a = _publish(
            ViewportAdapter(frame_height=5, evidence_ref="scroll:below"),
            _rows(10),
            RenderKey("d", "v1", 10),
        )
        assert a.frame().block.cell_ref(0, 4) == "scroll:below"

    def test_frame_before_publish_is_blank(self) -> None:
        assert ViewportAdapter(frame_height=4).frame().block.height == 4


# --- Coordinate resolution (deliverables 6, P1a, P2c) ------------------------


class TestCoordinateResolution:
    def _overflowing(self) -> ViewportAdapter:
        return _publish(
            ViewportAdapter(frame_height=5, evidence_ref="scroll:below"),
            _rows(10, ref_prefix="fact"),
            RenderKey("doc", "v1", 10),
        )

    def test_content_region_translates_through_offset(self) -> None:
        a = self._overflowing().scroll_to(3)  # window rows 3..6
        token = a.frame().token
        hit = a.resolve(0, 0, token)
        assert hit.region is FrameRegion.CONTENT
        assert hit.ref == "fact:3" and hit.content_xy == (0, 3)
        deeper = a.resolve(2, 3, token)  # last content row (y=3) → content row 6
        assert deeper.region is FrameRegion.CONTENT
        assert deeper.content_xy == (2, 6) and deeper.ref == "fact:6"

    def test_evidence_row_resolves_to_host_ref(self) -> None:
        a = self._overflowing()
        hit = a.resolve(0, 4, a.frame().token)  # the evidence row (last of F=5)
        assert hit.region is FrameRegion.EVIDENCE
        assert hit.ref == "scroll:below" and hit.content_xy is None

    def test_padding_region_resolves_to_nothing(self) -> None:
        a = _publish(ViewportAdapter(frame_height=6), _rows(3), RenderKey("d", "v1", 10))
        token = a.frame().token
        assert a.resolve(0, 1, token).region is FrameRegion.CONTENT
        assert a.resolve(0, 4, token).region is FrameRegion.PADDING  # below 3 content rows

    def test_x_beyond_width_is_outside_in_every_region(self) -> None:
        """P2c: x is bounded to the frame width for content, evidence, AND padding
        — an out-of-width point is off the frame, not a host-ref or padding hit."""
        over = self._overflowing()  # width 24, F=5 overflow (evidence at y=4)
        tok = over.frame().token
        assert over.resolve(99, 0, tok).region is FrameRegion.OUTSIDE  # content row
        assert over.resolve(99, 4, tok).region is FrameRegion.OUTSIDE  # evidence row
        fit = _publish(ViewportAdapter(frame_height=6), _rows(3), RenderKey("d", "v1", 10))
        assert fit.resolve(99, 4, fit.frame().token).region is FrameRegion.OUTSIDE  # padding row

    def test_out_of_frame_is_outside(self) -> None:
        a = self._overflowing()
        tok = a.frame().token
        assert a.resolve(0, 5, tok).region is FrameRegion.OUTSIDE  # y == F
        assert a.resolve(-1, 0, tok).region is FrameRegion.OUTSIDE
        assert a.resolve(0, -1, tok).region is FrameRegion.OUTSIDE

    def test_origin_offset_is_honored(self) -> None:
        a = self._overflowing().scroll_to(3)
        hit = a.resolve(4, 12, a.frame().token, origin_x=4, origin_y=12)  # local (0,0)
        assert hit.region is FrameRegion.CONTENT and hit.content_xy == (0, 3)

    def test_f1_overflow_single_row_is_evidence(self) -> None:
        a = self._overflowing().resize(1)
        assert a.resolve(0, 0, a.frame().token).region is FrameRegion.EVIDENCE

    def test_stale_token_is_dropped(self) -> None:
        """A token from a frame the state has replaced (here by a scroll) drops —
        never translated through the new geometry (the SIGWINCH drain window)."""
        a = self._overflowing()
        old = a.frame()
        scrolled = a.scroll(2)  # offset moves → new token
        stale = scrolled.resolve(0, 0, old.token)
        assert stale.stale and stale.region is FrameRegion.OUTSIDE
        # The frozen state that produced ``old`` still resolves it correctly.
        assert a.resolve(0, 0, old.token).region is FrameRegion.CONTENT
        # The scrolled state resolves its own token.
        assert scrolled.resolve(0, 0, scrolled.frame().token).region is FrameRegion.CONTENT

    def test_token_is_required(self) -> None:
        a = self._overflowing()
        with pytest.raises(TypeError):
            a.resolve(0, 0)  # type: ignore[call-arg]


# --- Degenerate guards --------------------------------------------------------


class TestDegenerate:
    def test_negative_frame_height_fails_loudly(self) -> None:
        a = ViewportAdapter()
        with pytest.raises(ContractError):
            a.publish(_rows(3), a.plan(RenderKey("d", "v1", 10)), frame_height=-1)
        published = _publish(ViewportAdapter(frame_height=5), _rows(3), RenderKey("d", "v1", 10))
        with pytest.raises(ContractError):
            published.resize(-1)

    def test_plan_is_a_returned_fact(self) -> None:
        plan = ViewportAdapter().plan(RenderKey("d", "v1", 10))
        assert isinstance(plan, Plan)
        assert plan.action is RenderAction.RE_RENDER and plan.base is None
