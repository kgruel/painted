"""The host capability bracket — run_cli's STATIC/LIVE render paths (§9.2–9.4).

run_cli resolves a *standing* Capabilities snapshot from its destination and
installs it as an ambient bracket around every offer it makes to the renderer.
These tests drive the real dispatch seam and read ``current_capabilities()`` /
``current_icons()`` from inside a capturing renderer — the only honest witness,
since the renderer takes no capability argument (it reads the channel at the
leaf). Per-facet resolution and the §9.4 IconSet pairing are asserted per mode.

Unit-tier siblings cover the channel itself (default/narrowing/nesting) and the
ColorDepth.NONE writer correction; this tier proves the host wires the bracket.
"""

from __future__ import annotations

import io
import sys

from painted import ASCII_ICONS, Block, Capabilities, Style, current_capabilities, current_icons
from painted.cli import CliContext, CliRunner, Fidelity, OutputMode, Zoom


class _FakeStdout:
    """A writable stdout with controllable ``isatty`` and ``encoding``.

    The bracket's glyph facet reads ``sys.stdout.encoding`` (§9.3); color/link read
    ``ctx.use_ansi``. Swapping sys.stdout lets a test fix the encoding signal while
    the constructed ``CliContext`` fixes the ANSI signal — the two facets resolve
    from different sources, exactly as the contract requires. (A plain wrapper, not
    a ``StringIO`` subclass, because ``StringIO.encoding`` is read-only.)
    """

    def __init__(self, *, encoding: str | None, isatty: bool) -> None:
        self._buf = io.StringIO()
        self.encoding = encoding
        self._isatty = isatty

    def write(self, s: str) -> int:
        return self._buf.write(s)

    def flush(self) -> None: ...

    def isatty(self) -> bool:
        return self._isatty

    def getvalue(self) -> str:
        return self._buf.getvalue()


def _ctx(
    *,
    is_tty: bool,
    use_ansi: bool,
    mode: OutputMode = OutputMode.STATIC,
) -> CliContext:
    return CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=mode,
        use_ansi=use_ansi,
        is_tty=is_tty,
        width=80,
        height=24,
    )


def _capturing_renderer(sink: list[tuple[Capabilities, object]]):
    """A renderer that records the ambient capabilities + icons at render time."""

    def rnd(data: object, fidelity: Fidelity, width: int | None) -> Block:
        sink.append((current_capabilities(), current_icons()))
        return Block.text(str(data), Style())

    return rnd


class TestStaticBracket:
    def test_static_tty_installs_fully_capable_bracket(self, monkeypatch):
        """A UTF-8 TTY: color/glyph/link all True; no ASCII pairing forced."""
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding="utf-8", isatty=True))
        sink: list[tuple[Capabilities, object]] = []
        CliRunner(renderer=_capturing_renderer(sink), fetch=lambda: "d")._dispatch(
            _ctx(is_tty=True, use_ansi=True)
        )
        caps, icons = sink[0]
        assert caps == Capabilities(color=True, glyph=True, link=True)
        assert icons is not ASCII_ICONS

    def test_static_pipe_utf8_keeps_glyph_while_color_and_link_narrow(self, monkeypatch):
        """The normative case: a UTF-8 pipe narrows color and link (ANSI off) but
        glyph does NOT co-narrow — the encoding still carries carrier glyphs, so no
        ASCII IconSet is installed (§9.3, §9.4)."""
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding="utf-8", isatty=False))
        sink: list[tuple[Capabilities, object]] = []
        CliRunner(renderer=_capturing_renderer(sink), fetch=lambda: "d")._dispatch(
            _ctx(is_tty=False, use_ansi=False)
        )
        caps, icons = sink[0]
        assert caps == Capabilities(color=False, glyph=True, link=False)
        assert icons is not ASCII_ICONS

    def test_static_pipe_ascii_narrows_glyph_and_pairs_ascii_icons(self, monkeypatch):
        """A known-ASCII destination narrows glyph; the §9.4 pairing installs an
        ASCII-safe IconSet so the two never disagree."""
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding="ascii", isatty=False))
        sink: list[tuple[Capabilities, object]] = []
        CliRunner(renderer=_capturing_renderer(sink), fetch=lambda: "d")._dispatch(
            _ctx(is_tty=False, use_ansi=False)
        )
        caps, icons = sink[0]
        assert caps == Capabilities(color=False, glyph=False, link=False)
        assert icons is ASCII_ICONS

    def test_unknowable_encoding_is_conservative(self, monkeypatch):
        """No encoding is unknowable → glyph False (conservative), ASCII paired."""
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding=None, isatty=True))
        sink: list[tuple[Capabilities, object]] = []
        CliRunner(renderer=_capturing_renderer(sink), fetch=lambda: "d")._dispatch(
            _ctx(is_tty=True, use_ansi=True)
        )
        caps, icons = sink[0]
        assert caps == Capabilities(color=True, glyph=False, link=True)
        assert icons is ASCII_ICONS


class TestNoColor:
    def test_no_color_narrows_color_not_glyph(self, monkeypatch):
        """NO_COLOR joins the color snapshot (matching Writer) but never touches
        glyph — a UTF-8 TTY keeps glyph=True and its Unicode IconSet."""
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding="utf-8", isatty=True))
        sink: list[tuple[Capabilities, object]] = []
        CliRunner(renderer=_capturing_renderer(sink), fetch=lambda: "d")._dispatch(
            _ctx(is_tty=True, use_ansi=True)
        )
        caps, icons = sink[0]
        assert caps == Capabilities(color=False, glyph=True, link=True)
        assert icons is not ASCII_ICONS


