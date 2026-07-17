"""The host viewport adapter — the omitted arm of the dual allocation contract,
wired (HOST_RUNG_DESIGN §6).

The renderer contract has two arms (RENDER_MODEL §2, restated in HOST_RUNG §2):
a renderer offered ``height`` returns an exact ``H``-row frame and owns its own
omission evidence; a renderer *not* offered height returns natural-height content
and the **host** applies a viewport — offset + window — and owns the viewport
state and the law-6 evidence. ``ViewportAdapter`` is that host half, as a value:
given a semantic renderer's natural-height ``Block`` and a frame height ``F``, it
owns render planning, the atomic cache, scroll/anchor reconciliation, the
assembled frame, and coordinate resolution.

It is **delivery-agnostic**. It never invokes a renderer (it *receives* Blocks),
never consults TTY state, never writes to a terminal, and imports nothing from
``cli`` or ``tui``. Mounting it into interactive dispatch — input routing,
SIGWINCH ordering, ``Surface`` event delivery — is S4; this object is built so S4
can drive it without modification, exercised here entirely through constructed
Blocks.

Per repo convention it is a **frozen** dataclass: transitions are pure functions
``(state, inputs) → new state`` and frame production is a pure function of state.
``Viewport`` (``painted.viewport``) stays the scroll-state carrier *inside* it —
this module never duplicates ``offset``/``visible``/``content`` or reimplements
clamping.

Placement (package root, beside ``inplace.py`` / ``diagnostics.py``, not
``painted.views``): the module map keeps the pure ``Viewport`` primitive and the
delivery mechanisms at root, while ``painted.views`` holds semantic projections
and component render functions. This adapter is host *orchestration* — render
planning, ticketed cache publication, frame identity, coordinate resolution — not
a view. It consumes ``views.assemble_frame`` (a root module importing views is
fine — the ``diagnostics.py`` precedent).

Two distinct identities, deliberately kept apart (the review's P1a/P1b):

* the **generation** (``_Generation.gid``) — the cached content Block's identity,
  a fresh ``_GenerationId`` object minted per ``plan`` call and stamped by an
  accepted ``publish``. It is *provenance, not a counter*: a lineage-local
  sequence could not tell two pure forks apart (both would propose the same next
  integer), so the identity is a per-plan object compared by identity. A
  ``seq`` survives on ``_Generation`` for ordering/debugging only. Render tickets
  (``Plan``) gate publication against the generation identity, so an out-of-order
  publish is rejected, and pure forks stay distinct.
* the **frame token** (``FrameToken``) — the exact *displayed mapping*
  (generation identity + offset + frame height). It changes on every distinct
  frame, *including a scroll*, and is what ``resolve`` requires — a token from a
  frame the state has since replaced (or from a sibling fork) resolves to a drop,
  never through new geometry.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING

from .core.errors import ContractError
from .viewport import Viewport
from .views import assemble_frame

if TYPE_CHECKING:
    from .core.block import Block


# --- Generation, tickets, and frame identity ---------------------------------


@dataclass(frozen=True, slots=True)
class RenderKey:
    """The renderer-input identity a cached content Block was produced from.

    The adapter never inspects data, fidelity, component state, capabilities, or
    presentation policy — it only asks "are the renderer inputs the same as last
    time?" So the caller reduces all of those to one opaque ``inputs`` token (any
    hashable — a tuple, a frozen state, a content hash). ``width`` is called out
    separately because a width change is the resize matrix's re-render-*and*-
    reconcile trigger (§6): numeric offsets are not stable across a reflow.

    ``content_id`` is the caller's **content identity** — its notion of "this is
    (still) the same document." The adapter takes it as an input rather than
    inventing a content-comparison heuristic (§6 fallback 4: reset-to-top only
    for a *new* content identity). Two renders of one growing log share a
    ``content_id``; opening a different log is a new one. Any hashable serves.
    """

    content_id: Hashable
    inputs: Hashable
    width: int | None


class _GenerationId:
    """A collision-free generation identity — one fresh instance per ``plan``
    call, compared by object identity.

    A lineage-local counter cannot distinguish **pure forks**: two plans issued
    from the same frozen base state would each propose ``seq + 1`` — the same
    integer — so branches with equal window geometry would mint equal
    ``FrameToken``s and cross-resolve. Frozen-state purity makes those divergent
    branches legal, so the identity needs *provenance*, not a counter. A distinct
    object per ``plan`` supplies it: each fork carries its own sentinel through
    ``plan → accepted generation → FrameToken``, and ``resolve`` matches on that
    object's identity. No ``Date``/``random`` needed — the object *is* the
    provenance. ``__slots__`` keeps it a bare identity marker.
    """

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class _Generation:
    """Private: the cached (inputs → Block) pairing and its identity.

    ``gid`` is the collision-free identity (a ``_GenerationId``), assigned only
    through an accepted ``publish`` from the ticket the plan carried; it is what
    ``FrameToken`` and ticketing compare on. ``seq`` is retained for ordering and
    debugging only — it is *not* the identity (pure forks share a ``seq``). Not a
    public type: correct use installs content through ``publish``, never by hand
    (the adapter fields are constructable — the ``Viewport`` precedent — but the
    identity is managed here so tickets stay sound).
    """

    key: RenderKey
    gid: _GenerationId
    seq: int


class RenderAction(Enum):
    """The resize-matrix decision, a returned fact the host acts on (§6).

    ``RE_RENDER`` — a renderer input changed (width, the opaque inputs token, or
    content identity): the host calls the renderer again and ``publish``es the
    result under the plan. ``RE_SLICE`` — only the frame *height* changed: the
    host calls ``resize`` and the cached Block is re-windowed, no renderer call.
    """

    RE_RENDER = "re-render"
    RE_SLICE = "re-slice"


@dataclass(frozen=True, slots=True)
class Plan:
    """The result of ``plan`` — the resize decision *and* the publication ticket.

    ``action`` is the matrix decision; ``key`` is the render inputs it was planned
    for. The other two fields are the ticket, both opaque provenance objects —
    carry the whole ``Plan`` to ``publish`` and never inspect them:

    * ``base`` — the generation identity the plan was issued against (``None``
      before any publish). ``publish`` accepts only while the adapter still sits
      on this identity, so a publish applied *out of order* after a newer one is
      rejected (its base no longer matches the advanced generation).
    * ``proposed`` — a fresh identity minted for the generation this plan would
      create. It makes **pure forks** distinguishable: two plans from one base
      carry *different* ``proposed`` objects, so the branches they publish get
      different generation identities (and thus non-colliding ``FrameToken``s)
      even though both pass the ``base`` check.
    """

    action: RenderAction
    key: RenderKey
    base: _GenerationId | None
    proposed: _GenerationId


@dataclass(frozen=True, slots=True)
class FrameToken:
    """Opaque identity of one *displayed mapping* — generation + window.

    Produced by ``frame`` inseparably from its Block and required by ``resolve``.
    Two frames compare equal iff they show the same content generation (by the
    generation's identity object, not a counter — so pure forks never collide)
    through the same offset and frame height. A scroll, a resize, and a re-render
    each mint a distinct token, and a stale token (from a frame the state has
    replaced) fails the equality gate in ``resolve``. Treat it as opaque.
    """

    generation: _GenerationId | None
    offset: int
    height: int


@dataclass(frozen=True, slots=True)
class Frame:
    """A delivered frame: the Block and the ``FrameToken`` that identifies it.

    The two are inseparable — a host cannot paint the Block and then hit-test
    against a *different* mapping, because ``resolve`` requires this token and it
    only matches the state that produced this frame.
    """

    block: Block
    token: FrameToken


class FrameRegion(Enum):
    """Which region of the delivered frame a coordinate fell in (§6 hit test).

    ``CONTENT`` translates to a content-Block coordinate; ``EVIDENCE`` is the
    host-authored scroll-evidence row (its own host ref, no content translation);
    ``PADDING`` is the blank remainder below fitted content; ``OUTSIDE`` is off
    the frame entirely — beyond its width or height, or host chrome the adapter
    does not own (the host handles its own events there).
    """

    CONTENT = "content"
    EVIDENCE = "evidence"
    PADDING = "padding"
    OUTSIDE = "outside"


@dataclass(frozen=True, slots=True)
class Hit:
    """The resolution of a frame coordinate (``ViewportAdapter.resolve``).

    ``region`` says which frame region was struck; ``ref`` is the denotation ref
    it resolves to (a content cell's ref for ``CONTENT``, the evidence row's host
    ref for ``EVIDENCE``, else ``None``); ``content_xy`` is the translated ``(x,
    y)`` into the cached content Block, present only for ``CONTENT``. ``stale`` is
    set when the query's token names a frame the state has replaced — drop the
    event, or re-run it against the frozen state that produced its frame; never
    resolve it here.
    """

    region: FrameRegion
    ref: str | None = None
    content_xy: tuple[int, int] | None = None
    stale: bool = False


# --- Window arithmetic --------------------------------------------------------


def _content_capacity(frame_height: int, content_height: int) -> int:
    """Content rows the window shows at frame height ``F`` — matches ``assemble_frame``.

    At ``F = 0`` nothing shows. When content **fits** (``content ≤ F``) the whole
    frame is content, so the capacity is ``F`` (offset pins to 0). When content
    **overflows** one row is reserved for the evidence row, so the capacity is
    ``F − 1`` (0 at ``F = 1`` — the single row *is* evidence). This equals
    ``assemble_frame``'s ``shown``, so ``max_offset`` matches its offset clamp.
    """
    if frame_height <= 0:
        return 0
    if content_height <= frame_height:
        return frame_height
    return frame_height - 1


def _window(offset: int, frame_height: int, content_height: int) -> Viewport:
    """A ``Viewport`` for ``content_height`` rows in a frame of ``frame_height``.

    The offset is *not* clamped here — the caller applies the intent op
    (``end``/``scroll_to``/``scroll_into_view``) that clamps, so intent survives
    the geometry change.
    """
    return Viewport(
        offset=offset,
        visible=_content_capacity(frame_height, content_height),
        content=content_height,
    )


def _clamp_cursor(index: int, content_height: int) -> int:
    """A retained cursor row clamped into the current content."""
    if content_height <= 0:
        return 0
    return max(0, min(index, content_height - 1))


# --- Anchor policy: the ref re-anchor (§6 fallback 2) ------------------------


def _row_ref(block: Block, y: int) -> str | None:
    """The first ref annotation in row ``y`` (``None`` if the row carries none).

    *Any* ref is an anchor candidate — scheme-ful (``fact:01JQ8F``) or scheme-less
    (``sidebar``). The ratified text says "visible semantic ref"; the ref model
    (refs.py) treats every ref as a denotation annotation, scheme-less included
    (they are simply inert in *link* deliveries), so all are usable as viewport
    anchors here, best-effort.
    """
    for x in range(block.width):
        ref = block.cell_ref(x, y)
        if ref is not None:
            return ref
    return None


def _first_row_with_ref(block: Block, ref: str) -> int | None:
    """The first row of ``block`` carrying ``ref`` (``None`` if absent).

    First occurrence, so a ref repeated or spanning rows re-anchors to its top —
    the best-effort discipline §6 names.
    """
    for y in range(block.height):
        for x in range(block.width):
            if block.cell_ref(x, y) == ref:
                return y
    return None


def _reanchor_offset(old_content: Block, old_view: Viewport, new_content: Block) -> int | None:
    """Offset that keeps the topmost visible ref in view after a reflow.

    Scans the old window top-down for the first row bearing a ref that also exists
    in the new content, and returns the new content row where that ref first
    appears — so the reader's anchor stays put across a width change. Returns
    ``None`` when no visible ref carries across (absent or reflowed out), so the
    caller falls through to the numeric offset (§6 fallback 3).
    """
    start = old_view.offset
    end = min(old_view.offset + old_view.visible, old_content.height)
    for oy in range(start, end):
        ref = _row_ref(old_content, oy)
        if ref is None:
            continue
        ny = _first_row_with_ref(new_content, ref)
        if ny is not None:
            return ny
    return None


# --- The adapter --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ViewportAdapter:
    """Host viewport state for one natural-height renderer binding (§6).

    Construct empty and drive it through its transitions — do **not** hand-build
    ``content``/``generation``: the fields are public (the ``Viewport`` precedent),
    but correct use installs content through ``publish``, which stamps the
    generation under a ticket. The protocol:

      * ``plan(key) → Plan`` — decide re-render vs re-slice and mint a ticket.
      * ``publish(block, plan) → ViewportAdapter | None`` — install a rendered
        Block *atomically with its key*, reconciling the viewport by the anchor
        policy; ``None`` when the ticket is stale (the publish lost a race).
      * ``resize(F) → ViewportAdapter`` — the height-only re-slice.
      * scroll ops — move the offset, tracking follow / cursor intent.
      * ``frame(...) → Frame`` — the exact-``F`` delivery Block and its token.
      * ``resolve(x, y, token, ...) → Hit`` — the hit-test frame transform.

    Fields:
      * ``frame_height`` — the current vertical allocation ``F ≥ 0`` (the host's
        offer after it reserves its own chrome; the adapter never crops further).
      * ``content`` — the cached natural-height Block (``None`` before publish).
      * ``generation`` — the ``_Generation`` the cached Block was produced under.
      * ``viewport`` — the ``Viewport`` scroll-state carrier.
      * ``following`` — the at-bottom / follow (tail) intent.
      * ``cursor`` — a retained cursor-row anchor (cursor-following intent), or
        ``None``. Mutually exclusive with ``following``. Reapplied across content
        and geometry changes, so a tracked row stays visible.
      * ``evidence_ref`` — an optional host-owned denotation ref stamped on the
        evidence row, so a click on it routes through the denotation channel.
    """

    frame_height: int = 0
    content: Block | None = None
    generation: _Generation | None = None
    viewport: Viewport = Viewport()
    following: bool = False
    cursor: int | None = None
    evidence_ref: str | None = None

    # --- The resize decision + ticket (§6 matrix) -----------------------------

    def plan(self, key: RenderKey) -> Plan:
        """Decide re-render vs re-slice for ``key`` and mint the publication ticket.

        ``RE_RENDER`` when any renderer input differs from the cached generation —
        width, the opaque ``inputs`` token, or content identity — or when nothing
        is cached yet; otherwise ``RE_SLICE``. The returned ``Plan`` carries the
        ticket: the generation identity it was issued against (``base``) and a
        fresh identity for the generation it would create (``proposed``) — the
        latter minted *per call*, so two plans from one base publish distinct,
        non-colliding generations.
        """
        base = None if self.generation is None else self.generation.gid
        action = (
            RenderAction.RE_RENDER
            if self.generation is None or key != self.generation.key
            else RenderAction.RE_SLICE
        )
        return Plan(action, key, base, _GenerationId())

    # --- Ticketed atomic cache publication + reconciliation -------------------

    def publish(
        self, content: Block, plan: Plan, *, frame_height: int | None = None
    ) -> ViewportAdapter | None:
        """Install ``content`` under ``plan.key`` if the ticket still holds (§6).

        Publication is **atomic with the key**: the Block and the ``RenderKey`` it
        was rendered for (carried in ``plan``) land in one transition, so a block
        can never be installed under a key it was not rendered for. The ticket
        makes that sound under concurrency:

        * *out-of-order* publishes fail — publication is accepted only while the
          adapter still sits on ``plan.base``, so a plan issued against a
          generation another publish has already advanced past returns ``None``
          (losing a race is normal in streaming; re-plan and re-render). A
          returned fact, never an exception.
        * *pure forks* are both accepted but stay distinguishable — two plans from
          one frozen base share a ``base`` (both pass the check) yet carry
          different ``proposed`` identities, so the branches they publish get
          different generation identities and thus non-colliding frame tokens.

        ``frame_height`` optionally updates ``F`` in the same step (a width+height
        resize renders once, publishes at the new height). The width-reflow anchor
        policy, in the §6 precedence order, with intent read *before* the new
        window is built (intent-before-geometry):
          1. follow/bottom intent survives to the new bottom;
          2. a retained cursor stays visible (cursor-following);
          3. a visible ref present in both Blocks re-anchors the view;
          4. the numeric offset holds, clamped;
          5. reset to top — only for a new content identity or no prior frame.
        (Ratified precedence: a shared ref re-anchors even across a new identity —
        the "same record seen in a different document" case — so reset is the last
        resort, not an identity short-circuit.)
        """
        F = self.frame_height if frame_height is None else frame_height
        if F < 0:
            raise ContractError(f"frame_height must be >= 0, got {F}")

        current = None if self.generation is None else self.generation.gid
        if plan.base is not current:  # identity: the plan's base must be *this* generation
            return None  # stale out-of-order ticket — lost the publication race

        was_following = self.following
        cursor = self.cursor
        old_content = self.content
        old_view = self.viewport
        fresh = self.generation is None or plan.key.content_id != self.generation.key.content_id

        base = _window(0, F, content.height)
        if was_following:
            view, following, new_cursor = base.end(), True, None  # (1)
        elif cursor is not None and not fresh:
            c = _clamp_cursor(cursor, content.height)
            view, following, new_cursor = base.scroll_into_view(c), False, c  # (2)
        else:
            anchor = (
                None if old_content is None else _reanchor_offset(old_content, old_view, content)
            )
            if anchor is not None:
                view = base.scroll_to(anchor)  # (3) ref re-anchor — beats reset
            elif fresh:
                view = base  # (5) new identity / no prior frame → top
            else:
                view = base.scroll_to(old_view.offset)  # (4) numeric hold, clamped
            following, new_cursor = False, None

        seq = 0 if self.generation is None else self.generation.seq + 1
        return replace(
            self,
            frame_height=F,
            content=content,
            generation=_Generation(key=plan.key, gid=plan.proposed, seq=seq),
            viewport=view,
            following=following,
            cursor=new_cursor,
        )

    # --- Height-only re-slice (§6 matrix, "omitted height") -------------------

    def resize(self, frame_height: int) -> ViewportAdapter:
        """Re-window the cached Block at a new frame height — no renderer call.

        The re-slice arm of the matrix (the host establishes "no renderer input
        changed" via ``plan`` first). Intent is captured before the window is
        rebuilt: a following viewport stays at the new bottom; a retained cursor
        stays visible; otherwise the numeric offset is re-clamped — terminal
        *shrink* grows ``max_offset`` and usually keeps the offset valid, while
        viewport *growth* or content shrink forces the clamp (§6 directionality).
        The generation is unchanged (same cached Block), but the frame token
        changes (geometry moved), so a stale event cannot resolve against it.
        """
        if frame_height < 0:
            raise ContractError(f"frame_height must be >= 0, got {frame_height}")

        if self.content is None or self.generation is None:
            view = _window(self.viewport.offset, frame_height, self.viewport.content)
            return replace(self, frame_height=frame_height, viewport=view.scroll_to(view.offset))

        base = _window(self.viewport.offset, frame_height, self.content.height)
        if self.following:
            view = base.end()
        elif self.cursor is not None:
            view = base.scroll_into_view(_clamp_cursor(self.cursor, self.content.height))
        else:
            view = base.scroll_to(self.viewport.offset)
        return replace(self, frame_height=frame_height, viewport=view)

    # --- Scroll ops (delegate to Viewport, track follow / cursor intent) ------
    #
    # A manual viewport move clears the cursor intent (the user grabbed the
    # viewport, no longer tracking a row) and sets follow when a downward move
    # reaches the bottom. ``scroll_into_view`` is the cursor-following entry: it
    # retains the cursor so later transitions keep that row visible.

    def _move(self, view: Viewport, *, following: bool, cursor: int | None) -> ViewportAdapter:
        return replace(self, viewport=view, following=following, cursor=cursor)

    def scroll(self, delta: int) -> ViewportAdapter:
        """Scroll by ``delta`` rows (positive down). Down-to-bottom re-follows."""
        if delta == 0:
            return self
        view = self.viewport.scroll(delta)
        return self._move(view, following=view.is_at_bottom if delta > 0 else False, cursor=None)

    def page_up(self) -> ViewportAdapter:
        """Scroll up one page; disengages follow and cursor."""
        return self._move(self.viewport.page_up(), following=False, cursor=None)

    def page_down(self) -> ViewportAdapter:
        """Scroll down one page; re-follows if it reaches the bottom."""
        view = self.viewport.page_down()
        return self._move(view, following=view.is_at_bottom, cursor=None)

    def home(self) -> ViewportAdapter:
        """Jump to the top; top-anchored (no follow, no cursor)."""
        return self._move(self.viewport.home(), following=False, cursor=None)

    def end(self) -> ViewportAdapter:
        """Jump to the bottom; engages follow."""
        return self._move(self.viewport.end(), following=True, cursor=None)

    def scroll_to(self, position: int) -> ViewportAdapter:
        """Scroll to an absolute offset; follows iff it lands at the bottom."""
        view = self.viewport.scroll_to(position)
        return self._move(view, following=view.is_at_bottom, cursor=None)

    def scroll_into_view(self, index: int) -> ViewportAdapter:
        """Scroll so content row ``index`` is visible and **retain it** as the
        cursor anchor — the cursor-following intent, reapplied by later
        transitions (not a one-time move)."""
        c = _clamp_cursor(index, self.viewport.content)
        return self._move(self.viewport.scroll_into_view(c), following=False, cursor=c)

    # --- Frame production (§6, over the S2 assembler) -------------------------

    def _token(self) -> FrameToken:
        gid = None if self.generation is None else self.generation.gid
        return FrameToken(generation=gid, offset=self.viewport.offset, height=self.frame_height)

    def frame(self, *, evidence_label: str | None = None) -> Frame:
        """The delivered frame — Block + token — exactly ``frame_height`` rows (§6).

        ``assemble_frame`` over the cached Block at the current offset: content
        padded when it fits, sliced with one host-authored evidence row when it
        overflows, evidence waived at ``F = 0`` (the §5 degenerate mirror). The
        evidence row counts *rows*, not entries; ``evidence_label`` is the seam for
        caller-supplied entry wording, supplied per frame because it is the
        application's to know. Any ``evidence_ref`` threads through. The returned
        ``Frame`` bundles the token ``resolve`` requires — the two are inseparable.
        """
        token = self._token()
        if self.content is None:
            from .core.block import Block

            return Frame(Block.empty(0, self.frame_height), token)
        block = assemble_frame(
            self.content,
            self.frame_height,
            self.viewport.offset,
            ref=self.evidence_ref,
            label=evidence_label,
        )
        return Frame(block, token)

    # --- Coordinate resolution (§6 hit test — the frame transform) ------------

    def resolve(
        self,
        x: int,
        y: int,
        token: FrameToken,
        *,
        origin_x: int = 0,
        origin_y: int = 0,
    ) -> Hit:
        """Resolve a frame coordinate to a region and ref (§6 hit test).

        The frame transform, not ``y + offset``: the region is resolved first, and
        only ``CONTENT`` coordinates translate — ``(x − origin_x, y − origin_y +
        offset)`` — against the cached Block. ``origin_x``/``origin_y`` are where
        the adapter's content region sits within the passed point's coordinate
        space, so S4 can hand raw surface coordinates through.

        ``token`` is **required** and guards the SIGWINCH drain window: if it does
        not match the state's current frame (a scroll, resize, or re-render has
        since minted a new token), the event was observed against a frame this
        state has replaced, and the result is ``stale`` — drop it, or re-run it
        against the frozen state that produced its frame. Never translate a stale
        event through the new geometry. Host chrome and the evidence row resolve to
        their own refs (or nothing); only content translates.
        """
        if token != self._token():
            return Hit(FrameRegion.OUTSIDE, stale=True)

        F = self.frame_height
        lx = x - origin_x
        ly = y - origin_y
        width = 0 if self.content is None else self.content.width
        # Bound x for ALL regions (not just content): an out-of-width point on the
        # evidence or padding row is off the frame, not a host-ref / padding hit.
        if self.content is None or F <= 0 or lx < 0 or lx >= width or ly < 0 or ly >= F:
            return Hit(FrameRegion.OUTSIDE)

        h = self.content.height
        if h <= F:
            # Fitted: content rows [0, h), then blank padding to F.
            return Hit(FrameRegion.PADDING) if ly >= h else self._content_hit(lx, ly)

        # Overflow: F-1 content rows, then one evidence row (the last row; the only
        # row at F=1). ``shown`` matches assemble_frame.
        if ly >= F - 1:
            return Hit(FrameRegion.EVIDENCE, ref=self.evidence_ref)
        return self._content_hit(lx, ly)

    def _content_hit(self, lx: int, ly: int) -> Hit:
        """Translate a content-region point through the offset and read its ref."""
        assert self.content is not None
        cy = ly + self.viewport.offset
        if cy >= self.content.height:  # defensive; the offset clamp keeps cy < height
            return Hit(FrameRegion.OUTSIDE)
        return Hit(FrameRegion.CONTENT, ref=self.content.cell_ref(lx, cy), content_xy=(lx, cy))


__all__ = [
    "ViewportAdapter",
    "RenderKey",
    "Plan",
    "RenderAction",
    "Frame",
    "FrameToken",
    "FrameRegion",
    "Hit",
]
