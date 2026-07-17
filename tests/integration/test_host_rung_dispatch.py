"""Route-level offer pinning + interactive dispatch (HOST_RUNG_DESIGN §§3-6, S4).

S1 landed the offer *matrix* in ``_render`` and proved it at the ``_render``
level. This tier pins it through the assembled dispatch — every delivery route a
declared binding travels — because the offer is a per-delivery decision made by
each route, not by ``_render`` alone (S1 review P3):

* a **declared** ``height_renderer=`` binding is offered ``height=None`` on every
  gated-off route (STATIC, in-place LIVE, streaming non-ANSI — the Q7 fence plus
  off-TTY), and ``height=H`` on the gated-on interactive offered path;
* an **undeclared** binding (``renderer=`` / ``render=`` / the transcription
  default) is *never* handed the ``height`` keyword on any route — it has none.

The interactive routes drive the real ``_dispatch`` → ``_run_interactive`` →
``_run_host`` seam with the alt-screen loop swapped for a ``TestSurface`` (the
same ``HostSurface`` the runner mounts, just without a terminal).
"""

from __future__ import annotations

from painted import Block, Style
from painted.cli import CliContext, CliRunner, Fidelity, OutputMode, Zoom, run_cli


class HeightRecorder:
    """A declared (offered-arm) renderer that records every ``height`` offer."""

    def __init__(self) -> None:
        self.calls: list[int | None] = []

    def __call__(self, data: object, fidelity: Fidelity, width: int | None, *, height: int | None):
        self.calls.append(height)
        rows = height if height is not None else 3  # exact H when offered, else natural
        return Block.empty(max(1, width or 10), rows)


class PlainRecorder:
    """An undeclared ``(data, fidelity, width)`` renderer that records the kwargs
    it is handed — it must never see ``height``."""

    def __init__(self) -> None:
        self.kwargs: list[dict[str, object]] = []

    def __call__(self, data: object, fidelity: Fidelity, width: int | None, **kwargs: object):
        self.kwargs.append(kwargs)
        return Block.empty(max(1, width or 10), 3)


def _ctx(mode: OutputMode, *, is_tty: bool, use_ansi: bool, height: int = 8) -> CliContext:
    return CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=mode,
        use_ansi=use_ansi,
        is_tty=is_tty,
        width=40,
        height=height,
    )


async def _one(state: object):
    yield state


class _StubInPlace:
    """Stand-in for InPlaceRenderer — the ANSI in-place path writes real cursor
    control to stdout, which a captured test stdout can't take."""

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    def __enter__(self) -> _StubInPlace:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def render(self, block: object) -> None: ...

    def finalize(self) -> None: ...


def _stub_inplace(monkeypatch) -> None:
    import painted.inplace as inplace_mod

    monkeypatch.setattr(inplace_mod, "InPlaceRenderer", _StubInPlace)


# --- The declared binding: gated-off routes offer height=None ----------------


def test_static_route_offers_height_none(capsys) -> None:
    recorder = HeightRecorder()
    runner = CliRunner(height_renderer=recorder, fetch=lambda: {"x": 1})
    runner._dispatch(_ctx(OutputMode.STATIC, is_tty=True, use_ansi=True))
    assert recorder.calls == [None]


def test_inplace_live_route_offers_height_none(capsys) -> None:
    recorder = HeightRecorder()
    runner = CliRunner(
        height_renderer=recorder,
        fetch=lambda: {"x": 1},
        fetch_stream=lambda: _one({"x": 1}),
    )
    runner._dispatch(_ctx(OutputMode.LIVE, is_tty=True, use_ansi=True))
    assert recorder.calls == [None]


def test_streaming_non_ansi_route_offers_height_none(capsys) -> None:
    recorder = HeightRecorder()
    runner = CliRunner(
        height_renderer=recorder,
        fetch=lambda: {"x": 1},
        fetch_stream=lambda: _one({"x": 1}),
    )
    runner._dispatch(_ctx(OutputMode.LIVE, is_tty=False, use_ansi=False))
    assert recorder.calls == [None]


# --- The declared binding: the gated-on interactive path offers height=H -----


def _mount_via_testsurface(monkeypatch, *, width: int, height: int) -> None:
    """Swap the alt-screen launch for a TestSurface run of the same HostSurface."""

    def fake_run_host_surface(*, render, accepts_height, content_id, inputs, **_kw) -> int:
        from painted.tui import HostSurface, TestSurface

        surface = HostSurface(
            render=render,
            accepts_height=accepts_height,
            content_id=content_id,
            inputs=inputs,
        )
        TestSurface(surface, width=width, height=height).run_to_completion()
        return 0

    monkeypatch.setattr("painted.cli.stream_surface.run_host_surface", fake_run_host_surface)


def test_interactive_offered_path_offers_height_H(monkeypatch) -> None:
    _mount_via_testsurface(monkeypatch, width=40, height=8)
    recorder = HeightRecorder()
    runner = CliRunner(height_renderer=recorder, fetch=lambda: {"x": 1})
    rc = runner._dispatch(_ctx(OutputMode.INTERACTIVE, is_tty=True, use_ansi=True, height=8))
    assert rc == 0
    # The offered arm on a hard vertical frame — the full frame height (§5/§6).
    assert recorder.calls == [8]


