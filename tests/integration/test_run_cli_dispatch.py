"""End-to-end run_cli dispatch — the real CLI path, mode by mode.

These classes drive run_cli() through parse → compile → detect_context →
dispatch and assert on what reaches stdout (capsys) or the renderer:
STATIC/JSON/LIVE delivery, error blocks and exit codes, live fallbacks,
streaming, and --help through the real intercept. Unit-tier siblings test
the pieces (parse_fidelity, help_doc construction); this tier tests the
assembled path. Moved from tests/unit/test_fidelity*.py (the golden-migration
follow-up: the integration tier owns dispatch).
"""

from __future__ import annotations

import json

import pytest

from painted import Block, Style
from painted.cli import (
    CliContext,
    CliRunner,
    Fidelity,
    HelpArg,
    OutputMode,
    Zoom,
    run_cli,
)
from painted.core.errors import DeclarationError


# =============================================================================
# CliRunner dispatch (from test_fidelity.py)
# =============================================================================


class TestCliRunner:
    """Tests for CliRunner class."""

    def test_invalid_live_delivery_raises_at_construction(self):
        """Misconfiguration raises immediately, never degrades at dispatch."""
        with pytest.raises(DeclarationError, match="live_delivery"):
            CliRunner(
                render=lambda ctx, data: Block.text("x", Style()),
                fetch=lambda: "x",
                live_delivery="surfce",
            )

    def test_static_output(self, monkeypatch):
        """Static mode uses print_block and returns 0."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        render_called = False
        fetch_called = False
        received_ctx = None

        def render(ctx: CliContext, data: str) -> Block:
            nonlocal render_called, received_ctx
            render_called = True
            received_ctx = ctx
            return Block.text(f"zoom={ctx.zoom.value}: {data}", Style())

        def fetch() -> str:
            nonlocal fetch_called
            fetch_called = True
            return "test data"

        # AUTO resolves to STATIC when not a TTY
        result = run_cli(
            [],
            render=render,
            fetch=fetch,
        )

        assert result == 0
        assert render_called, "render should be called"
        assert fetch_called, "fetch should be called"
        assert received_ctx.mode == OutputMode.STATIC

    def test_json_output(self, capsys, monkeypatch):
        """JSON mode outputs JSON."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def render(ctx: CliContext, data: dict) -> Block:
            return Block.text("unused", Style())

        def fetch() -> dict:
            return {"status": "ok", "count": 42}

        result = run_cli(
            ["--json"],
            render=render,
            fetch=fetch,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert '"status": "ok"' in captured.out
        assert '"count": 42' in captured.out

    def test_zoom_passed_to_render(self, monkeypatch):
        """Zoom level is passed to render function."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        received_zoom = None

        def render(ctx: CliContext, data: str) -> Block:
            nonlocal received_zoom
            received_zoom = ctx.zoom
            return Block.text(data, Style())

        run_cli(
            ["-v"],
            render=render,
            fetch=lambda: "data",
        )

        assert received_zoom == Zoom.DETAILED

    def test_fidelity_passed_to_render(self, monkeypatch):
        """Fidelity from --max-chars/--max-lines is passed to render function."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        received_fidelity = None

        def render(ctx: CliContext, data: str) -> Block:
            nonlocal received_fidelity
            received_fidelity = ctx.fidelity
            return Block.text(data, Style())

        run_cli(
            ["--max-chars", "50", "--max-lines", "10"],
            render=render,
            fetch=lambda: "data",
            budgets=True,
        )

        assert received_fidelity is not None
        assert received_fidelity.chars == 50
        assert received_fidelity.lines == 10

    def test_no_fidelity_flags_gives_zero_limits(self, monkeypatch):
        """Without density flags, ctx.fidelity.chars and .lines are 0 (unlimited)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        received_fidelity = None

        def render(ctx: CliContext, data: str) -> Block:
            nonlocal received_fidelity
            received_fidelity = ctx.fidelity
            return Block.text(data, Style())

        run_cli(
            [],
            render=render,
            fetch=lambda: "data",
        )

        assert received_fidelity is not None
        assert received_fidelity.chars == 0
        assert received_fidelity.lines == 0

    def test_custom_handler(self, monkeypatch):
        """Custom handler is called for matching mode."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        handler_called = False
        received_ctx = None

        def custom_interactive(ctx: CliContext) -> int:
            nonlocal handler_called, received_ctx
            handler_called = True
            received_ctx = ctx
            return 42

        result = run_cli(
            ["-i"],
            render=lambda ctx, data: Block.text("unused", Style()),
            fetch=lambda: "data",
            handlers={OutputMode.INTERACTIVE: custom_interactive},
        )

        assert handler_called
        assert received_ctx.mode == OutputMode.INTERACTIVE
        assert result == 42

    def test_fetch_failure_static_renders_error_and_returns_1(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        render_called = False

        def render(ctx: CliContext, data: str) -> Block:
            nonlocal render_called
            render_called = True
            return Block.text("unused", Style())

        def fetch() -> str:
            raise ValueError("nope")

        result = run_cli([], render=render, fetch=fetch)

        assert result == 1
        assert render_called is False
        captured = capsys.readouterr()
        assert "nope" in captured.out
        assert "Traceback" not in captured.out

    def test_fetch_failure_json_outputs_error_object_and_returns_1(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def fetch() -> dict:
            raise RuntimeError("badness")

        result = run_cli(
            ["--json"],
            render=lambda ctx, data: Block.text("unused", Style()),
            fetch=fetch,
        )

        assert result == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload == {"error": "badness"}

    def test_render_failure_static_renders_minimal_error_and_returns_2(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def render(ctx: CliContext, data: str) -> Block:
            raise KeyError("kaboom")

        result = run_cli([], render=render, fetch=lambda: "ok")

        assert result == 2
        captured = capsys.readouterr()
        assert "KeyError" in captured.out
        assert "kaboom" in captured.out
        assert "Traceback" not in captured.out


class TestRunCliHelp:
    """Integration tests for --help with command args."""

    def test_help_with_help_args_shows_command_args(self, capsys, monkeypatch):
        """--help with help_args shows command args prominently."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--help"],
            render=lambda ctx, data: Block.text("unused", Style()),
            fetch=lambda: "ok",
            prog="myapp",
            description="My application",
            help_args=[
                HelpArg("vertex", "Vertex name", positional=True),
                HelpArg("--since", "Time range", default="7d"),
            ],
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "vertex" in captured.out
        assert "Vertex name" in captured.out
        assert "--since" in captured.out
        assert "(default: 7d)" in captured.out
        assert "myapp" in captured.out

    def test_help_with_add_args_shows_command_args(self, capsys, monkeypatch):
        """--help with add_args shows registered args."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def add_args(parser):
            parser.add_argument("file", help="Input file")
            parser.add_argument("--format", help="Output format")

        result = run_cli(
            ["--help"],
            render=lambda ctx, data: Block.text("unused", Style()),
            fetch=lambda: "ok",
            prog="myapp",
            add_args=add_args,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert "file" in captured.out
        assert "Input file" in captured.out
        assert "--format" in captured.out

    def test_help_without_command_args_unchanged(self, capsys, monkeypatch):
        """--help without help_args/add_args shows rendering options as before."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--help"],
            render=lambda ctx, data: Block.text("unused", Style()),
            fetch=lambda: "ok",
            prog="myapp",
        )

        assert result == 0
        captured = capsys.readouterr()
        # Rendering groups shown with headers (not collapsed)
        assert "Zoom" in captured.out
        assert "-q, --quiet" in captured.out


# =============================================================================
# Mode inference, JSON path, error blocks, live tiers (from test_fidelity_extended.py)
# =============================================================================


class TestCliRunnerModeInference:
    def test_fetch_stream_enables_live_mode(self, monkeypatch):
        """When fetch_stream is provided, LIVE mode is available."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        async def fake_stream():
            yield "data"

        CliRunner(
            render=lambda ctx, data: Block.text(str(data), Style()),
            fetch=lambda: "data",
            fetch_stream=fake_stream,
        )

        # parse_args should not error with --live
        import argparse

        parser = argparse.ArgumentParser()
        from painted.cli import add_cli_args

        modes = {OutputMode.STATIC, OutputMode.LIVE}
        add_cli_args(parser, modes=modes)
        parsed = parser.parse_args(["--live"])
        assert parsed.live is True

    def test_handler_returns_none_becomes_zero(self, monkeypatch):
        """Custom handler returning None is treated as exit code 0."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def handler(ctx: CliContext) -> None:
            return None  # type: ignore[return-value]

        result = run_cli(
            ["-i"],
            render=lambda ctx, data: Block.text("x", Style()),
            fetch=lambda: "ok",
            handlers={OutputMode.INTERACTIVE: handler},
        )
        assert result == 0

    def test_json_format_implies_static(self, capsys, monkeypatch):
        """--json with AUTO mode resolves to STATIC."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        received_ctx = None

        def render(ctx: CliContext, data: str) -> Block:
            nonlocal received_ctx
            received_ctx = ctx
            return Block.text(data, Style())

        result = run_cli(
            ["--json"],
            render=render,
            fetch=lambda: {"val": 1},
        )
        assert result == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == {"val": 1}

    def test_plain_format_implies_static(self, capsys, monkeypatch):
        """--plain with AUTO mode resolves to STATIC."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        result = run_cli(
            ["--plain"],
            render=lambda ctx, data: Block.text("hello", Style()),
            fetch=lambda: "ok",
        )
        assert result == 0

    def test_quiet_implies_static(self, monkeypatch):
        """Zoom.MINIMAL (-q) with AUTO mode resolves to STATIC."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["-q"],
            render=lambda ctx, data: Block.text("minimal", Style()),
            fetch=lambda: "ok",
        )
        assert result == 0


class TestCliRunnerJsonPath:
    def test_json_non_dataclass_state(self, capsys, monkeypatch):
        """JSON mode handles non-dataclass state (dict, list, etc.)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--json"],
            render=lambda ctx, data: Block.text("x", Style()),
            fetch=lambda: [1, 2, 3],
        )
        assert result == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == [1, 2, 3]

    def test_json_fetch_error(self, capsys, monkeypatch):
        """JSON mode fetch error produces error JSON."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--json"],
            render=lambda ctx, data: Block.text("x", Style()),
            fetch=lambda: (_ for _ in ()).throw(IOError("disk full")),
        )
        assert result == 1
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"error": "disk full"}


class TestCliRunnerErrorBlocks:
    def test_fetch_error_block_uses_palette(self):
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=24,
        )
        block = CliRunner._fetch_error_block(ctx, ValueError("bad input"))
        text = "".join(cell.char for cell in block.row(0))
        assert "bad input" in text

    def test_render_error_block_includes_type(self):
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=24,
        )
        block = CliRunner._render_error_block(ctx, KeyError("missing"))
        text = "".join(cell.char for cell in block.row(0))
        assert "KeyError" in text

    def test_render_error_block_empty_message(self):
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=24,
        )
        block = CliRunner._render_error_block(ctx, RuntimeError(""))
        text = "".join(cell.char for cell in block.row(0))
        assert "RuntimeError" in text

    def test_fetch_error_block_narrow_width(self):
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=0,
            height=24,
        )
        block = CliRunner._fetch_error_block(ctx, ValueError("x"))
        assert block.width >= 1


