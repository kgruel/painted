"""Laws for the alt-screen live tier: StreamSurface + CliRunner._run_live_surface.

StreamSurface is the cli-private adapter that hosts a `fetch_stream` on a
Surface alt screen (the 'sustained' tier of the two-tier live contract, see
docs/LIVE_DELIVERY_DESIGN.md). These tests pin the genuinely new logic without
a terminal:

  - stream hosting: states are consumed to exhaustion, the last is retained,
    pause gates consumption, stream failures are captured (not raised);
  - ref_schemes= evaluation (docs/RENDERER_CONTRACT_DESIGN.md §7): eager, once
    per successful fetch event, in _consume() — never lazily at render time,
    never keyed by state identity. The resolved (state, schemes) pair travels
    as one atomic unit, so state and schemes can never be observed out of
    sync (a repeated-identity fetch, a coalesced state, a stream that
    exhausts mid-flight all stay self-consistent);
  - render(): paints the current frame, captures render failures, blanks when
    there is no frame yet;
  - keys: q / ctrl-c quit, space toggles pause;
  - _run_live_surface: deposits the final frame (or the failure) and returns the
    right exit code, and the delivery gate only takes the alt-screen path on a
    real TTY.

The frame-bracket lifecycle matrix (§11 scope hygiene) drives the PRODUCTION
seam wherever it can: successful render/flush/resize/quit go through
TestSurface, whose _render_and_capture() mirrors Surface.run()'s own
`with self._frame_scope(): ...` bracket — a manual `with surf._frame_scope():`
call in a test would stay green even if that production wiring were deleted,
which is exactly what TestSurface exercises for real. A renderer/flush
exception and a real cancellation need the actual async loop (TestSurface is
synchronous and never calls the real _flush()), so those three drive
asyncio.run(surf.run()) directly, against a Writer over an in-memory stream —
still the production bracket at tui/surface.py, never a manual re-entry.
Evaluation itself (fetch-time, in _consume()) is exercised directly via
asyncio.run(surf._consume()), mirroring tests/unit/test_live_stream.py.
"""

from __future__ import annotations

import asyncio
import io
import os

import pytest

from painted import Block, CliContext, Fidelity, RefScheme, Style, Zoom
from painted.cli.runner import CliRunner
from painted.cli.stream_surface import StreamSurface
from painted.cli.types import OutputMode
from painted.core.writer import Writer
from painted.refs import current_ref_schemes
from painted.tui import Buffer, Surface, TestSurface
from painted.tui.testing import buffer_to_lines

from tests.helpers import static_ctx


# --- Fixtures: a trivial render and parameterizable streams ---


def _surface_render(state: object, width: int) -> Block:
    """The StreamSurface render callback shape (§6): (state, buffer_width) →
    Block. In production this is the runner's adapted closure; here a stand-in
    that ignores width, so a plain frame is captured."""
    return Block.text(str(state), Style())


def _legacy_render(state: object, fidelity: Fidelity, width: int | None) -> Block:
    """The CliRunner ``renderer=`` shape (data, fidelity, width) — used by the
    _run_live_surface deposit tests, which drive the runner, not the surface
    callback."""
    return Block.text(str(state), Style())


def _stream_of(states, *, fail_after=None):
    """An async stream factory yielding `states`; optionally raises mid-flight."""

    async def gen():
        for i, s in enumerate(states):
            if fail_after is not None and i == fail_after:
                raise RuntimeError("stream boom")
            yield s

    return gen


def _make_surface(
    states,
    *,
    fail_after=None,
    render=_surface_render,
    live_meter=False,
    resolve_ref_schemes=None,
) -> StreamSurface:
    return StreamSurface(
        render=render,
        fetch_stream=_stream_of(states, fail_after=fail_after),
        live_meter=live_meter,
        resolve_ref_schemes=resolve_ref_schemes,
    )


def _recording_resolver(name: str = "fact"):
    """A ``resolve_ref_schemes=`` callable that records every state it was
    actually invoked against — makes "evaluated once per fetch event" an
    assertion instead of an inference."""
    calls: list[object] = []

    def resolve(state: object) -> tuple[RefScheme, ...]:
        calls.append(state)
        return (RefScheme(name, lambda v: f"https://x/{state}/{v}"),)

    resolve.calls = calls  # type: ignore[attr-defined]
    return resolve


