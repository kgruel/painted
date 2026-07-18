"""The inward host-event seam (HOST_RUNG_DESIGN §7, S5).

``on_host_event=`` carries host viewing-state to the application as *input* — the
inward counterpart of the outward-only ``Surface.emit``. These pin the seam's
ruled contract:

* the **two-token discipline** — ``observed`` is always the last *displayed*
  frame (stable across a drain batch, so later events in a batch legitimately
  carry ``observed != current``), ``current`` is always the live installed
  mapping (never copied from ``observed``), and no event fires before the first
  frame is displayed;
* **each ``ViewportChange`` reason minted from its transition** — a manual scroll
  is ``ScrollChange``, follow engage/track/disengage is ``FollowChange``, a
  cursor move is ``CursorFollowChange``, a resize is ``ResizeChange``;
* **hit and quit events** carry the two tokens (and the ``Hit``);
* **honest silence** — the offered arm owns no viewport, so a declared sink there
  fires zero times;
* **handler-exception propagation** — a sink fault fails the active host delivery
  loud through the production run loop (terminal restored, exception escapes),
  never swallowed nor rerouted to ``emit``.

Driven through the shared ``HostViewport`` controller directly and through
``HostSurface`` / ``TestSurface``; the follow acceptance shape (a declared stream
end-to-end) is ``tests/integration/test_follow_acceptance.py``.
"""

from __future__ import annotations

import pytest

from painted import (
    CursorFollowChange,
    FollowChange,
    HostHitEvent,
    HostQuitEvent,
    HostViewportEvent,
    ResizeChange,
    ScrollChange,
)
from painted.core.block import Block
from painted.core.cell import Style
from painted.core.compose import join_vertical
from painted.host import HostViewport
from painted.mouse import MouseAction, MouseButton, MouseEvent
from painted.tui import HostSurface, TestSurface


def _rows(n: int, width: int = 20, ref_prefix: str | None = None) -> Block:
    return join_vertical(
        *[
            Block.text(
                f"row{i}",
                Style(),
                width=width,
                ref=None if ref_prefix is None else f"{ref_prefix}:{i}",
            )
            for i in range(n)
        ]
    )


def _mounted(
    rows: int,
    *,
    width: int = 20,
    height: int = 5,
    follow_start: bool = False,
    ref_prefix: str | None = None,
) -> tuple[HostViewport, list[object]]:
    """A controller with content installed and a first frame displayed (so
    ``last_token`` names a real displayed mapping), plus its recording sink."""
    events: list[object] = []
    vp = HostViewport(content_id="doc", on_event=events.append, follow_start=follow_start)
    vp.set_geometry(width, height)
    vp.install(_rows(rows, width, ref_prefix), reason=None)  # mount: no event
    events.clear()  # drop nothing (mount is silent) — defensive
    vp.frame()  # produce a displayed frame → last_token set
    return vp, events


# --- The two-token discipline: clamp / no-op → observed == current -----------


def test_mount_is_silent_no_synthetic_event() -> None:
    """A mount installs content but mints no event (no synthetic mount event, §7)."""
    events: list[object] = []
    vp = HostViewport(content_id="doc", on_event=events.append)
    vp.set_geometry(20, 5)
    vp.install(_rows(20), reason=None)
    assert events == []


def test_clamped_scroll_is_a_no_op_event_with_observed_equal_current() -> None:
    vp, events = _mounted(20)  # top-anchored, offset 0
    displayed = vp.last_token
    assert vp.route_key("up") is True  # clamped at the top — still ours
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, HostViewportEvent)
    assert isinstance(ev.reason, ScrollChange)
    assert ev.observed == displayed  # the frame the input landed on
    assert ev.current == ev.observed  # a true no-op relative to the displayed frame
    assert ev.offset == 0


def test_no_events_before_the_first_display() -> None:
    """Input arriving before any frame is displayed produces NO event — there is
    no observed mapping, and painted never manufactures a tokenless one (§7)."""
    events: list[object] = []
    vp = HostViewport(content_id="doc", on_event=events.append, follow_start=True)
    vp.set_geometry(20, 5)
    vp.install(_rows(30), reason=None)  # content, but no frame() yet
    # A whole batch of transitions before the first display:
    vp.route_key("down")
    vp.route_key("end")
    vp.route_wheel(MouseButton.SCROLL_UP)
    vp.cursor_to(4)
    vp.route_quit()
    assert events == []  # nothing displayed → nothing observed → nothing delivered
    # Once a frame is displayed, the seam comes alive.
    vp.frame()
    vp.route_key("up")
    assert len(events) == 1


