"""Laws for the alt-screen live tier: StreamSurface + CliRunner._run_live_surface.

StreamSurface is the cli-private adapter that hosts a `fetch_stream` on a
Surface alt screen (the 'sustained' tier of the two-tier live contract, see
docs/LIVE_DELIVERY_DESIGN.md). These tests pin the genuinely new logic without
a terminal:

  - stream hosting: states are consumed to exhaustion, the last is retained,
    pause gates consumption, stream failures are captured (not raised);
  - render(): paints the current state, captures render failures, blanks when
    there is no state yet;
  - keys: q / ctrl-c quit, space toggles pause;
  - _run_live_surface: deposits the final frame (or the failure) and returns the
    right exit code, and the delivery gate only takes the alt-screen path on a
    real TTY.

TestSurface can't drive this path — it runs the loop synchronously and never
fires the lifecycle hooks that spawn the async consumer — so the consumer is
exercised directly via asyncio.run, mirroring tests/unit/test_live_stream.py.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from painted import Block, CliContext, Fidelity, Style, Zoom
from painted.cli.runner import CliRunner
from painted.cli.stream_surface import StreamSurface
from painted.cli.types import OutputMode
from painted.tui import Buffer
from painted.tui.testing import buffer_to_lines

from tests.helpers import static_ctx


# --- Fixtures: a trivial render and parameterizable streams ---


def _surface_render(state: object, width: int) -> Block:
    """The StreamSurface render callback shape (§6): (state, buffer_width) →
    Block. In production this is the runner's adapted closure; here a stand-in
    that ignores width, so a plain frame is captured."""
    return Block.text(str(state), Style())


def _legacy_render(ctx: CliContext, state: object) -> Block:
    """The CliRunner ``render=`` legacy shape (ctx, state) — used by the
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
    states, *, fail_after=None, render=_surface_render, live_meter=False
) -> StreamSurface:
    return StreamSurface(
        render=render,
        fetch_stream=_stream_of(states, fail_after=fail_after),
        live_meter=live_meter,
    )


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


# --- render() ---


def test_render_paints_current_state():
    surf = _make_surface(["hello"])
    surf._buf = Buffer(10, 1)
    surf._state = "hello"
    surf.render()
    assert buffer_to_lines(surf._buf)[0].startswith("hello")


def test_render_exception_is_captured_as_render():
    def boom(state, width):
        raise ValueError("render boom")

    surf = _make_surface(["x"], render=boom)
    surf._buf = Buffer(10, 1)
    surf._running = True
    surf._state = "x"
    surf.render()
    assert surf.error_kind == "render"
    assert isinstance(surf.error, ValueError)
    assert surf._running is False  # a render failure stops the loop


def test_render_without_state_is_blank():
    surf = _make_surface([])
    surf._buf = Buffer(5, 1)
    surf.render()  # _state is still None
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
    surf._state = "x"
    surf._buf = Buffer(30, 1)
    surf.render()
    surf._buf = Buffer(52, 1)  # the alt screen resized
    surf.render()
    assert offered == [30, 52]


# --- The delivery gauge ---


def test_frames_feed_the_gauge(monkeypatch):
    """One render+flush cycle records one cost sample — the meter lives on
    the delivery side of the decoupling, where the cost actually is."""
    from painted.tui import Surface

    monkeypatch.setattr(Surface, "_flush", lambda self: None)  # silence the terminal
    surf = _make_surface(["hello"], live_meter=True)
    surf._buf = Buffer(40, 2)
    surf._state = "hello"
    surf.render()
    surf._flush()
    assert len(surf.meter._costs) == 1


def test_stateless_frames_are_not_measured(monkeypatch):
    """A flush whose render carried no state contributes no sample."""
    from painted.tui import Surface

    monkeypatch.setattr(Surface, "_flush", lambda self: None)
    surf = _make_surface([], live_meter=True)
    surf._buf = Buffer(40, 2)
    surf.render()  # _state is still None
    surf._flush()
    assert surf.meter._costs == []


def test_gauge_is_opt_in(monkeypatch):
    """Without live_meter, frames are neither measured nor dressed."""
    from painted.tui import Surface

    monkeypatch.setattr(Surface, "_flush", lambda self: None)
    surf = _make_surface(["hello"])
    surf._buf = Buffer(40, 2)
    surf._state = "hello"
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


def _runner(render=_legacy_render, **kwargs) -> CliRunner:
    return CliRunner(render=render, fetch=lambda: None, fetch_stream=_stream_of([]), **kwargs)


def test_deposits_last_frame_on_success(monkeypatch, capsys):
    async def fake_run(self):
        self.last_state = "final"

    monkeypatch.setattr(StreamSurface, "run", fake_run)
    code = _runner()._run_live_surface(static_ctx(Zoom.SUMMARY))
    assert code == 0
    assert "final" in capsys.readouterr().out  # last frame left in scrollback


def test_deposit_offers_current_geometry_after_resize(monkeypatch):
    """The final deposited frame is itself an offer (§§5–6): it re-reads
    *current* columns, so a resize during the alt-screen session tracks
    through to the deposit rather than depositing at detection-time
    ctx.width."""

    async def fake_run(self):
        self.last_state = "final"

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
        self.last_state = "final".ljust(64, ".")
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
        render=_legacy_render,
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
        render=_legacy_render,
        fetch=lambda: None,
        fetch_stream=_stream_of(["only"]),
        live_delivery="surface",
    )
    code = runner._run_live(static_ctx(Zoom.SUMMARY))
    assert code == 0
    assert "only" in capsys.readouterr().out