# --- Stream hosting ---


def test_consumes_stream_to_exhaustion():
    surf = _make_surface(["a", "b", "c"])
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.last_state == "c"
    assert surf.error is None
    assert surf._running is False  # exhaustion quits the loop (finally → quit)


def test_stream_error_is_captured_as_fetch():
    surf = _make_surface(["a", "b"], fail_after=1)
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.error_kind == "fetch"
    assert isinstance(surf.error, RuntimeError)
    assert surf.last_state == "a"  # last good state survives for the deposit
    assert surf._running is False


def test_paused_consumer_stops_consuming_then_resumes():
    """Pause = stop pulling the iterator. Nothing advances while paused; on
    resume the stream drains and the loop exits at exhaustion."""
    pulls: list[str] = []

    async def gen():
        for s in ["a", "b", "c"]:
            pulls.append(s)
            yield s

    surf = StreamSurface(render=_surface_render, fetch_stream=gen)

    async def drive() -> int:
        surf._running = True
        surf._paused = True
        task = asyncio.create_task(surf._consume())
        await asyncio.sleep(0.05)
        while_paused = len(pulls)
        surf._paused = False
        await task  # resumes, drains, exits at exhaustion
        return while_paused

    while_paused = asyncio.run(drive())
    assert while_paused == 0  # the iterator was never pulled while paused
    assert pulls == ["a", "b", "c"]  # all pulled after resume
    assert surf.last_state == "c"


# --- ref_schemes= evaluation (§7): eager, once per fetch event, in _consume() ---
#
# This is the P1 fix: no identity cache. Evaluation happens exactly once per
# successful fetch — never once per distinct state (a repeated-identity fetch
# is evaluated twice), never deferred to render time (a coalesced state that
# never renders was still evaluated, at its own fetch). The (state, schemes)
# pair is carried as one atomic write into `_frame`/`_last_frame`, so a reader
# can never observe a state whose schemes came from a different fetch.


def test_evaluates_once_per_successful_fetch():
    resolver = _recording_resolver()
    surf = _make_surface(["a", "b", "c"], resolve_ref_schemes=resolver)
    surf._running = True
    asyncio.run(surf._consume())
    assert resolver.calls == ["a", "b", "c"]


def test_repeated_identity_fetch_evaluates_every_time():
    """P1 failure (a): a stream that yields the SAME object twice — mutated
    in place between fetches, or an interned scalar — must still be
    evaluated on the second fetch. There is no cache to key by identity."""
    box = ["shared"]  # a mutable object mutated in place between fetches

    async def gen():
        yield box
        box[0] = "mutated"
        yield box  # the SAME object, mutated — still a new fetch event

    resolver = _recording_resolver()
    surf = StreamSurface(render=_surface_render, fetch_stream=gen, resolve_ref_schemes=resolver)
    surf._running = True
    asyncio.run(surf._consume())
    assert len(resolver.calls) == 2  # evaluated on both fetches, despite `is` identity
    assert resolver.calls[0] is resolver.calls[1] is box  # literally the same object both times


def test_a_coalesced_states_fault_still_surfaces():
    """P1 failure (b): a state that would have been coalesced away — never
    chosen to render because a newer one immediately supersedes it — was
    still evaluated at ITS OWN fetch. Its callable's fault surfaces (it
    aborts the consumer loop before the next state is even fetched), instead
    of silently disappearing because a later state won the race."""

    def resolver(state):
        if state == "a":
            raise RuntimeError("a boom")
        return ()  # "b" would resolve cleanly, but is never reached

    surf = _make_surface(["a", "b"], resolve_ref_schemes=resolver)
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.error_kind == "render"
    assert isinstance(surf.error, RuntimeError)
    assert str(surf.error) == "a boom"
    # "a"'s pair never completed (atomicity: an incomplete evaluation must
    # not partially update last_state without matching schemes), and "b" was
    # never even fetched — the fault stopped the loop before either landed.
    assert surf.last_state is None


