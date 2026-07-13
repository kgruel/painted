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


def _renderer(data, fidelity, width):
    """A (data, fidelity, width) → Block renderer — the §1 contract shape."""
    return Block.text(f"data={data} depth={fidelity.depth} width={width}", Style())


def _legacy(ctx: CliContext, data) -> Block:
    return Block.text(f"legacy {data}", Style())


class TestRendererContractConstruction:
    """S1 of the renderer contract (docs/RENDERER_CONTRACT_DESIGN.md §3).

    All render-path declaration validation lives at runner construction, not
    parser construction: the empty-argv fast path never builds a parser, and
    neither render/renderer/fetch mints a flag, so a parser-time check would
    never fire on bare ``tool``. Each fault is therefore asserted on **empty
    argv** — the path that skips the parser entirely.
    """

    def test_missing_fetch_raises_at_construction(self):
        with pytest.raises(DeclarationError, match="fetch"):
            run_cli([], renderer=_renderer)

    def test_both_render_and_renderer_raises_at_construction(self):
        with pytest.raises(DeclarationError, match="not both"):
            run_cli([], _legacy, lambda: "x", renderer=_renderer)

    def test_neither_installs_a_default_renderer(self):
        # S3: neither render= nor renderer= no longer faults — the framework
        # installs its transcription default, so there is always exactly one
        # renderer at dispatch (§4). We assert only the structural fact and that
        # the private default does not leak; *behavior* (that it transcribes) is
        # pinned by TestTranscriptionDefault, not by the callable's identity.
        runner = CliRunner(fetch=lambda: "x")
        assert runner.render is None
        assert runner.renderer is not None  # a renderer was installed
        # field(repr=False): the private default never surfaces through the repr.
        assert "renderer=" not in repr(runner)

    def test_tags_without_a_renderer_faults_at_construction(self):
        # The fence (§4): transcription cannot consume fidelity.visible, so a
        # declared Tag would mint a dead --{name} flag. tags= with neither
        # render= nor renderer= faults — taking the old *neither* fault's place.
        from painted.cli import Tag

        with pytest.raises(DeclarationError, match="tags= requires"):
            CliRunner(fetch=lambda: "x", tags=[Tag("thinking", "Show reasoning")])

    def test_tags_with_a_renderer_is_allowed(self):
        # The fence is scoped to the *neither* form: a declared renderer can
        # consume fidelity.visible, so tags= stays valid alongside one.
        runner = CliRunner(renderer=_renderer, fetch=lambda: "x", tags=[])
        assert runner.renderer is _renderer

    def test_faults_bypass_the_parser(self, monkeypatch):
        """The fault fires before any parser is built (empty argv, no flags)."""
        import painted.cli.runner as runner_mod

        def _boom(*a, **k):  # a parser build here would mean the check ran too late
            raise AssertionError("build_parser must not be reached for a render-path fault")

        monkeypatch.setattr(runner_mod, "build_parser", _boom)
        with pytest.raises(DeclarationError):
            run_cli([], render=_legacy, renderer=_renderer, fetch=lambda: "x")