class TestCliRunnerLiveFallback:
    def test_live_without_stream_renders_static(self, capsys, monkeypatch):
        """LIVE mode without fetch_stream falls back to fetch-and-render."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.LIVE,
            use_ansi=True,
            is_tty=False,
            width=80,
            height=24,
        )
        runner = CliRunner(
            render=lambda ctx, data: Block.text("live-ok", Style()),
            fetch=lambda: "ok",
        )
        result = runner._dispatch(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "live-ok" in captured.out

    def test_live_fetch_error(self, capsys, monkeypatch):
        """LIVE mode fetch error returns 1."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.LIVE,
            use_ansi=True,
            is_tty=False,
            width=80,
            height=24,
        )
        runner = CliRunner(
            render=lambda ctx, data: Block.text("x", Style()),
            fetch=lambda: (_ for _ in ()).throw(IOError("fail")),
        )
        result = runner._dispatch(ctx)
        assert result == 1

    def test_live_render_error(self, capsys, monkeypatch):
        """LIVE mode render error returns 2."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.LIVE,
            use_ansi=True,
            is_tty=False,
            width=80,
            height=24,
        )

        def bad_render(ctx, data):
            raise ValueError("render broke")

        runner = CliRunner(
            render=bad_render,
            fetch=lambda: "ok",
        )
        result = runner._dispatch(ctx)
        assert result == 2

    def test_interactive_without_handler_falls_to_live(self, capsys, monkeypatch):
        """INTERACTIVE mode without custom handler falls through to _run_live."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.INTERACTIVE,
            use_ansi=True,
            is_tty=False,
            width=80,
            height=24,
        )
        runner = CliRunner(
            render=lambda ctx, data: Block.text("interactive-fallback", Style()),
            fetch=lambda: "ok",
        )
        result = runner._dispatch(ctx)
        assert result == 0
        captured = capsys.readouterr()
        assert "interactive-fallback" in captured.out