def test_raising_resolver_is_classified_as_render_not_fetch():
    """The fault is a declaration-time fault (§7), classified as a
    render-phase fault regardless of which task detected it — never
    misattributed to _consume()'s own "the stream raised" classification."""

    def boom(state):
        raise RuntimeError("scheme boom")

    surf = _make_surface(["x"], resolve_ref_schemes=boom)
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.error_kind == "render"  # not "fetch"
    assert isinstance(surf.error, RuntimeError)
    assert surf._running is False


def test_a_resolver_fault_does_not_corrupt_a_prior_successful_fetch():
    """last_state/last_ref_schemes hold the last SUCCESSFUL pair — a fault on
    a later fetch doesn't overwrite what a prior good fetch already carried."""

    def resolver(state):
        if state == "b":
            raise RuntimeError("b boom")
        return (RefScheme("fact", lambda v: v),)

    surf = _make_surface(["a", "b"], resolve_ref_schemes=resolver)
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.last_state == "a"
    assert surf.last_ref_schemes is not None
    assert [s.name for s in surf.last_ref_schemes] == ["fact"]


def test_last_state_and_last_ref_schemes_never_desync():
    """The P1 headline guarantee (failure (c)): last_state and
    last_ref_schemes are two reads of the SAME atomic pair — across a
    multi-state stream, every observation is self-consistent, including the
    final one after the stream exhausts mid-flight (no render ever had to
    happen for the pair to be correct)."""
    resolver = _recording_resolver()
    surf = _make_surface(["a", "b", "c"], resolve_ref_schemes=resolver)
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.last_state == "c"
    assert surf.last_ref_schemes is not None
    assert [s.name for s in surf.last_ref_schemes] == ["fact"]
    # The pair is literally the same object _consume() constructed — not two
    # attributes that happened to agree.
    assert surf._last_frame == ("c", surf.last_ref_schemes)


def test_no_resolver_declared_carries_none_schemes():
    surf = _make_surface(["a"])  # resolve_ref_schemes not declared
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.last_state == "a"
    assert surf.last_ref_schemes is None


def test_empty_schemes_result_is_carried_as_an_empty_tuple_not_none():
    """An explicit empty declaration (ref_schemes=[]) still installs a
    (disabling) bracket — it must not collapse to "nothing declared"."""
    surf = _make_surface(["a"], resolve_ref_schemes=lambda state: ())
    surf._running = True
    asyncio.run(surf._consume())
    assert surf.last_ref_schemes == ()  # not None


# --- render() ---


def test_render_paints_current_state():
    surf = _make_surface(["hello"])
    surf._buf = Buffer(10, 1)
    surf._frame = ("hello", None)
    surf.render()
    assert buffer_to_lines(surf._buf)[0].startswith("hello")


def test_render_exception_is_captured_as_render():
    def boom(state, width):
        raise ValueError("render boom")

    surf = _make_surface(["x"], render=boom)
    surf._buf = Buffer(10, 1)
    surf._running = True
    surf._frame = ("x", None)
    surf.render()
    assert surf.error_kind == "render"
    assert isinstance(surf.error, ValueError)
    assert surf._running is False  # a render failure stops the loop


def test_render_without_state_is_blank():
    surf = _make_surface([])
    surf._buf = Buffer(5, 1)
    surf.render()  # _frame is still None
    assert buffer_to_lines(surf._buf) == ["     "]


def test_render_offers_buffer_width_per_frame():
    """The surface offers its buffer's *current* width each frame (§6): a
    resize re-creates _buf at the new geometry, so the next frame's offer
    tracks it rather than a once-captured context width."""
    offered: list[int] = []

    def capture(state, width):
        offered.append(width)
        return Block.text(str(state), Style())

    surf = _make_surface(["x"], render=capture)
    surf._frame = ("x", None)
    surf._buf = Buffer(30, 1)
    surf.render()
    surf._buf = Buffer(52, 1)  # the alt screen resized
    surf.render()
    assert offered == [30, 52]


# --- _frame_scope(): installs an already-resolved pair, never evaluates ---