def test_drain_batch_observed_stays_the_displayed_frame_current_stays_live() -> None:
    """The exact drain-batch shape (Surface.run drains several inputs before a
    repaint): observed stays the last displayed frame across the batch while
    current tracks the live adapter — so a later event carries observed !=
    current, and that is correct causality, not a bug (§7)."""
    vp, events = _mounted(30, follow_start=False)  # top, offset 0
    displayed = vp.last_token
    # Two inputs, NO frame() between them (one drain batch).
    vp.route_key("end")  # engage follow → bottom
    vp.route_key("end")  # already at the bottom — a clamped no-op *this* transition
    assert [e.observed for e in events] == [displayed, displayed]  # both landed on frame 0
    # First event moved the viewport to the bottom → current advanced off the
    # displayed frame; observed != current is legitimate.
    assert events[0].current != events[0].observed
    # Second 'end' is a no-op *relative to the already-installed state*, but the
    # displayed frame is still frame 0, so it too reports the live bottom mapping.
    assert events[1].current == events[0].current  # same live mapping both report
    assert events[1].current != events[1].observed  # still != the displayed frame


def test_quit_current_is_the_live_mapping_not_a_copy_of_observed() -> None:
    """route_quit must report the LIVE installed mapping as current — never copy
    observed — so a quit after an in-batch scroll carries the true divergence."""
    vp, events = _mounted(30)  # top, offset 0
    displayed = vp.last_token
    vp.route_key("down")  # advance the adapter within the batch (no repaint)
    events.clear()
    vp.route_quit()
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, HostQuitEvent)
    assert ev.observed == displayed  # the displayed frame the quit landed on
    assert ev.current == vp.adapter.token()  # the live mapping, not a copy of observed
    assert ev.current != ev.observed  # the scroll moved the adapter off frame 0


# --- Each ViewportChange reason minted from its transition -------------------


def test_scroll_in_the_middle_mints_scroll_change() -> None:
    vp, events = _mounted(20)
    vp.route_key("down")
    ev = events[-1]
    assert isinstance(ev, HostViewportEvent)
    assert isinstance(ev.reason, ScrollChange)
    assert ev.following is False
    assert ev.current != ev.observed  # the viewport moved
    assert ev.offset == 1


def test_end_key_mints_follow_change_engaged() -> None:
    vp, events = _mounted(20)
    vp.route_key("end")
    ev = events[-1]
    assert isinstance(ev, HostViewportEvent)
    assert isinstance(ev.reason, FollowChange)
    assert ev.following is True
    assert ev.is_at_bottom is True


def test_scroll_up_from_following_mints_follow_change_disengaged() -> None:
    vp, events = _mounted(20, follow_start=True)
    # Seed a following frame at the bottom, then scroll off the tail.
    vp.route_key("end")
    events.clear()
    vp.route_key("up")
    ev = events[-1]
    assert isinstance(ev, HostViewportEvent)
    assert isinstance(ev.reason, FollowChange)  # follow was involved (disengaged)
    assert ev.following is False
    assert ev.is_at_bottom is False


def test_cursor_to_mints_cursor_follow_change() -> None:
    vp, events = _mounted(20)
    vp.cursor_to(7)
    ev = events[-1]
    assert isinstance(ev, HostViewportEvent)
    assert isinstance(ev.reason, CursorFollowChange)
    assert ev.cursor_row == 7


def test_resize_mints_resize_change_through_the_surface() -> None:
    events: list[object] = []
    app = HostSurface(
        render=lambda w, h: _rows(20, w), accepts_height=False, on_host_event=events.append
    )
    harness = TestSurface(app, width=20, height=8)
    harness.run_to_completion()
    events.clear()
    harness.resize(20, 5)  # height-only → re-slice, one ResizeChange
    assert len(events) == 1
    ev = events[0]
    assert isinstance(ev, HostViewportEvent)
    assert isinstance(ev.reason, ResizeChange)