class TestLiveBracket:
    def test_live_installs_bracket_in_the_render_task(self, monkeypatch):
        """LIVE brackets in the task that invokes the renderer (§9.2): the
        in-place stream loop renders inside the standing bracket, so the resolved
        facets reach the renderer through the asyncio task it spawns."""

        class _StubRenderer:
            def __init__(self, *a, **k) -> None: ...
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return None

            def render(self, block: Block) -> None: ...
            def finalize(self) -> None: ...

        import painted.inplace as inplace_mod

        monkeypatch.setattr(inplace_mod, "InPlaceRenderer", _StubRenderer)
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding="utf-8", isatty=True))

        sink: list[tuple[Capabilities, object]] = []

        async def stream():
            yield "a"

        CliRunner(
            renderer=_capturing_renderer(sink), fetch=lambda: "unused", fetch_stream=stream
        )._dispatch(_ctx(is_tty=True, use_ansi=True, mode=OutputMode.LIVE))

        assert sink, "the live path must have offered a frame to the renderer"
        caps, _ = sink[0]
        assert caps == Capabilities(color=True, glyph=True, link=True)


class TestNonRenderPaths:
    def test_json_path_installs_no_bracket(self, capsys, monkeypatch):
        """--json renders nothing and installs nothing: the renderer is never
        invoked, so no capability read ever happens (§9.3)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from painted.cli import run_cli

        sink: list[tuple[Capabilities, object]] = []
        rc = run_cli(["--json"], renderer=_capturing_renderer(sink), fetch=lambda: {"a": 1})
        assert rc == 0
        assert sink == []  # nothing rendered → nothing installed

    def test_custom_handler_is_not_wrapped(self, monkeypatch):
        """A custom handler owns its own bracket, so the framework installs none:
        even a destination that would narrow every facet leaves the handler seeing
        the fully-capable default (§9.3)."""
        monkeypatch.setattr(sys, "stdout", _FakeStdout(encoding="ascii", isatty=False))
        seen: dict[str, object] = {}

        def handler(ctx: CliContext) -> int:
            seen["caps"] = current_capabilities()
            seen["icons"] = current_icons()
            return 0

        CliRunner(
            renderer=lambda d, f, w: Block.text("unused", Style()),
            fetch=lambda: "d",
            handlers={OutputMode.STATIC: handler},
        )._dispatch(_ctx(is_tty=False, use_ansi=False))

        assert seen["caps"] == Capabilities()  # default — the framework wrapped nothing
        assert seen["icons"] is not ASCII_ICONS  # no ASCII pairing forced on the handler


class TestOneSnapshot:
    """§9.1: NO_COLOR is read once per delivery and fed to both the color facet
    and the serializing Writer, so a mid-run env change cannot split content
    choice from serialization."""

    def test_static_serializer_uses_the_bracket_snapshot_not_a_second_read(
        self, capsys, monkeypatch
    ):
        """The color facet and the serializer share one NO_COLOR read. A renderer
        that *mutates* the environment mid-render cannot desync them: the facet saw
        NO_COLOR, and the serializer — fed the same snapshot resolved before the
        bracket — still suppresses colour even though the env was cleared before the
        write happens."""
        import os

        from painted.cli import run_cli

        monkeypatch.setattr("sys.stdout.isatty", lambda: True)  # TTY → use_ansi
        monkeypatch.setenv("NO_COLOR", "1")
        seen: dict[str, Capabilities] = {}

        def renderer(data, fidelity, width):
            seen["caps"] = current_capabilities()
            # Hostile mid-render env change: clear NO_COLOR between the bracket
            # (already resolved) and the print_block serialization below.
            os.environ.pop("NO_COLOR", None)
            return Block.text("hi", Style(fg="red"))

        # A TTY with no fetch_stream: LIVE resolves, then falls back to a single
        # fetch-and-render through the static delivery path.
        rc = run_cli([], renderer=renderer, fetch=lambda: "d")
        out = capsys.readouterr().out

        assert rc == 0
        assert seen["caps"].color is False  # the facet saw NO_COLOR
        # The serializer honored the same snapshot — no red SGR — despite the env
        # having been cleared before the write. Two independent reads would have
        # re-enabled colour here; one snapshot does not.
        assert "\x1b[31m" not in out
        assert "31" not in out

    def test_error_serializer_carries_the_delivery_snapshot(self, capsys, monkeypatch):
        """The error writer is a stdout serializer opened inside _host_scope, so it
        carries the delivery's snapshot too (§9.1). A renderer that clears NO_COLOR
        and *then raises* must not hand the error writer a fresher, different policy:
        the error print_block still receives the pre-resolved snapshot (True), not
        the post-pop env read (False)."""
        import os

        import painted.core.writer as writer_mod
        from painted.cli import run_cli

        seen_no_color: list[bool | None] = []
        real_print_block = writer_mod.print_block

        def spy(block, stream=None, *, use_ansi=None, no_color=None):
            seen_no_color.append(no_color)
            return real_print_block(block, stream, use_ansi=use_ansi, no_color=no_color)

        # _emit_error re-imports print_block from the module on each call, so
        # patching the module attribute is enough to observe the error serializer.
        monkeypatch.setattr(writer_mod, "print_block", spy)
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        monkeypatch.setenv("NO_COLOR", "1")

        def renderer(data, fidelity, width):
            os.environ.pop("NO_COLOR", None)  # a fresh read here would yield False
            raise ValueError("boom")

        rc = run_cli([], renderer=renderer, fetch=lambda: "d")
        capsys.readouterr()

        assert rc == 2  # render failure
        assert seen_no_color, "the error serializer must have run"
        # Every stdout serializer in the delivery — here just the error writer —
        # received the pre-resolved snapshot (True), never the post-pop env (False).
        assert all(nc is True for nc in seen_no_color)