def test_frame_scope_is_a_noop_before_any_fetch():
    surf = _make_surface(["x"], resolve_ref_schemes=_recording_resolver())
    with surf._frame_scope():
        pass  # a usable no-op — nothing has been fetched yet


def test_frame_scope_is_a_noop_when_nothing_was_declared():
    surf = _make_surface(["x"])  # resolve_ref_schemes not declared
    surf._frame = ("x", None)
    with surf._frame_scope():
        assert current_ref_schemes() == {}


def test_frame_scope_installs_the_carried_schemes():
    surf = _make_surface(["x"])
    surf._frame = ("x", (RefScheme("fact", lambda v: v),))
    with surf._frame_scope():
        assert set(current_ref_schemes()) == {"fact"}
    assert current_ref_schemes() == {}  # released on exit


def test_frame_scope_installs_an_empty_bracket_for_an_empty_declaration():
    """schemes=() (an explicit empty declaration) still installs — it
    disables ambient resolution, distinct from schemes=None (undeclared)."""
    from painted.refs import use_refs

    surf = _make_surface(["x"])
    surf._frame = ("x", ())
    with use_refs(RefScheme("ambient", lambda v: v)):
        with surf._frame_scope():
            assert current_ref_schemes() == {}  # ambient replaced by the empty declaration
        assert set(current_ref_schemes()) == {"ambient"}  # restored on exit


def test_frame_scope_never_calls_the_resolver():
    """Evaluation moved to _consume() (§7 / P1) — _frame_scope() only reads
    the already-resolved pair, however many times it's entered."""
    resolver = _recording_resolver()
    surf = _make_surface(["x"], resolve_ref_schemes=resolver)
    surf._frame = ("x", (RefScheme("fact", lambda v: v),))
    for _ in range(3):
        with surf._frame_scope():
            pass
    assert resolver.calls == []  # never invoked from here, not even once


# --- The frame-bracket lifecycle matrix (§11 scope hygiene) ---
#
# render/flush/resize/quit drive through TestSurface, whose _render_and_
# capture() wraps `with self.surface._frame_scope(): ...` — the SAME
# production bracket Surface.run() enters (tui/surface.py). A manual
# `with surf._frame_scope():` call in a test would stay green even if that
# wiring were deleted; going through TestSurface would not (verified by
# hand: commenting out the `with` in testing.py turns these red).
#
# A renderer/flush exception and a real cancellation need the actual async
# loop — TestSurface is synchronous and never calls the real _flush() — so
# those three drive asyncio.run(surf.run()) against an in-memory Writer,
# which is Surface.run()'s own bracket, not a re-implementation of it.


def _stub_run_surface(surf: StreamSurface) -> None:
    """Point a StreamSurface at an in-memory terminal so its real async
    run() loop can execute headless (no tty, no alt-screen side effects
    that would leak into the test process)."""
    surf._writer = Writer(io.StringIO())


def test_scope_is_active_during_render_via_test_surface():
    """render() runs *inside* the installed bracket — driven through the
    real harness wiring, not a manual context-manager entry."""
    seen: dict[str, set[str]] = {}

    def render_and_peek(state, width):
        seen["schemes"] = set(current_ref_schemes())
        return Block.text(str(state), Style())

    surf = StreamSurface(render=render_and_peek, fetch_stream=_stream_of([]))
    surf._frame = ("x", (RefScheme("fact", lambda v: f"https://x/{v}"),))
    harness = TestSurface(surf, width=10, height=1, write_ansi=True)
    harness.run_to_completion()
    assert seen["schemes"] == {"fact"}
    assert current_ref_schemes() == {}  # released once the bracket exits


def test_scope_spans_through_serialization_via_test_surface():
    """The bracket must still be active when refs actually resolve — during
    write, not just during paint — proven by a real OSC 8 hyperlink landing
    in the harness's captured ANSI output."""
    surf = StreamSurface(
        render=lambda s, w: Block.text(str(s), Style(), ref="fact:01"), fetch_stream=_stream_of([])
    )
    surf._frame = ("x", (RefScheme("fact", lambda v: f"https://loops.dev/f/{v}"),))
    harness = TestSurface(surf, width=20, height=1, write_ansi=True)
    harness.run_to_completion()
    assert "\x1b]8;;https://loops.dev/f/01" in harness.stream.getvalue()