class TestRendererContractDispatch:
    """Every published call form dispatches correctly (§11)."""

    def test_renderer_keyword_form_dispatches(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        rc = run_cli(["--plain"], renderer=_renderer, fetch=lambda: "HELLO")
        assert rc == 0
        out = capsys.readouterr().out
        # renderer receives the compiled Fidelity intact (depth=1 for SUMMARY).
        assert "data=HELLO" in out
        assert "depth=1" in out

    def test_renderer_receives_fidelity_intact_and_offered_width_forwarded(self):
        """The compiled Fidelity is passed *whole* — the same object, never
        decomposed and rebuilt — and the ``_render`` seam forwards whatever
        ``offered`` width the caller resolved, by value. The offer *rule*
        (TTY-vs-None) is ``_offered_width``'s job, tested separately; this
        pins that the seam does not re-derive it."""
        seen: dict = {}

        def rnd(data, fidelity, width):
            seen["fidelity"] = fidelity
            seen["width"] = width
            return Block.text("x", Style())

        runner = CliRunner(renderer=rnd, fetch=lambda: "d")
        ctx = CliContext(
            fidelity=Fidelity(depth=2, visible=frozenset({"thinking"})),
            mode=OutputMode.STATIC,
            use_ansi=False,
            is_tty=False,
            width=73,
            height=24,
        )
        runner._render(ctx, "d", 51)  # an explicit offer, distinct from ctx.width
        assert seen["fidelity"] is ctx.fidelity  # intact — the same object, not a copy
        assert seen["width"] == 51  # forwarded verbatim, not re-derived from ctx

    def test_legacy_positional_form_unchanged(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        rc = run_cli(["--plain"], _legacy, lambda: "WORLD")
        assert rc == 0
        assert "legacy WORLD" in capsys.readouterr().out

    def test_legacy_keyword_form_unchanged(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        rc = run_cli(["--plain"], render=_legacy, fetch=lambda: "WORLD")
        assert rc == 0
        assert "legacy WORLD" in capsys.readouterr().out

    def test_legacy_positional_construction_preserved(self, capsys, monkeypatch):
        """``CliRunner(render, fetch)`` — the legacy positional layout — still
        binds render then fetch. ``renderer`` is kw_only, so it never steals the
        second positional slot (which would fault as a 'both' declaration)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        runner = CliRunner(_legacy, lambda: "POS")  # positional render, positional fetch
        assert runner.render is _legacy
        assert runner.renderer is None
        rc = runner.run(["--plain"])
        assert rc == 0
        assert "legacy POS" in capsys.readouterr().out

    def test_render_emits_no_deprecation_warning(self, monkeypatch, recwarn):
        """0.11 keeps render= silent — the DeprecationWarning gate opens at 0.12 (§3)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        run_cli(["--plain"], render=_legacy, fetch=lambda: "x")
        assert not [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]


class TestTranscriptionDefault:
    """The *neither* form renders by transcription (§4) — the no-lens graduate
    invoked through the contract, not a paint() call."""

    def test_transcription_default_renders_fetched_data(self, capsys, monkeypatch):
        # No render=, no renderer=: the framework transcribes the fetched data.
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        rc = run_cli(["--plain"], fetch=lambda: {"status": "ok", "items": 42})
        assert rc == 0
        out = capsys.readouterr().out
        assert "status" in out and "ok" in out
        assert "items" in out and "42" in out

    def test_verbosity_visibly_changes_default_output(self, capsys, monkeypatch):
        # The honesty half that holds (§4): -q/-v arrive through fidelity.depth and
        # visibly change transcription output — depth is a facet it consumes.
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        run_cli(["--plain", "-q"], fetch=lambda: {"a": 1, "b": 2})
        quiet = capsys.readouterr().out
        run_cli(["--plain", "-vv"], fetch=lambda: {"a": 1, "b": 2})
        verbose = capsys.readouterr().out
        assert quiet != verbose
        assert "dict[2]" in quiet  # minimal depth transcribes the shape's count

    def test_pipe_transcribes_natural_width(self, capsys, monkeypatch):
        # On a pipe the offer is None (§5), so transcription renders natural: the
        # fabricated fallback width never reaches the renderer. A long value is not
        # clipped to a terminal column count it was never offered.
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        long_value = "x" * 120
        rc = run_cli(["--plain"], fetch=lambda: {"k": long_value})
        assert rc == 0
        assert long_value in capsys.readouterr().out

    def test_max_lines_visibly_truncates_default_output(self, capsys, monkeypatch):
        # The other honesty half (§4/§11): declared budgets consumed by
        # transcription visibly change output. --max-lines only exists because
        # budgets=True was declared; it samples the key-value table to N rows.
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def data():
            return {f"k{i}": i for i in range(10)}

        run_cli(["--plain", "-v"], fetch=data, budgets=True)
        unbudgeted = capsys.readouterr().out
        run_cli(["--plain", "-v", "--max-lines", "3"], fetch=data, budgets=True)
        budgeted = capsys.readouterr().out
        assert budgeted != unbudgeted
        assert "k9: 9" in unbudgeted  # all ten rows before the budget
        assert "k9: 9" not in budgeted  # sampled away by --max-lines 3
        assert "+7 more" in budgeted  # 10 - 3, with the honest overflow footer

    def test_max_chars_visibly_truncates_default_output(self, capsys, monkeypatch):
        # --max-chars caps a string value's display width; it exists only because
        # budgets=True was declared. Compared unbudgeted vs budgeted at the same
        # depth, the value is visibly shortened with an honest length indicator.
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def data():
            return {"k": "y" * 100}

        run_cli(["--plain", "-vv"], fetch=data, budgets=True)
        unbudgeted = capsys.readouterr().out
        run_cli(["--plain", "-vv", "--max-chars", "20"], fetch=data, budgets=True)
        budgeted = capsys.readouterr().out
        assert budgeted != unbudgeted
        assert "y" * 100 in unbudgeted  # full value at natural width, unbudgeted
        assert "y" * 100 not in budgeted  # capped
        assert "[100 chars]" in budgeted  # the honest truncation indicator


def _ctx(
    *,
    is_tty: bool,
    width: int,
    use_ansi: bool | None = None,
    mode: OutputMode = OutputMode.STATIC,
) -> CliContext:
    return CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=mode,
        use_ansi=is_tty if use_ansi is None else use_ansi,
        is_tty=is_tty,
        width=width,
        height=24,
    )


class TestOfferSeam:
    """The width offer rule (§5–6, S2). ``_offered_width`` is the one place the
    rule lives: stdout is a real viewport (a TTY) → offer geometry; any
    viewportless destination → offer None (natural). The live hosts re-offer
    *current* geometry per frame, so a mid-run resize re-enters the renderer as
    changed input."""

    def test_offered_width_offers_geometry_on_a_tty(self):
        ctx = _ctx(is_tty=True, width=80)
        # Default geometry is ctx.width (one-shot dispatch)…
        assert CliRunner._offered_width(ctx) == 80
        # …and a live path may override with the frame's current width.
        assert CliRunner._offered_width(ctx, 120) == 120

    def test_offered_width_offers_none_off_a_tty(self):
        ctx = _ctx(is_tty=False, width=80)
        assert CliRunner._offered_width(ctx) is None
        # The rule gates on the TTY, not the geometry: an offered frame width
        # is still discarded for None under a pipe.
        assert CliRunner._offered_width(ctx, 120) is None

    def test_plain_at_a_tty_still_offers_geometry(self):
        """Format is orthogonal to the offer: --plain drops ANSI, not the
        viewport. A real TTY's columns are real, so geometry is still offered
        (the gate is is_tty, not use_ansi) — end to end through static."""
        forced_plain_tty = _ctx(is_tty=True, width=88, use_ansi=False)
        assert CliRunner._offered_width(forced_plain_tty) == 88

        seen: dict = {}

        def rnd(data, fidelity, width):
            seen["width"] = width
            return Block.text("x", Style())

        CliRunner(renderer=rnd, fetch=lambda: "d")._run_static(forced_plain_tty)
        assert seen["width"] == 88

    def test_static_pipe_offers_none_to_the_renderer(self):
        """The pipe case arrives as width=None — natural sizing, no fabricated
        fallback. Driven through the real static delivery path."""
        seen: dict = {}

        def rnd(data, fidelity, width):
            seen["width"] = width
            return Block.text("x", Style())

        CliRunner(renderer=rnd, fetch=lambda: "d")._run_static(_ctx(is_tty=False, width=80))
        assert seen["width"] is None

    def test_static_tty_offers_ctx_width_to_the_renderer(self):
        seen: dict = {}

        def rnd(data, fidelity, width):
            seen["width"] = width
            return Block.text("x", Style())

        CliRunner(renderer=rnd, fetch=lambda: "d")._run_static(_ctx(is_tty=True, width=97))
        assert seen["width"] == 97

    def test_inplace_live_reoffers_current_geometry_per_frame(self, monkeypatch):
        """The in-place host owns a live viewport: each frame re-reads terminal
        geometry, so a mid-run resize changes the next offer (§6)."""

        class StubRenderer:
            def __init__(self, *args, **kwargs): ...
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def render(self, block: Block) -> None: ...
            def finalize(self) -> None: ...

        import painted.inplace as inplace_mod

        monkeypatch.setattr(inplace_mod, "InPlaceRenderer", StubRenderer)
        # Terminal resizes between the two frames: 30 cols, then 50.
        cols = iter([30, 50])
        import os

        monkeypatch.setattr(
            "shutil.get_terminal_size",
            lambda *a, **k: os.terminal_size((next(cols), 24)),
        )

        offered: list[int | None] = []

        def rnd(data, fidelity, width):
            offered.append(width)
            return Block.text(str(data), Style())

        async def fake_stream():
            yield "a"
            yield "b"

        runner = CliRunner(renderer=rnd, fetch=lambda: "unused", fetch_stream=fake_stream)
        # LIVE on a TTY viewport (use_ansi True, is_tty True) → in-place ANSI branch.
        runner._dispatch(_ctx(is_tty=True, width=999, use_ansi=True, mode=OutputMode.LIVE))
        assert offered == [30, 50]  # the resize re-entered as a changed offer


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