def test_interactive_non_tty_falls_back_to_live_with_height_none(capsys) -> None:
    recorder = HeightRecorder()
    runner = CliRunner(height_renderer=recorder, fetch=lambda: {"x": 1})
    # Not a usable TTY: no alt screen — INTERACTIVE falls back to LIVE, gated off.
    runner._dispatch(_ctx(OutputMode.INTERACTIVE, is_tty=False, use_ansi=False))
    assert recorder.calls == [None]


# --- The undeclared binding: never handed the height keyword anywhere --------


def test_undeclared_binding_never_receives_height_keyword(monkeypatch, capsys) -> None:
    _mount_via_testsurface(monkeypatch, width=40, height=8)

    for mode, is_tty, use_ansi in [
        (OutputMode.STATIC, True, True),
        (OutputMode.INTERACTIVE, True, True),
        (OutputMode.INTERACTIVE, False, False),
    ]:
        recorder = PlainRecorder()
        runner = CliRunner(renderer=recorder, fetch=lambda: {"x": 1})
        runner._dispatch(_ctx(mode, is_tty=is_tty, use_ansi=use_ansi))
        assert recorder.kwargs, f"renderer was never called for {mode}"
        assert all(kw == {} for kw in recorder.kwargs), (
            f"undeclared binding received a keyword on {mode}: {recorder.kwargs}"
        )


def test_undeclared_binding_never_receives_height_on_live_routes(monkeypatch, capsys) -> None:
    """The two LIVE routes complete the undeclared coverage: in-place LIVE (ANSI
    TTY) and the streaming non-ANSI cadence both call the renderer with no
    keyword."""
    _stub_inplace(monkeypatch)
    for is_tty, use_ansi in [(True, True), (False, False)]:
        recorder = PlainRecorder()
        runner = CliRunner(
            renderer=recorder,
            fetch=lambda: {"x": 1},
            fetch_stream=lambda: _one({"x": 1}),
        )
        runner._dispatch(_ctx(OutputMode.LIVE, is_tty=is_tty, use_ansi=use_ansi))
        assert recorder.kwargs, f"renderer was never called (is_tty={is_tty})"
        assert all(kw == {} for kw in recorder.kwargs), (
            f"undeclared binding received a keyword on a LIVE route: {recorder.kwargs}"
        )


# --- Dispatch priority: handler wins; a declared stream stays live-tier -------


def test_custom_interactive_handler_wins_over_host_rung(monkeypatch) -> None:
    mounted: list[bool] = []
    monkeypatch.setattr(
        "painted.cli.stream_surface.run_host_surface",
        lambda **_kw: (mounted.append(True), 0)[1],
    )
    called: list[bool] = []

    def handler(ctx: CliContext) -> int:
        called.append(True)
        return 7

    runner = CliRunner(
        renderer=lambda d, f, w: Block.empty(w or 1, 1),
        fetch=lambda: {},
        handlers={OutputMode.INTERACTIVE: handler},
    )
    rc = runner._dispatch(_ctx(OutputMode.INTERACTIVE, is_tty=True, use_ansi=True))
    assert rc == 7
    assert called == [True]
    assert mounted == []  # the escape wins — the host rung is never mounted


def test_declared_stream_stays_live_tier_under_interactive(monkeypatch, capsys) -> None:
    _stub_inplace(monkeypatch)
    mounted: list[bool] = []
    monkeypatch.setattr(
        "painted.cli.stream_surface.run_host_surface",
        lambda **_kw: (mounted.append(True), 0)[1],
    )
    runner = CliRunner(
        renderer=lambda d, f, w: Block.empty(w or 1, 1),
        fetch=lambda: {},
        fetch_stream=lambda: _one({}),
    )
    runner._dispatch(_ctx(OutputMode.INTERACTIVE, is_tty=True, use_ansi=True))
    # A declared stream under -i converges onto the live tier, not the host rung:
    # the single-fetch host rung would drop the stream (§7).
    assert mounted == []


# --- Piped -i through REAL detect_context — ANSI stays context-derived (P1) ---


def test_piped_interactive_emits_clean_non_ansi(monkeypatch, capsys) -> None:
    """`-i` into a pipe, resolved by the real detect_context: the mode degrades
    to LIVE but ANSI stays off the destination — no escapes leak into the pipe."""
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    rc = run_cli(
        ["-i"],
        renderer=lambda d, f, w: Block.text("hello", Style(fg="red")),
        fetch=lambda: {},
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "hello" in out
    assert "\x1b[" not in out  # no ANSI serialized into the pipe


def test_piped_interactive_stream_emits_no_cursor_control(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    rc = run_cli(
        ["-i"],
        renderer=lambda d, f, w: Block.text("frame", Style()),
        fetch=lambda: {},
        fetch_stream=lambda: _one({}),
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "\x1b[" not in out  # a stream under piped -i emits no cursor control


def test_interactive_is_available_on_every_command() -> None:
    """`-i` is honest now: the host rung mounts any binding, so INTERACTIVE is in
    the supported mode set even with no handler and no stream (§1)."""
    runner = CliRunner(renderer=lambda d, f, w: Block.empty(w or 1, 1), fetch=lambda: {})
    parser = runner._get_parser()
    options = {s for a in parser._actions for s in a.option_strings}
    assert "-i" in options