def test_scope_releases_after_a_swallowed_renderer_exception_via_test_surface():
    """render() catches its own exception internally (self.error) — the
    harness's bracket still exits cleanly on this "successful" pass."""

    def boom(state, width):
        raise ValueError("render boom")

    surf = StreamSurface(render=boom, fetch_stream=_stream_of([]))
    surf._running = True
    surf._frame = ("x", (RefScheme("fact", lambda v: v),))
    harness = TestSurface(surf, width=10, height=1)
    harness.run_to_completion()
    assert current_ref_schemes() == {}
    assert surf.error_kind == "render"
    assert isinstance(surf.error, ValueError)


def test_resize_does_not_change_the_carried_schemes_via_test_surface():
    """A resize re-creates the buffer and forces a re-render of the SAME
    frame pair — no new fetch, so no re-evaluation is even possible (the
    resolver isn't called from here at all — see test_frame_scope_never_
    calls_the_resolver). This proves the bracket still installs correctly
    across a real resize driven through the harness."""
    seen: list[set[str]] = []

    def render_and_peek(state, width):
        seen.append(set(current_ref_schemes()))
        return Block.text(str(state), Style())

    surf = StreamSurface(render=render_and_peek, fetch_stream=_stream_of([]))
    surf._frame = ("x", (RefScheme("fact", lambda v: v),))
    harness = TestSurface(surf, width=10, height=1)
    harness.run_to_completion()
    harness.resize(20, 2)
    surf._dirty = True
    harness._render_and_capture([])
    assert seen == [{"fact"}, {"fact"}]  # the bracket installed on both frames


def test_frame_scope_releases_cleanly_when_quit_is_triggered_mid_run():
    """quit() (via 'q') stops future frames, but the bracket for whatever
    frame is still in flight when it fires still installs and releases
    cleanly — peeked from inside render() so the assertion is sensitive to
    the bracket's presence, not just its absence of a leak."""
    seen: list[set[str]] = []

    def render_and_peek(state, width):
        seen.append(set(current_ref_schemes()))
        return Block.text(str(state), Style())

    surf = StreamSurface(render=render_and_peek, fetch_stream=_stream_of([]))
    surf._frame = ("x", (RefScheme("fact", lambda v: v),))
    harness = TestSurface(surf, width=10, height=1, input_queue=["q"])
    harness.run_to_completion()
    assert surf._running is False  # q quit the loop
    assert seen and seen[-1] == {"fact"}  # the in-flight frame's bracket was active
    assert current_ref_schemes() == {}  # and released once the run completed


def test_scope_releases_on_a_real_flush_exception():
    """An exception that genuinely propagates through Surface.run()'s own
    `with self._frame_scope(): render(); _flush()` (unlike a renderer fault,
    which render() swallows) still releases — TestSurface never calls the
    real _flush(), so this drives the actual async loop instead. The
    renderer itself observes the installed scope before the flush ever
    fires, so the assertion is sensitive to the bracket's *presence*, not
    just the absence of a post-exit leak (an unscoped block downstream would
    otherwise satisfy the leak check vacuously)."""
    seen: list[set[str]] = []

    def render_and_peek(state, width):
        seen.append(set(current_ref_schemes()))
        return Block.text(str(state), Style())

    def bad_flush(self):
        # The very first frame renders with no state yet (_frame is still
        # None, render() returns early without calling render_and_peek) —
        # only raise once a real, schemed frame has actually rendered, so
        # the peek above is guaranteed to have fired first.
        if self._frame is not None:
            raise RuntimeError("flush boom")

    async def gen():
        # A single fetch, then hold — an instantly-exhausting stream would
        # race its own quit() against the render this test needs to reach
        # (the consumer's second __anext__() can resolve to StopAsyncIteration
        # without ever yielding control back to the render loop in between,
        # so the frame this test needs to observe never gets a chance to
        # paint before the stream tears itself down). _stop()'s teardown
        # cancels this task regardless of whether it ever wakes from the sleep.
        yield "x"
        await asyncio.sleep(3600)

    resolver = _recording_resolver()
    surf = StreamSurface(render=render_and_peek, fetch_stream=gen, resolve_ref_schemes=resolver)
    _stub_run_surface(surf)

    original_flush = StreamSurface._flush
    StreamSurface._flush = bad_flush  # type: ignore[method-assign]
    try:
        with pytest.raises(RuntimeError, match="flush boom"):
            asyncio.run(surf.run())
    finally:
        StreamSurface._flush = original_flush  # type: ignore[method-assign]
    assert seen and seen[-1] == {"fact"}  # active before the flush that then raised
    assert current_ref_schemes() == {}  # released despite the propagating exception