class TestCliRunnerLiveStreaming:
    def test_live_with_stream_renders_each_state_and_finalizes(self, monkeypatch):
        renderers: list[object] = []

        class StubRenderer:
            def __init__(self, *args, **kwargs):
                self.blocks: list[Block] = []
                self.finalized = False
                renderers.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def render(self, block: Block) -> None:
                self.blocks.append(block)

            def finalize(self) -> None:
                self.finalized = True

        import painted.inplace as inplace_mod

        monkeypatch.setattr(inplace_mod, "InPlaceRenderer", StubRenderer)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.LIVE,
            use_ansi=True,
            is_tty=False,
            width=40,
            height=5,
        )

        async def fake_stream():
            yield "a"
            yield "b"

        runner = CliRunner(
            render=lambda ctx, data: Block.text(str(data), Style()),
            fetch=lambda: "unused",
            fetch_stream=fake_stream,
        )

        result = runner._dispatch(ctx)
        assert result == 0
        assert len(renderers) == 1
        renderer: StubRenderer = renderers[0]  # type: ignore[assignment]
        assert [row[0].char for row in (renderer.blocks[0].row(0), renderer.blocks[1].row(0))] == [
            "a",
            "b",
        ]
        assert renderer.finalized is True

    def test_live_stream_render_error_returns_2(self, monkeypatch):
        renderers: list[object] = []

        class StubRenderer:
            def __init__(self, *args, **kwargs):
                self.blocks: list[Block] = []
                self.finalized = False
                renderers.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def render(self, block: Block) -> None:
                self.blocks.append(block)

            def finalize(self) -> None:
                self.finalized = True

        import painted.inplace as inplace_mod

        monkeypatch.setattr(inplace_mod, "InPlaceRenderer", StubRenderer)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.LIVE,
            use_ansi=True,
            is_tty=False,
            width=40,
            height=5,
        )

        async def fake_stream():
            yield "ok"
            yield "boom"

        def maybe_bad_render(ctx, data):
            if data == "boom":
                raise ValueError("render broke")
            return Block.text(str(data), Style())

        runner = CliRunner(
            render=maybe_bad_render,
            fetch=lambda: "unused",
            fetch_stream=fake_stream,
        )

        result = runner._dispatch(ctx)
        assert result == 2
        assert len(renderers) == 1
        renderer: StubRenderer = renderers[0]  # type: ignore[assignment]
        assert renderer.finalized is True
        # Last rendered block should be an error block.
        assert "ValueError" in "".join(c.char for c in renderer.blocks[-1].row(0))

    def test_live_stream_fetch_error_returns_1(self, monkeypatch):
        renderers: list[object] = []

        class StubRenderer:
            def __init__(self, *args, **kwargs):
                self.blocks: list[Block] = []
                self.finalized = False
                renderers.append(self)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def render(self, block: Block) -> None:
                self.blocks.append(block)

            def finalize(self) -> None:
                self.finalized = True

        import painted.inplace as inplace_mod

        monkeypatch.setattr(inplace_mod, "InPlaceRenderer", StubRenderer)

        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.LIVE,
            use_ansi=True,
            is_tty=False,
            width=40,
            height=5,
        )

        async def bad_stream():
            yield "ok"
            raise RuntimeError("fetch broke")

        runner = CliRunner(
            render=lambda ctx, data: Block.text(str(data), Style()),
            fetch=lambda: "unused",
            fetch_stream=bad_stream,
        )

        result = runner._dispatch(ctx)
        assert result == 1
        assert len(renderers) == 1
        renderer: StubRenderer = renderers[0]  # type: ignore[assignment]
        assert renderer.finalized is True
        assert "fetch broke" in "".join(c.char for c in renderer.blocks[-1].row(0))


