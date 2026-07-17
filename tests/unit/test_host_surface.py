"""Unit tests for the interactive host rung (HOST_RUNG_DESIGN §6, S4).

``HostSurface`` mounts a renderer binding into an alt-screen ``Surface`` — the
fourth delivery. Driven through ``TestSurface`` (no real terminal), these pin:

* the **omitted arm** — natural-height render sliced by the adapter, scroll-key
  routing, follow / at-bottom intent, the evidence row on overflow;
* the **offered arm** — an exact ``H``-row frame each dirty frame, and the loud
  ``ContractError`` when the renderer breaks exactness;
* the **resize matrix** — a height-only resize re-slices with *no renderer call*
  (proven by counting invocations); a width change re-renders;
* the **event-order hazard** — a resize interleaved between paint and a queued
  mouse event resolves stale (dropped), never through the new geometry.
"""

from __future__ import annotations

import pytest

from painted.capabilities import current_capabilities
from painted.core.block import Block
from painted.core.cell import Style
from painted.core.compose import join_vertical
from painted.core.errors import ContractError
from painted.core.writer import ColorDepth
from painted.host import FrameRegion
from painted.mouse import MouseAction, MouseButton, MouseEvent
from painted.tui import HostSurface, TestSurface


class _QueueKeyboard:
    """A no-op keyboard context manager for driving the real ``Surface.run()``."""

    def __enter__(self) -> _QueueKeyboard:
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def get_input(self) -> None:
        return None


def _rows(n: int, width: int = 24, ref_prefix: str | None = None) -> Block:
    """``n`` distinct content rows; each carries a ref when ``ref_prefix`` is set."""
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


def _click(x: int, y: int) -> MouseEvent:
    return MouseEvent(MouseAction.PRESS, MouseButton.LEFT, x, y)


# --- The omitted arm ---------------------------------------------------------


def test_omitted_arm_offers_natural_sizing_and_slices_to_frame() -> None:
    calls: list[tuple[int, int | None]] = []

    def render(width: int, height: int | None) -> Block:
        calls.append((width, height))
        return _rows(20, width)

    app = HostSurface(render=render, accepts_height=False)
    frames = TestSurface(app, width=24, height=10).run_to_completion()

    # The omitted arm is offered natural sizing — height=None, never an integer.
    assert calls == [(24, None)]
    # Frame is exactly the allocation; overflow (20 > 10) reserves one evidence row.
    assert len(frames[-1].lines) == 10
    assert "more rows" in frames[-1].text
    assert app._adapter is not None
    assert app._adapter.viewport.offset == 0


def test_omitted_arm_scroll_keys_route_through_adapter() -> None:
    calls: list[tuple[int, int | None]] = []

    def render(width: int, height: int | None) -> Block:
        calls.append((width, height))
        return _rows(20, width)

    app = HostSurface(render=render, accepts_height=False)
    TestSurface(app, width=24, height=10).run_to_completion()
    assert app._adapter is not None

    app.on_key("down")
    assert app._adapter.viewport.offset == 1
    app.on_key("page_down")
    down_offset = app._adapter.viewport.offset
    assert down_offset > 1
    app.on_key("end")
    assert app._adapter.following is True
    assert app._adapter.viewport.is_at_bottom
    app.on_key("home")
    assert app._adapter.viewport.offset == 0
    assert app._adapter.following is False

    # Scrolling never re-renders — it is pure re-slice territory.
    assert calls == [(24, None)]


def test_omitted_arm_scroll_wheel_moves_viewport() -> None:
    app = HostSurface(render=lambda w, h: _rows(30, w), accepts_height=False)
    TestSurface(app, width=24, height=10).run_to_completion()
    assert app._adapter is not None

    app.on_mouse(MouseEvent(MouseAction.SCROLL, MouseButton.SCROLL_DOWN, 0, 0))
    assert app._adapter.viewport.offset > 0
    scrolled = app._adapter.viewport.offset
    app.on_mouse(MouseEvent(MouseAction.SCROLL, MouseButton.SCROLL_UP, 0, 0))
    assert app._adapter.viewport.offset < scrolled