def test_scope_releases_on_a_real_cancellation():
    """asyncio.CancelledError is a BaseException — render()'s `except
    Exception` doesn't catch it, so it propagates through the bracket. Driven
    through the real Surface.run() loop so the propagation is a genuine
    mid-frame exception inside production's own async task, not a simulated
    one. The renderer observes the installed scope before raising, so the
    assertion is sensitive to the bracket's *presence* (an unscoped block
    downstream would otherwise satisfy the post-exit leak check vacuously)."""
    seen: list[set[str]] = []

    def cancel_mid_render(state, width):
        seen.append(set(current_ref_schemes()))
        raise asyncio.CancelledError()

    async def gen():
        # A single fetch, then hold — an instantly-exhausting stream would
        # race its own quit() against the render this test needs to reach
        # (the loop can exit before ever rendering the fetched frame).
        # _stop()'s teardown cancels this task regardless of whether it
        # ever wakes from the sleep.
        yield "x"
        await asyncio.sleep(3600)

    resolver = _recording_resolver()
    surf = StreamSurface(render=cancel_mid_render, fetch_stream=gen, resolve_ref_schemes=resolver)
    _stub_run_surface(surf)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(surf.run())

    assert seen and seen[-1] == {"fact"}  # active before the cancellation
    assert current_ref_schemes() == {}  # released despite it
    assert resolver.calls == ["x"]  # the fetch was still evaluated eagerly before the cancel


def test_render_skips_when_frame_scope_already_flagged_an_error():
    """render()'s own guard: a scheme-resolution failure recorded before it
    ran (by _consume(), now) must not be stomped by a render that then
    proceeds unscoped."""
    surf = _make_surface(["x"])
    surf._buf = Buffer(10, 1)
    surf._frame = ("x", None)
    surf.error = RuntimeError("already failed")
    surf.error_kind = "render"
    surf.render()
    assert surf.error_kind == "render"
    assert str(surf.error) == "already failed"  # not overwritten by a fresh render
    assert buffer_to_lines(surf._buf) == [" " * 10]  # blanked, nothing painted


# --- The delivery gauge ---


def test_frames_feed_the_gauge(monkeypatch):
    """One render+flush cycle records one cost sample — the meter lives on
    the delivery side of the decoupling, where the cost actually is."""
    monkeypatch.setattr(Surface, "_flush", lambda self: None)  # silence the terminal
    surf = _make_surface(["hello"], live_meter=True)
    surf._buf = Buffer(40, 2)
    surf._frame = ("hello", None)
    surf.render()
    surf._flush()
    assert len(surf.meter._costs) == 1


def test_stateless_frames_are_not_measured(monkeypatch):
    """A flush whose render carried no state contributes no sample."""
    monkeypatch.setattr(Surface, "_flush", lambda self: None)
    surf = _make_surface([], live_meter=True)
    surf._buf = Buffer(40, 2)
    surf.render()  # _frame is still None
    surf._flush()
    assert surf.meter._costs == []


def test_gauge_is_opt_in(monkeypatch):
    """Without live_meter, frames are neither measured nor dressed."""
    monkeypatch.setattr(Surface, "_flush", lambda self: None)
    surf = _make_surface(["hello"])
    surf._buf = Buffer(40, 2)
    surf._frame = ("hello", None)
    surf.render()
    surf._flush()
    assert surf.meter._costs == []


# --- keys ---


@pytest.mark.parametrize("key", ["q", "\x03"])
def test_quit_keys_stop_the_loop(key):
    surf = _make_surface([])
    surf._running = True
    surf.on_key(key)
    assert surf._running is False