def test_width_resize_mints_one_resize_change() -> None:
    events: list[object] = []
    app = HostSurface(
        render=lambda w, h: _rows(20, w), accepts_height=False, on_host_event=events.append
    )
    harness = TestSurface(app, width=20, height=8)
    harness.run_to_completion()
    events.clear()
    harness.resize(30, 8)  # width change → re-render + reconcile, one ResizeChange
    assert len(events) == 1
    assert isinstance(events[0], HostViewportEvent)
    assert isinstance(events[0].reason, ResizeChange)


# --- Hit and quit events carry the two tokens -------------------------------


def test_hit_event_carries_two_tokens_and_the_hit() -> None:
    events: list[object] = []
    app = HostSurface(
        render=lambda w, h: _rows(20, w, "fact"),
        accepts_height=False,
        on_host_event=events.append,
    )
    TestSurface(app, width=20, height=10).run_to_completion()
    displayed = app._vp.last_token
    app.on_mouse(MouseEvent(MouseAction.PRESS, MouseButton.LEFT, 0, 2))
    hit_events = [e for e in events if isinstance(e, HostHitEvent)]
    assert len(hit_events) == 1
    ev = hit_events[0]
    assert ev.observed == displayed
    assert ev.hit.ref == "fact:2"  # the content row's ref (offset 0)


def test_quit_key_mints_quit_event() -> None:
    events: list[object] = []
    app = HostSurface(
        render=lambda w, h: _rows(20, w), accepts_height=False, on_host_event=events.append
    )
    TestSurface(app, width=20, height=8).run_to_completion()
    displayed = app._vp.last_token
    app.on_key("q")
    quit_events = [e for e in events if isinstance(e, HostQuitEvent)]
    assert len(quit_events) == 1
    ev = quit_events[0]
    assert ev.observed == displayed
    assert ev.current == ev.observed  # a quit performs no viewport transition


# --- Honest silence: the offered arm owns no viewport -----------------------


def test_offered_arm_sink_never_fires() -> None:
    """The offered arm's renderer owns the frame, so painted holds no viewport —
    a declared sink is legal and receives zero calls (§7)."""
    events: list[object] = []
    app = HostSurface(
        render=lambda w, h: Block.empty(w, h or 0),
        accepts_height=True,
        on_host_event=events.append,
    )
    TestSurface(app, width=20, height=8).run_to_completion()
    app.on_key("down")  # the offered arm routes no scroll
    app.on_key("q")  # and mints no quit event
    app.on_mouse(MouseEvent(MouseAction.PRESS, MouseButton.LEFT, 0, 2))
    assert events == []


# --- Handler-exception propagation through the production run loop -----------


class _DelayedKeyKeyboard:
    """A keyboard that yields nothing on the first drain (so the first frame
    displays), then the key once, then EOF. The delay matters: input arriving
    before any frame is displayed produces no event (§7), so the key must land
    on a *later* drain batch to exercise the sink through the real loop."""

    def __init__(self, key: str) -> None:
        self._key = key
        self._calls = 0

    def __enter__(self) -> _DelayedKeyKeyboard:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def get_input(self) -> str | None:
        # Call 1 (first drain batch): None → the loop renders the first frame.
        # Call 2 (second batch): the key → on_key after a frame is displayed.
        self._calls += 1
        return self._key if self._calls == 2 else None


@pytest.mark.asyncio
async def test_handler_exception_propagates_through_run_loop() -> None:
    """A sink that raises fails the active host delivery loud: the exception
    escapes ``Surface.run()`` and its finally restores the terminal — never
    swallowed, never rerouted to ``emit`` (§7)."""

    def boom(_event: object) -> None:
        raise RuntimeError("handler boom")

    app = HostSurface(render=lambda w, h: _rows(20, w), accepts_height=False, on_host_event=boom)
    TestSurface(app, width=20, height=8)  # installs a hermetic StringIO writer
    app._writer.size = lambda: (20, 8)  # type: ignore[method-assign]
    app._keyboard = _DelayedKeyKeyboard("down")  # type: ignore[assignment]

    restored: list[str] = []
    for name in ("exit_alt_screen", "show_cursor"):
        original = getattr(app._writer, name)

        def spy(*args: object, _n: str = name, _o=original, **kwargs: object) -> object:
            restored.append(_n)
            return _o(*args, **kwargs)

        setattr(app._writer, name, spy)

    with pytest.raises(RuntimeError, match="handler boom"):
        await app.run()

    assert "exit_alt_screen" in restored  # terminal restored on the loud escape
    assert "show_cursor" in restored