# =============================================================================
# Slice 1 — additive completion enablers: build_parser, ctx.args, fetch arity
# =============================================================================


class TestBuildParser:
    """build_parser builds the same parser without render/fetch — the parser
    completion and help walk."""

    def test_builds_framework_flags(self):
        from painted.cli.types import build_parser

        parser = build_parser()
        opts = {s for a in parser._actions for s in a.option_strings}
        assert {"-q", "--verbose", "--json", "--plain"} <= opts

    def test_add_args_extends_parser(self):
        from painted.cli.types import build_parser

        def add_args(p):
            p.add_argument("--frame", type=int, default=0)

        parser = build_parser(add_args=add_args)
        parsed = parser.parse_args(["--frame", "7"])
        assert parsed.frame == 7

    def test_add_args_dest_collision_raises(self):
        from painted.cli import Tag
        from painted.cli.types import build_parser

        def add_args(p):
            # distinct option string, same dest — argparse won't catch it,
            # the dest-collision check must.
            p.add_argument("--think", dest="thinking")

        with pytest.raises(DeclarationError, match="collides"):
            build_parser(add_args=add_args, tags=[Tag("thinking", "reasoning")])

    def test_mode_flags_follow_modes(self):
        from painted.cli.types import build_parser

        with_live = {
            s
            for a in build_parser(modes={OutputMode.STATIC, OutputMode.LIVE})._actions
            for s in a.option_strings
        }
        assert "--live" in with_live
        without_live = {
            s for a in build_parser(modes={OutputMode.STATIC})._actions for s in a.option_strings
        }
        assert "--live" not in without_live