def test_space_toggles_pause():
    surf = _make_surface([])
    assert surf._paused is False
    surf.on_key(" ")
    assert surf._paused is True
    surf.on_key(" ")
    assert surf._paused is False


# --- _run_live_surface: deposit + exit codes ---


def _runner(renderer=_legacy_render, **kwargs) -> CliRunner:
    return CliRunner(renderer=renderer, fetch=lambda: None, fetch_stream=_stream_of([]), **kwargs)


def test_deposits_last_frame_on_success(monkeypatch, capsys):
    async def fake_run(self):
        self._last_frame = ("final", None)

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    code = _runner()._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 0
    assert "final" in capsys.readouterr().out  # last frame left in scrollback


def test_deposits_a_none_final_state(monkeypatch, capsys):
    """A final fetched state of None is a real frame — renderer data is
    unconstrained, so the deposit gates on frame *presence*
    (surface.last_frame), never the state payload. A run whose last state is
    None must still get its promised scrollback deposit (and its ref
    bracket), not exit 0 silently."""

    async def fake_run(self):
        self._last_frame = (None, None)

    monkeypatch.setattr(StreamSurface, "run", fake_run)

    rendered: list[object] = []

    def rnd(data, fidelity, width):
        rendered.append(data)
        return Block.text(repr(data), Style())

    code = _runner(renderer=rnd)._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 0
    assert rendered == [None]  # the deposit rendered the None payload
    assert "None" in capsys.readouterr().out


def test_no_fetch_at_all_deposits_nothing(monkeypatch, capsys):
    """The other side of the presence gate: a run where nothing was ever
    fetched has no frame to deposit — last_frame is None, the renderer is
    never called."""

    async def fake_run(self):
        pass  # no fetch event ever happened

    monkeypatch.setattr(StreamSurface, "run", fake_run)

    rendered: list[object] = []

    def rnd(data, fidelity, width):
        rendered.append(data)
        return Block.text(repr(data), Style())

    code = _runner(renderer=rnd)._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 0
    assert rendered == []
    assert capsys.readouterr().out == ""


def test_deposit_offers_current_geometry_after_resize(monkeypatch):
    """The final deposited frame is itself an offer (§§5–6): it re-reads
    *current* columns, so a resize during the alt-screen session tracks
    through to the deposit rather than depositing at detection-time
    ctx.width."""

    async def fake_run(self):
        self._last_frame = ("final", None)

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    # The terminal resized to 120 cols during the (faked) session.
    monkeypatch.setattr("shutil.get_terminal_size", lambda *a, **k: os.terminal_size((120, 24)))

    offered: list[int | None] = []

    def rnd(data, fidelity, width):
        offered.append(width)
        return Block.text(str(data), Style())

    # _tty_ctx is is_tty=True, width=80 at detection — the deposit must ignore
    # that 80 and offer the current 120.
    runner = CliRunner(renderer=rnd, fetch=lambda: None, fetch_stream=_stream_of([]))
    code = runner._run_live_surface(_tty_ctx())
    assert code == 0
    assert offered == [120]  # deposit tracked the resize, not ctx.width=80


def test_deposit_carries_the_final_gauge(monkeypatch, capsys):
    """The scrollback artifact shows what the run cost."""

    async def fake_run(self):
        # Wide enough that the gauge row (truncated to the frame's width)
        # still shows its budget suffix.
        self._last_frame = ("final".ljust(64, "."), None)
        self.meter._costs.append(7.5)
        self.meter._periods.append(33.0)

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    code = _runner(live_meter=True)._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 0
    out = capsys.readouterr().out
    assert "final" in out and "budget" in out


def test_deposits_fetch_error(monkeypatch, capsys):
    async def fake_run(self):
        self.error = RuntimeError("kaboom")
        self.error_kind = "fetch"

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    code = _runner()._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 1
    assert "kaboom" in capsys.readouterr().out