def test_quit_keys_stop_the_loop() -> None:
    app = HostSurface(render=lambda w, h: _rows(20, w), accepts_height=False)
    TestSurface(app, width=24, height=10).run_to_completion()
    assert app._running is True
    app.on_key("q")
    assert app._running is False


# --- The offered arm ---------------------------------------------------------


def test_offered_arm_offers_H_and_paints_exact_frame() -> None:
    calls: list[tuple[int, int | None]] = []

    def render(width: int, height: int | None) -> Block:
        calls.append((width, height))
        assert height is not None
        return Block.empty(width, height)

    app = HostSurface(render=render, accepts_height=True)
    frames = TestSurface(app, width=24, height=8).run_to_completion()

    # The offered arm gets the full frame height (the host draws no chrome, §5).
    assert calls == [(24, 8)]
    assert len(frames[-1].lines) == 8


def test_offered_arm_exactness_violation_is_loud() -> None:
    def bad(width: int, height: int | None) -> Block:
        # One row too many — the offered arm must return exactly H (§5).
        return Block.empty(width, (height or 0) + 1)

    app = HostSurface(render=bad, accepts_height=True)
    with pytest.raises(ContractError):
        TestSurface(app, width=24, height=8).run_to_completion()


def test_offered_arm_ignores_scroll_keys() -> None:
    calls: list[int | None] = []

    def render(width: int, height: int | None) -> Block:
        calls.append(height)
        return Block.empty(width, height or 0)

    app = HostSurface(render=render, accepts_height=True)
    TestSurface(app, width=24, height=8).run_to_completion()
    app.on_key("down")  # the renderer owns internal scroll on this arm
    assert app._dirty is False  # no re-render was requested


# --- The resize matrix (§6) --------------------------------------------------


def test_height_only_resize_reslices_without_a_renderer_call() -> None:
    calls: list[tuple[int, int | None]] = []

    def render(width: int, height: int | None) -> Block:
        calls.append((width, height))
        return _rows(20, width)

    app = HostSurface(render=render, accepts_height=False)
    harness = TestSurface(app, width=24, height=10)
    harness.run_to_completion()
    assert calls == [(24, None)]  # one render at construction

    # Height-only resize: the omitted-height arm of the matrix — re-slice only.
    harness.resize(24, 6)
    assert calls == [(24, None)]  # NO new renderer call
    assert app._height == 6

    # A width change is always semantic — re-render, then reconcile the anchor.
    harness.resize(30, 6)
    assert calls == [(24, None), (30, None)]


def test_offered_arm_resize_re_renders_with_new_H() -> None:
    calls: list[int | None] = []

    def render(width: int, height: int | None) -> Block:
        calls.append(height)
        return Block.empty(width, height or 0)

    app = HostSurface(render=render, accepts_height=True)
    harness = TestSurface(app, width=24, height=8)
    harness.run_to_completion()
    assert calls == [8]

    harness.resize(24, 5)  # SIGWINCH on the offered arm → the budget changed
    app.render()  # the dirty frame the loop would paint next
    assert calls == [8, 5]


# --- The event-order hazard (§6) ---------------------------------------------


def test_click_resolves_against_the_displayed_frame() -> None:
    app = HostSurface(render=lambda w, h: _rows(20, w, "fact"), accepts_height=False)
    TestSurface(app, width=24, height=10).run_to_completion()

    # Content row 2 is at frame y=2 (offset 0); it carries ref fact:2.
    app.on_mouse(_click(0, 2))
    hit = app.hits[-1]
    assert hit.stale is False
    assert hit.region is FrameRegion.CONTENT
    assert hit.ref == "fact:2"
    assert hit.content_xy == (0, 2)

    # The last frame row (y=9) is the host-authored evidence row (20 > 10).
    app.on_mouse(_click(0, 9))
    assert app.hits[-1].region is FrameRegion.EVIDENCE