class TestArgsView:
    """ArgsView is a read-only attribute view; unknown names raise, never
    fabricate."""

    def test_attribute_access(self):
        from painted.cli import ArgsView

        view = ArgsView({"frame": 7, "name": "x"})
        assert view.frame == 7
        assert view["name"] == "x"
        assert "frame" in view
        assert view.get("missing", 99) == 99

    def test_unknown_name_raises(self):
        from painted.cli import ArgsView

        with pytest.raises(AttributeError):
            ArgsView({}).nope

    def test_read_only(self):
        from painted.cli import ArgsView

        with pytest.raises(AttributeError):
            ArgsView({"frame": 1}).frame = 2

    def test_empty_default(self):
        from painted.cli import ArgsView

        assert len(ArgsView()) == 0


class TestCtxArgs:
    """run_cli surfaces consumer add_args via ctx.args, excluding framework
    flags and declared tag/alias dests."""

    def test_consumer_arg_on_ctx(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def add_args(p):
            p.add_argument("--frame", type=int, default=0)

        def render(ctx, data):
            seen["frame"] = ctx.args.frame
            seen["has_quiet"] = "quiet" in ctx.args
            return Block.text("x", Style())

        run_cli(["--frame", "5"], render=render, fetch=lambda: "d", add_args=add_args)
        assert seen["frame"] == 5
        # framework flags are owned by the framework, not surfaced as args
        assert seen["has_quiet"] is False

    def test_declared_dest_excluded_from_args(self, monkeypatch):
        from painted.cli import Tag

        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def render(ctx, data):
            seen["has_thinking"] = "thinking" in ctx.args
            return Block.text("x", Style())

        run_cli(
            ["--thinking"],
            render=render,
            fetch=lambda: "d",
            tags=[Tag("thinking", "reasoning")],
        )
        # the tag compiles into fidelity, not ctx.args
        assert seen["has_thinking"] is False

    def test_empty_args_on_bare_invocation(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def render(ctx, data):
            seen["len"] = len(ctx.args)
            return Block.text("x", Style())

        run_cli([], render=render, fetch=lambda: "d")
        assert seen["len"] == 0


class TestFetchArityShim:
    """A 0-param fetch is called nullary (unchanged); a 1-param fetch receives
    ctx."""

    def test_nullary_fetch_untouched(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        calls = []

        def fetch():
            calls.append("nullary")
            return "d"

        run_cli([], render=lambda ctx, d: Block.text(d, Style()), fetch=fetch)
        assert calls == ["nullary"]

    def test_ctx_fetch_receives_ctx(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def add_args(p):
            p.add_argument("--frame", type=int, default=0)

        def fetch(ctx):
            seen["frame"] = ctx.args.frame
            return "d"

        run_cli(
            ["--frame", "3"],
            render=lambda ctx, d: Block.text(d, Style()),
            fetch=fetch,
            add_args=add_args,
        )
        assert seen["frame"] == 3

    def test_ctx_fetch_on_json_path(self, monkeypatch):
        """JSON export carries ctx too, so an arity-1 fetch still works."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def fetch(ctx):
            seen["called"] = True
            return {"ok": True}

        code = run_cli(
            ["--json"],
            render=lambda ctx, d: Block.text("x", Style()),
            fetch=fetch,
        )
        assert code == 0
        assert seen["called"] is True