def test_deposit_installs_the_last_states_schemes(monkeypatch, capsys):
    """The final deposit is itself a separate serialization event — it
    reuses the schemes already resolved for the last fetched state (§7),
    which is what a real run leaves in ``last_ref_schemes``."""

    async def fake_run(self):
        self._last_frame = ("final", (RefScheme("fact", lambda v: f"https://loops.dev/f/{v}"),))

    monkeypatch.setattr(StreamSurface, "run", fake_run)

    def rnd(data, fidelity, width):
        return Block.text(data, Style(), ref="fact:01")

    runner = CliRunner(
        renderer=rnd,
        fetch=lambda: None,
        fetch_stream=_stream_of([]),
        ref_schemes=[RefScheme("fact", lambda v: f"https://loops.dev/f/{v}")],
    )
    code = runner._run_live_surface(_tty_ctx())
    assert code == 0
    assert "\x1b]8;;https://loops.dev/f/01" in capsys.readouterr().out


def test_deposit_reuses_the_carried_pair_without_reevaluating(monkeypatch, capsys):
    """P1: the deposit must not re-invoke the resolver — it reuses the pair
    already resolved (in _consume()) for the state that was fetched last."""
    resolver = _recording_resolver()

    async def fake_run(self):
        # Two fetch events happen; the second is the one that deposits —
        # mirrors how a real run resolves per fetch event.
        self._last_frame = ("first", resolver("first"))
        self._last_frame = ("final", resolver("final"))

    monkeypatch.setattr(StreamSurface, "run", fake_run)

    def rnd(data, fidelity, width):
        return Block.text(data, Style(), ref="fact:01")

    runner = CliRunner(
        renderer=rnd, fetch=lambda: None, fetch_stream=_stream_of([]), ref_schemes=resolver
    )
    code = runner._run_live_surface(_tty_ctx())
    assert code == 0
    assert resolver.calls == ["first", "final"]  # exactly the two fetch-time evaluations
    assert "\x1b]8;;https://x/final/01" in capsys.readouterr().out


def test_deposit_ref_resolution_fault_returns_2(monkeypatch, capsys):
    """A resolution fault surfaces during the live run itself — inside
    _consume(), the only place evaluation happens — not at deposit, which
    has nothing left to evaluate. Captured the same way any render fault is:
    error_kind="render", handled before the deposit branch runs."""

    async def fake_run(self):
        self.error = RuntimeError("deposit scheme boom")
        self.error_kind = "render"

    monkeypatch.setattr(StreamSurface, "run", fake_run)

    def boom(state):
        raise RuntimeError("deposit scheme boom")

    code = _runner(ref_schemes=boom)._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 2
    assert "RuntimeError: deposit scheme boom" in capsys.readouterr().out


def test_deposits_render_error(monkeypatch, capsys):
    async def fake_run(self):
        self.error = ValueError("rkaboom")
        self.error_kind = "render"

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    code = _runner()._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 2
    assert "rkaboom" in capsys.readouterr().out


# --- The delivery gate in _run_live ---


def _tty_ctx() -> CliContext:
    return CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=OutputMode.LIVE,
        use_ansi=True,
        is_tty=True,
        width=80,
        height=24,
    )


def test_surface_delivery_taken_on_tty(monkeypatch):
    """live_delivery='surface' on a real TTY routes to the alt-screen path."""
    seen = {}

    def fake(self, ctx):
        seen["surface"] = True
        return 0

    monkeypatch.setattr(CliRunner, "_run_live_surface", fake)
    runner = CliRunner(
        renderer=_legacy_render,
        fetch=lambda: None,
        fetch_stream=_stream_of(["x"]),
        live_delivery="surface",
    )
    runner._run_live(_tty_ctx())
    assert seen.get("surface")


def test_surface_delivery_falls_back_to_inplace_when_not_tty(capsys):
    """Not a TTY → the alt screen can't be taken; the in-place non-ANSI branch
    deposits the final frame instead (static_ctx is is_tty=False, use_ansi=False)."""
    runner = CliRunner(
        renderer=_legacy_render,
        fetch=lambda: None,
        fetch_stream=_stream_of(["only"]),
        live_delivery="surface",
    )
    code = runner._run_live(static_ctx(Zoom.SUMMARY))
    assert code == 0
    assert "only" in capsys.readouterr().out
