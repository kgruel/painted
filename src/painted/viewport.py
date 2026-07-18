"""Viewport: scroll state for vertically-scrollable views."""

from __future__ import annotations

from dataclasses import dataclass, replace


def frame_capacity(frame_height: int, content_height: int) -> int:
    """Content rows a frame of ``frame_height`` shows for ``content_height`` rows.

    The law-6 reserved-row arithmetic shared by every windowed view (the host
    ``ViewportAdapter`` and the offered-arm ``list_view``/``table``/
    ``data_explorer`` components) — one definition so the frame vocabulary and
    the scroll state that feeds it never drift:

    - ``frame_height <= 0`` → ``0`` (nothing shows; law-6 evidence waived).
    - content **fits** (``content_height <= frame_height``) → ``frame_height``
      (the whole frame is content; offset pins to 0).
    - content **overflows** → ``frame_height - 1`` (one row is reserved for the
      evidence row; ``0`` at ``frame_height == 1`` — the single row *is* the
      evidence row, the ``assemble_frame``/``InPlaceRenderer`` precedent).

    This equals ``assemble_frame``'s ``shown``, so an offset clamped against this
    capacity matches the frame builder's own slice — a selected final item lands
    above the evidence row, never behind it. The overflow decision compares the
    natural ``content_height`` to ``frame_height`` (not to the capacity), which is
    the resolved fixpoint: reserving the row cannot itself flip the decision.
    """
    if frame_height <= 0:
        return 0
    if content_height <= frame_height:
        return frame_height
    return frame_height - 1


@dataclass(frozen=True, slots=True)
class Viewport:
    """Scroll state for a vertically-scrollable view.

    Tracks offset (first visible row), visible height, and content height.
    All operations return new Viewport instances (immutable).

    Use with vslice() for rendering:
        visible_block = vslice(content_block, viewport.offset, viewport.visible)
    """

    offset: int = 0
    visible: int = 0
    content: int = 0

    @property
    def max_offset(self) -> int:
        """Maximum valid offset (0 if content fits in viewport)."""
        return max(0, self.content - self.visible)

    @property
    def can_scroll(self) -> bool:
        """True if content exceeds viewport height."""
        return self.content > self.visible

    @property
    def is_at_top(self) -> bool:
        """True if scrolled to the top."""
        return self.offset == 0

    @property
    def is_at_bottom(self) -> bool:
        """True if scrolled to the bottom."""
        return self.offset >= self.max_offset

    def _clamp(self, offset: int) -> int:
        """Clamp offset to valid range [0, max_offset]."""
        return max(0, min(offset, self.max_offset))

    def scroll(self, delta: int) -> Viewport:
        """Scroll by delta rows. Positive = down, negative = up."""
        return replace(self, offset=self._clamp(self.offset + delta))

    def scroll_to(self, position: int) -> Viewport:
        """Scroll to absolute position."""
        return replace(self, offset=self._clamp(position))

    def page_up(self) -> Viewport:
        """Scroll up by one page (visible height)."""
        return self.scroll(-self.visible)

    def page_down(self) -> Viewport:
        """Scroll down by one page (visible height)."""
        return self.scroll(self.visible)

    def home(self) -> Viewport:
        """Scroll to top."""
        return replace(self, offset=0)

    def end(self) -> Viewport:
        """Scroll to bottom."""
        return replace(self, offset=self.max_offset)

    def scroll_into_view(self, index: int) -> Viewport:
        """Adjust offset to ensure index is visible.

        If index is above the viewport, scrolls up to show it at top.
        If index is below the viewport, scrolls down to show it at bottom.
        If index is already visible, returns unchanged.
        """
        if index < self.offset:
            return replace(self, offset=max(0, index))
        elif index >= self.offset + self.visible:
            return replace(self, offset=self._clamp(index - self.visible + 1))
        return self

    def with_content(self, content: int) -> Viewport:
        """Return viewport with updated content height, clamping offset if needed."""
        new = replace(self, content=content)
        return replace(new, offset=new._clamp(new.offset))

    def with_visible(self, visible: int) -> Viewport:
        """Return viewport with updated visible height, clamping offset if needed."""
        new = replace(self, visible=visible)
        return replace(new, offset=new._clamp(new.offset))


def _scroll_into_capacity(vp: Viewport, index: int) -> Viewport:
    """Scroll ``vp`` so ``index`` is visible within the content *capacity*.

    Like ``Viewport.scroll_into_view``, but clamps against
    ``frame_capacity(vp.visible, vp.content)`` — one row fewer under overflow,
    reserved for the law-6 evidence row — so a selected final item lands above
    that row, never behind it. ``vp.visible`` is the frame allocation ``F`` (the
    page size a caller reads off it directly) and is **preserved**; only the
    offset moves. At capacity 0 (``F = 0``, or ``F = 1`` under overflow — the
    single row *is* the evidence row) there is no content row to reveal, so the
    offset is left untouched.

    This is the one capacity-scroll every windowed component's state goes through
    — ``list_view``/``table``/``data_explorer`` ``scroll_into_view``,
    ``with_visible``, and the ``data_explorer`` move/page ops — so the package
    holds a single viewport-state convention: ``visible`` is always ``F``, the
    offset always capacity-clamped. Module-level and underscore-private: it is not
    part of ``Viewport``'s public surface (the offered-arm evidence slice is an
    internal contract, not an exported viewport operation).
    """
    cap = frame_capacity(vp.visible, vp.content)
    if cap <= 0:
        return vp
    scrolled = vp.with_visible(cap).scroll_into_view(index)
    return replace(scrolled, visible=vp.visible)