def test_resize_between_paint_and_queued_click_drops_stale_event() -> None:
    """The SIGWINCH drain hazard, closed: a mouse event observed against the
    displayed frame, arriving after a resize mutated the geometry, resolves
    stale — never translated through the new geometry against old content."""
    app = HostSurface(render=lambda w, h: _rows(20, w, "fact"), accepts_height=False)
    harness = TestSurface(app, width=24, height=10)
    harness.run_to_completion()  # paints frame T0 (offset 0, frame height 10)

    # Interleave a resize between the paint and the queued click — the buffers
    # swap and geometry changes, but no repaint has happened yet.
    harness.resize(24, 6)

    app.on_mouse(_click(0, 2))
    hit = app.hits[-1]
    assert hit.stale is True  # dropped
    assert hit.ref is None
    assert hit.content_xy is None


# --- The capability bracket (§9.3) — active on every render path ------------


def test_omitted_arm_layout_render_runs_under_the_surface_capability_bracket() -> None:
    """The natural render happens in ``layout()`` — outside the run loop's
    per-frame bracket — so HostSurface must install the Surface capability
    bracket itself, on the initial mount *and* every width re-render. A
    capability-sensitive renderer proves it: a NONE-depth Surface resolves
    ``color=False``, while the ambient default is ``True``."""
    seen: list[bool] = []

    def render(width: int, height: int | None) -> Block:
        seen.append(current_capabilities().color)
        return _rows(20, width)

    # Sanity: outside any Surface, the ambient capability is color=True.
    assert current_capabilities().color is True

    app = HostSurface(render=render, accepts_height=False)
    harness = TestSurface(app, width=24, height=10, color_depth=ColorDepth.NONE)
    assert seen == [False]  # the layout-time render saw the Surface's caps

    harness.resize(30, 10)  # width change → re-render, still bracketed
    assert seen == [False, False]

    # And the bracket is scoped — it does not leak past the render.
    assert current_capabilities().color is True


# --- Terminal restoration on a loud escape (§5) ------------------------------


@pytest.mark.asyncio
async def test_offered_arm_contract_error_restores_terminal() -> None:
    """An offered-arm exactness violation escapes the *production* run loop
    loud: the alt screen is exited and the cursor/keyboard restored by
    ``Surface.run()``'s finally, and the ContractError still propagates."""

    def bad(width: int, height: int | None) -> Block:
        return Block.empty(width, (height or 0) + 1)  # one row too many

    app = HostSurface(render=bad, accepts_height=True)
    TestSurface(app, width=20, height=6)  # installs a hermetic StringIO writer
    app._writer.size = lambda: (20, 6)  # type: ignore[method-assign]
    app._keyboard = _QueueKeyboard()  # type: ignore[assignment]

    events: list[str] = []
    for name in ("enter_alt_screen", "exit_alt_screen", "hide_cursor", "show_cursor"):
        original = getattr(app._writer, name)

        def spy(*args: object, _n: str = name, _o=original, **kwargs: object) -> object:
            events.append(_n)
            return _o(*args, **kwargs)

        setattr(app._writer, name, spy)

    with pytest.raises(ContractError):
        await app.run()

    # Restored, in order: entered then exited the alt screen; cursor shown again.
    assert "exit_alt_screen" in events
    assert "show_cursor" in events
    assert events.index("enter_alt_screen") < events.index("exit_alt_screen")


def test_no_displayed_frame_yet_means_no_resolution() -> None:
    app = HostSurface(render=lambda w, h: _rows(20, w, "fact"), accepts_height=False)
    # Construct without running the loop: layout ran (adapter built) but render
    # has not, so there is no displayed-frame token to resolve against.
    TestSurface(app, width=24, height=10)
    app._last_token = None
    app.on_mouse(_click(0, 2))
    assert app.hits == []  # nothing resolved — no frame was displayed
