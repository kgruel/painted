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

from painted import Block, RefScheme, Style, current_ref_schemes, use_refs
from painted.cli import (
    CliContext,
    CliRunner,
    Fidelity,
    HelpArg,
    OutputMode,
    Zoom,
    run_cli,
)
from painted.core.errors import ContractError, DeclarationError


# =============================================================================
# CliRunner dispatch (from test_fidelity.py)
# =============================================================================


class TestCliRunner:
    """Tests for CliRunner class."""

    def test_invalid_live_delivery_raises_at_construction(self):
        """Misconfiguration raises immediately, never degrades at dispatch."""
        with pytest.raises(DeclarationError, match="live_delivery"):
            CliRunner(
                renderer=lambda data, fidelity, width: Block.text("x", Style()),
                fetch=lambda: "x",
                live_delivery="surfce",
            )

    def test_static_output(self, monkeypatch):
        """Static mode uses print_block and returns 0. ctx.mode is surfaced
        through an arity-1 fetch(ctx) — renderer= never receives ctx."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        render_called = False
        fetch_called = False
        received_ctx = None

        def renderer(data: str, fidelity: Fidelity, width: int | None) -> Block:
            nonlocal render_called
            render_called = True
            return Block.text(f"depth={fidelity.depth}: {data}", Style())

        def fetch(ctx: CliContext) -> str:
            nonlocal fetch_called, received_ctx
            fetch_called = True
            received_ctx = ctx
            return "test data"

        # AUTO resolves to STATIC when not a TTY
        result = run_cli(
            [],
            renderer=renderer,
            fetch=fetch,
        )

        assert result == 0
        assert render_called, "renderer should be called"
        assert fetch_called, "fetch should be called"
        assert received_ctx.mode == OutputMode.STATIC

    def test_json_output(self, capsys, monkeypatch):
        """JSON mode outputs JSON."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def renderer(data: dict, fidelity: Fidelity, width: int | None) -> Block:
            return Block.text("unused", Style())

        def fetch() -> dict:
            return {"status": "ok", "count": 42}

        result = run_cli(
            ["--json"],
            renderer=renderer,
            fetch=fetch,
        )

        assert result == 0
        captured = capsys.readouterr()
        assert '"status": "ok"' in captured.out
        assert '"count": 42' in captured.out

    def test_zoom_passed_to_renderer(self, monkeypatch):
        """Zoom level (fidelity.depth) is passed to the renderer."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        received_depth = None

        def renderer(data: str, fidelity: Fidelity, width: int | None) -> Block:
            nonlocal received_depth
            received_depth = fidelity.depth
            return Block.text(data, Style())

        run_cli(
            ["-v"],
            renderer=renderer,
            fetch=lambda: "data",
        )

        assert received_depth is not None
        assert Zoom(received_depth) == Zoom.DETAILED

    def test_fidelity_passed_to_renderer(self, monkeypatch):
        """Fidelity from --max-chars/--max-lines is passed to the renderer."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        received_fidelity = None

        def renderer(data: str, fidelity: Fidelity, width: int | None) -> Block:
            nonlocal received_fidelity
            received_fidelity = fidelity
            return Block.text(data, Style())

        run_cli(
            ["--max-chars", "50", "--max-lines", "10"],
            renderer=renderer,
            fetch=lambda: "data",
            budgets=True,
        )

        assert received_fidelity is not None
        assert received_fidelity.chars == 50
        assert received_fidelity.lines == 10

    def test_no_fidelity_flags_gives_zero_limits(self, monkeypatch):
        """Without density flags, fidelity.chars and .lines are 0 (unlimited)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        received_fidelity = None

        def renderer(data: str, fidelity: Fidelity, width: int | None) -> Block:
            nonlocal received_fidelity
            received_fidelity = fidelity
            return Block.text(data, Style())

        run_cli(
            [],
            renderer=renderer,
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
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
            fetch=lambda: "data",
            handlers={OutputMode.INTERACTIVE: custom_interactive},
        )

        assert handler_called
        assert received_ctx.mode == OutputMode.INTERACTIVE
        assert result == 42

    def test_fetch_failure_preserves_multiline_message(self, capsys, monkeypatch):
        """A consumer's error message owns its line structure — a three-line
        did-you-mean block arrives on stderr as three lines, never flattened
        to one run-on line (friction: cli-error-multiline-flattening)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def fetch() -> str:
            raise ValueError("vertex not found: projcets\nDid you mean: projects?\nKnown: a, b")

        result = run_cli([], renderer=lambda d, f, w: Block.text("x", Style()), fetch=fetch)

        assert result == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        lines = [ln.rstrip() for ln in captured.err.splitlines() if ln.strip()]
        assert lines == [
            "vertex not found: projcets",
            "Did you mean: projects?",
            "Known: a, b",
        ]

    def test_fetch_failure_stderr_ansi_follows_stderr_plane(self, capsys, monkeypatch):
        """Error ANSI gates on stderr's own TTY-ness overridden by the --plain
        request — never the resolved stdout format (same rule as the refusal
        seam). Piped stdout with a TTY stderr still styles the error; --plain
        suppresses it."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        monkeypatch.setattr("sys.stderr.isatty", lambda: True)

        def fetch() -> str:
            raise ValueError("styled nope")

        renderer = lambda d, f, w: Block.text("x", Style())  # noqa: E731

        assert run_cli([], renderer=renderer, fetch=fetch) == 1
        styled = capsys.readouterr().err
        assert "styled nope" in styled
        assert "\x1b[" in styled  # stderr is a TTY: the error renders styled

        assert run_cli(["--plain"], renderer=renderer, fetch=fetch) == 1
        plain = capsys.readouterr().err
        assert "styled nope" in plain
        assert "\x1b[" not in plain  # the --plain request wins on the stderr plane

    def test_fetch_failure_static_renders_error_and_returns_1(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        render_called = False

        def renderer(data: str, fidelity: Fidelity, width: int | None) -> Block:
            nonlocal render_called
            render_called = True
            return Block.text("unused", Style())

        def fetch() -> str:
            raise ValueError("nope")

        result = run_cli([], renderer=renderer, fetch=fetch)

        assert result == 1
        assert render_called is False
        captured = capsys.readouterr()
        assert "nope" in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""  # stdout stays a clean data channel on failure

    def test_fetch_failure_json_outputs_error_object_and_returns_1(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def fetch() -> dict:
            raise RuntimeError("badness")

        result = run_cli(
            ["--json"],
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
            fetch=fetch,
        )

        assert result == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert payload == {"error": "badness"}
        assert captured.out == ""  # `tool --json > file` never writes an error as data

    def test_render_failure_static_renders_minimal_error_and_returns_2(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def renderer(data: str, fidelity: Fidelity, width: int | None) -> Block:
            raise KeyError("kaboom")

        result = run_cli([], renderer=renderer, fetch=lambda: "ok")

        assert result == 2
        captured = capsys.readouterr()
        assert "KeyError" in captured.err
        assert "kaboom" in captured.err
        assert "Traceback" not in captured.err
        assert captured.out == ""


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
        with pytest.warns(DeprecationWarning, match="render="):
            rc = run_cli(["--plain"], _legacy, lambda: "WORLD")
        assert rc == 0
        assert "legacy WORLD" in capsys.readouterr().out

    def test_legacy_keyword_form_unchanged(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.warns(DeprecationWarning, match="render="):
            rc = run_cli(["--plain"], render=_legacy, fetch=lambda: "WORLD")
        assert rc == 0
        assert "legacy WORLD" in capsys.readouterr().out

    def test_legacy_positional_construction_preserved(self, capsys, monkeypatch):
        """``CliRunner(render, fetch)`` — the legacy positional layout — still
        binds render then fetch. ``renderer`` is kw_only, so it never steals the
        second positional slot (which would fault as a 'both' declaration)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.warns(DeprecationWarning, match="render="):
            runner = CliRunner(_legacy, lambda: "POS")  # positional render, positional fetch
        assert runner.render is _legacy
        assert runner.renderer is None
        rc = runner.run(["--plain"])
        assert rc == 0
        assert "legacy POS" in capsys.readouterr().out

    def test_render_emits_deprecation_warning_once_at_construction(self, monkeypatch):
        """0.12 opens the gate (§3, §12 M5-d): render= warns exactly once, at
        construction — not per frame — naming the renderer= replacement and
        the design doc."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.warns(DeprecationWarning, match="renderer=.*RENDERER_CONTRACT_DESIGN") as rec:
            run_cli(["--plain"], render=_legacy, fetch=lambda: "x")
        deprecations = [w for w in rec.list if issubclass(w.category, DeprecationWarning)]
        assert len(deprecations) == 1
        assert deprecations[0].filename == __file__

    def test_renderer_form_emits_no_deprecation_warning(self, monkeypatch, recwarn):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        run_cli(["--plain"], renderer=_renderer, fetch=lambda: "x")
        assert not [w for w in recwarn.list if issubclass(w.category, DeprecationWarning)]

    def test_transcription_default_emits_no_deprecation_warning(self, monkeypatch, recwarn):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        run_cli(["--plain"], fetch=lambda: "x")
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

    def test_forced_plain_live_reoffers_current_geometry_per_frame(self, monkeypatch, capsys):
        """--plain --live at a real TTY takes the non-ANSI cadence branch, but
        the offer is still per-frame (§6): --plain drops ANSI, not the
        viewport, so each state's render re-reads current columns — never the
        detection-time ctx.width."""
        import os

        cols = iter([30, 50])
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
        # Forced-plain on a TTY (use_ansi False, is_tty True) → non-ANSI branch.
        code = runner._dispatch(_ctx(is_tty=True, width=999, use_ansi=False, mode=OutputMode.LIVE))
        assert code == 0
        assert offered == [30, 50]  # never the stale detection-time 999
        assert "b" in capsys.readouterr().out  # the last frame still deposits

    def test_forced_plain_live_pipe_still_offers_none(self, monkeypatch, capsys):
        """The same branch under a pipe: the re-read geometry is discarded by
        the offer rule — every frame's offer stays None (natural sizing)."""
        offered: list[int | None] = []

        def rnd(data, fidelity, width):
            offered.append(width)
            return Block.text(str(data), Style())

        async def fake_stream():
            yield "a"
            yield "b"

        runner = CliRunner(renderer=rnd, fetch=lambda: "unused", fetch_stream=fake_stream)
        code = runner._dispatch(_ctx(is_tty=False, width=80, use_ansi=False, mode=OutputMode.LIVE))
        assert code == 0
        assert offered == [None, None]
        capsys.readouterr()


def _height_renderer(data, fidelity, width, *, height):
    """A height-aware renderer (docs/HOST_RUNG_DESIGN.md §4). Natural content
    when the offer is omitted; an exact H-row Block when one is made."""
    if height is None:
        return Block.text(f"data={data}", Style())
    return Block.empty(max(1, width or 1), height)


class TestHeightDeclaration:
    """The `height_renderer=` declaration (docs/HOST_RUNG_DESIGN.md §3–4): the
    acceptance arm, mutually exclusive with every other renderer form, all four
    normalizing into the private `_binding` record dispatch consults."""

    def test_height_renderer_alone_is_a_complete_declaration(self):
        # No renderer= needed: height_renderer= is a full declaration on its own.
        runner = CliRunner(height_renderer=_height_renderer, fetch=lambda: "d")
        assert runner.render is None
        assert runner.renderer is None  # not required, not installed
        assert runner.height_renderer is _height_renderer

    def test_height_renderer_and_renderer_collide_at_construction(self):
        with pytest.raises(DeclarationError, match="not both"):
            CliRunner(
                renderer=_renderer,
                height_renderer=_height_renderer,
                fetch=lambda: "d",
            )

    def test_height_renderer_and_legacy_render_collide_at_construction(self):
        # Mutual exclusion covers the legacy render= form too (§4, round-3 P2).
        with pytest.raises(DeclarationError, match="not both"):
            CliRunner(
                render=_legacy,
                height_renderer=_height_renderer,
                fetch=lambda: "d",
            )

    def test_height_renderer_collisions_bypass_the_parser(self, monkeypatch):
        """Like every render-path fault, the collision fires at construction on
        empty argv — before any parser is built."""
        import painted.cli.runner as runner_mod

        def _boom(*a, **k):
            raise AssertionError("build_parser must not be reached for a render-path fault")

        monkeypatch.setattr(runner_mod, "build_parser", _boom)
        with pytest.raises(DeclarationError):
            run_cli([], renderer=_renderer, height_renderer=_height_renderer, fetch=lambda: "d")

    def test_height_renderer_with_tags_is_allowed(self):
        # The transcription fence is scoped to the *no-renderer* form: a declared
        # height_renderer= consumes fidelity.visible like renderer=, so tags= is
        # valid alongside it.
        from painted.cli import Tag

        runner = CliRunner(
            height_renderer=_height_renderer,
            fetch=lambda: "d",
            tags=[Tag("thinking", "reasoning")],
        )
        assert runner.height_renderer is _height_renderer


class TestBindingRecord:
    """All four authored forms normalize into `_binding` (§3), which carries the
    declared arm — dispatch reads this, never the callable's arity."""

    def test_height_renderer_records_the_accepting_arm(self):
        runner = CliRunner(height_renderer=_height_renderer, fetch=lambda: "d")
        assert runner._binding.accepts_height is True
        assert runner._binding.legacy is False
        assert runner._binding.call is _height_renderer

    def test_renderer_records_the_three_argument_arm(self):
        runner = CliRunner(renderer=_renderer, fetch=lambda: "d")
        assert runner._binding.accepts_height is False
        assert runner._binding.legacy is False
        assert runner._binding.call is _renderer

    def test_legacy_render_records_the_legacy_arm(self):
        with pytest.warns(DeprecationWarning):
            runner = CliRunner(render=_legacy, fetch=lambda: "d")
        assert runner._binding.accepts_height is False
        assert runner._binding.legacy is True
        assert runner._binding.call is _legacy

    def test_transcription_default_records_the_three_argument_arm(self):
        # The *neither* form installs the transcription default into `renderer`;
        # the binding wraps it, undeclared like any renderer= form.
        runner = CliRunner(fetch=lambda: "d")
        assert runner._binding.accepts_height is False
        assert runner._binding.legacy is False
        assert runner._binding.call is runner.renderer  # the installed default


class TestHeightOfferMatrix:
    """The three-row offer matrix (§3). In S1 every shipped delivery is
    gated-off — the Q7 STATIC-TTY fence and off-TTY always — so a declared
    binding is offered `height=None` everywhere; an undeclared binding is never
    handed the keyword at all."""

    def test_undeclared_renderer_is_never_passed_the_height_keyword(self, capsys):
        """An undeclared renderer whose signature rejects a `height` kwarg proves
        the keyword is never passed: if it were, the call would TypeError. It
        renders cleanly on both a pipe and a TTY."""

        def strict(data, fidelity, width):  # no height, no **kwargs
            return Block.text("x", Style())

        runner = CliRunner(renderer=strict, fetch=lambda: "d")
        assert runner._dispatch(_ctx(is_tty=False, width=80)) == 0
        assert runner._dispatch(_ctx(is_tty=True, width=80)) == 0
        capsys.readouterr()

    def test_declared_renderer_receives_explicit_none_off_a_tty(self, capsys):
        received: list[int | None] = []

        def rec(data, fidelity, width, *, height):
            received.append(height)
            return Block.text("x", Style())

        runner = CliRunner(height_renderer=rec, fetch=lambda: "d")
        assert runner._dispatch(_ctx(is_tty=False, width=80)) == 0
        assert received == [None]  # explicit None, not Python's default
        capsys.readouterr()

    def test_declared_renderer_receives_explicit_none_on_a_static_tty(self, capsys):
        """The Q7 fence (§3): a declared renderer on a STATIC TTY receives
        `height=None` unconditionally — the host does not consult terminal
        height even though it is known (here a 60-row terminal)."""
        received: list[int | None] = []

        def rec(data, fidelity, width, *, height):
            received.append(height)
            return Block.text("x", Style())

        runner = CliRunner(height_renderer=rec, fetch=lambda: "d")
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=60,  # a known terminal height — still not offered
        )
        assert runner._dispatch(ctx) == 0
        assert received == [None]
        capsys.readouterr()

    def test_declared_renderer_renders_natural_content_end_to_end(self, capsys, monkeypatch):
        """The full run_cli path with a height_renderer=: gated-off, so it renders
        its natural (height=None) content."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        rc = run_cli(["--plain"], height_renderer=_height_renderer, fetch=lambda: "HELLO")
        assert rc == 0
        assert "data=HELLO" in capsys.readouterr().out


class TestHeightExactness:
    """The offer-site exactness contract (§5), exercised through `_render` (the
    offer site) and the `_verify_height` helper directly, since no shipped S1
    path offers an integer H yet."""

    def test_offered_height_zero_requires_an_exact_zero_row_block(self):
        # H=0 is a valid offer (§5): the renderer returns Block.empty(w, 0).
        runner = CliRunner(height_renderer=_height_renderer, fetch=lambda: "d")
        block = runner._render(_ctx(is_tty=True, width=10), "d", 10, height=0)
        assert block.height == 0

    def test_offered_height_is_enforced_exactly(self):
        runner = CliRunner(height_renderer=_height_renderer, fetch=lambda: "d")
        block = runner._render(_ctx(is_tty=True, width=10), "d", 10, height=7)
        assert block.height == 7

    def test_wrong_height_faults_at_the_offer_site(self):
        # A conforming renderer would return H rows; this one lies, returning 2.
        def liar(data, fidelity, width, *, height):
            return Block.empty(max(1, width or 1), 2)

        runner = CliRunner(height_renderer=liar, fetch=lambda: "d")
        with pytest.raises(ContractError, match="exactly H rows"):
            runner._render(_ctx(is_tty=True, width=10), "d", 10, height=5)

    def test_negative_offer_faults_before_the_renderer_runs(self):
        # A negative H is a host bug (§5) — it must fault before app code is
        # called, never handing a bogus allocation to the renderer.
        called = {"v": False}

        def rec(data, fidelity, width, *, height):
            called["v"] = True
            return Block.empty(1, 0)

        runner = CliRunner(height_renderer=rec, fetch=lambda: "d")
        with pytest.raises(ContractError, match="non-negative"):
            runner._render(_ctx(is_tty=True, width=10), "d", 10, height=-1)
        assert called["v"] is False  # the renderer was never invoked

    def test_none_offer_performs_no_exactness_check(self):
        # The omitted arm: natural content of any height is fine.
        runner = CliRunner(height_renderer=_height_renderer, fetch=lambda: "d")
        block = runner._render(_ctx(is_tty=True, width=10), "some data", 10, height=None)
        assert block.height >= 1  # natural sizing, unconstrained


def _ansi_ctx(*, width: int = 80) -> CliContext:
    return CliContext(
        fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
        mode=OutputMode.STATIC,
        use_ansi=True,
        is_tty=True,
        width=width,
        height=24,
    )


class TestRefSchemes:
    """ref_schemes= (§7): the runner-owned bracket around render +
    serialization. Static declarations validate at construction
    (DeclarationError); a callable evaluates per fetch, in the render phase —
    a raising callable enters the render-error path unchanged, an invalid
    result faults ContractError. Excluded from handler-dispatched modes
    (static only) and the --json fork (never, static or callable)."""

    def test_bad_name_validates_at_construction(self):
        with pytest.raises(DeclarationError, match="kebab-case"):
            CliRunner(
                renderer=lambda data, fidelity, width: Block.text("x", Style()),
                fetch=lambda: "x",
                ref_schemes=[RefScheme("Bad_Name", lambda v: v)],
            )

    def test_duplicate_names_validate_at_construction(self):
        with pytest.raises(DeclarationError, match="declared twice"):
            CliRunner(
                renderer=lambda data, fidelity, width: Block.text("x", Style()),
                fetch=lambda: "x",
                ref_schemes=[
                    RefScheme("fact", lambda v: v),
                    RefScheme("fact", lambda v: v.upper()),
                ],
            )

    def test_non_refscheme_element_validates_at_construction(self):
        with pytest.raises(DeclarationError, match="not a RefScheme"):
            CliRunner(
                renderer=lambda data, fidelity, width: Block.text("x", Style()),
                fetch=lambda: "x",
                ref_schemes=["not-a-scheme"],  # type: ignore[list-item]
            )

    def test_non_sequence_non_callable_validates_at_construction(self):
        """A set (or any object that is neither the declared Sequence shape
        nor callable) must fault DeclarationError at construction — not be
        silently misclassified as "callable" and crash with an unrelated
        TypeError at render time (P2-1)."""
        with pytest.raises(DeclarationError, match="Sequence of RefScheme"):
            CliRunner(
                renderer=lambda data, fidelity, width: Block.text("x", Style()),
                fetch=lambda: "x",
                ref_schemes={RefScheme("fact", lambda v: v)},  # type: ignore[arg-type]
            )

    def test_post_construction_mutation_does_not_reopen_the_declaration(self, capsys):
        """The static form is frozen at construction: mutating the
        caller-owned list afterward (e.g. appending a duplicate name) must
        not detonate a mid-cycle DeclarationError from use_refs (P1-1)."""
        schemes = [RefScheme("fact", lambda v: f"https://loops.dev/f/{v}")]

        def rnd(data, fidelity, width):
            return Block.text("deploy", Style(), ref="fact:01")

        runner = CliRunner(renderer=rnd, fetch=lambda: "x", ref_schemes=schemes)
        schemes.append(RefScheme("fact", lambda v: v))  # a duplicate name, added after construction

        code = runner._run_static(_ansi_ctx())
        assert code == 0  # not 2 — the mutation never reaches the bracket
        assert "\x1b]8;;https://loops.dev/f/01" in capsys.readouterr().out

    def test_callable_result_rejects_a_set(self, capsys):
        """The callable-result route enforces the same Sequence[RefScheme]
        shape as the static route (P2-1) — a set is not a Sequence, even
        though it's iterable."""

        def bad(state):
            return {RefScheme("fact", lambda v: v)}

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "x",
            ref_schemes=bad,
        )
        code = runner._run_static(_ansi_ctx())
        assert code == 2
        err = capsys.readouterr().err
        assert "ContractError" in err
        assert "Sequence of RefScheme" in err

    def test_static_ref_schemes_installs_around_render_and_serialize(self, capsys):
        def rnd(data, fidelity, width):
            return Block.text("deploy", Style(), ref="fact:01")

        runner = CliRunner(
            renderer=rnd,
            fetch=lambda: "x",
            ref_schemes=[RefScheme("fact", lambda v: f"https://loops.dev/f/{v}")],
        )
        code = runner._run_static(_ansi_ctx())
        assert code == 0
        assert "\x1b]8;;https://loops.dev/f/01" in capsys.readouterr().out

    def test_absent_ref_schemes_leaves_ambient_untouched(self, capsys):
        """No declaration → the framework installs no bracket at all: an
        app's own ambient use_refs() keeps flowing through the CLI tier."""

        def rnd(data, fidelity, width):
            return Block.text("deploy", Style(), ref="fact:01")

        with use_refs(RefScheme("fact", lambda v: f"https://ambient/{v}")):
            runner = CliRunner(renderer=rnd, fetch=lambda: "x")  # ref_schemes absent
            code = runner._run_static(_ansi_ctx())

        assert code == 0
        assert "https://ambient/01" in capsys.readouterr().out

    def test_empty_ref_schemes_disables_ambient(self, capsys):
        """ref_schemes=[] is a valid explicit empty declaration: it disables
        ambient resolution for the runner-owned cycle, restoring the prior
        ambient state once the bracket exits."""

        def rnd(data, fidelity, width):
            return Block.text("deploy", Style(), ref="fact:01")

        with use_refs(RefScheme("fact", lambda v: f"https://ambient/{v}")):
            runner = CliRunner(renderer=rnd, fetch=lambda: "x", ref_schemes=[])
            code = runner._run_static(_ansi_ctx())
            # ambient state is restored once the runner-owned bracket exits
            assert "fact" in current_ref_schemes()

        assert code == 0
        out = capsys.readouterr().out
        assert "\x1b]8;;" not in out  # the ref is inert — no hyperlink at all

    def test_callable_evaluates_against_the_fetched_state(self, capsys):
        seen: list[object] = []

        def schemes_for(state):
            seen.append(state)
            return [RefScheme("fact", lambda v: f"https://x/{state}/{v}")]

        def rnd(data, fidelity, width):
            return Block.text("deploy", Style(), ref="fact:01")

        runner = CliRunner(renderer=rnd, fetch=lambda: "abc", ref_schemes=schemes_for)
        code = runner._run_static(_ansi_ctx())
        assert code == 0
        assert seen == ["abc"]
        assert "\x1b]8;;https://x/abc/01" in capsys.readouterr().out

    def test_callable_raising_propagates_unchanged_into_render_error_path(self, capsys):
        def boom(state):
            raise RuntimeError("app boom")

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "x",
            ref_schemes=boom,
        )
        code = runner._run_static(_ansi_ctx())
        assert code == 2  # the render-error exit code, not a special one
        err = capsys.readouterr().err
        assert "RuntimeError: app boom" in err
        assert "ContractError" not in err  # unwrapped — an app fault, not painted's

    def test_callable_invalid_element_faults_contracterror(self, capsys):
        def bad(state):
            return [object()]  # not a RefScheme

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "x",
            ref_schemes=bad,
        )
        code = runner._run_static(_ansi_ctx())
        assert code == 2  # same render-error path as a renderer fault
        assert "ContractError" in capsys.readouterr().err

    def test_callable_duplicate_names_faults_contracterror(self, capsys):
        def bad(state):
            return [RefScheme("fact", lambda v: v), RefScheme("fact", lambda v: v)]

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "x",
            ref_schemes=bad,
        )
        code = runner._run_static(_ansi_ctx())
        assert code == 2
        err = capsys.readouterr().err
        assert "ContractError" in err
        assert "declared twice" in err

    def test_callable_result_is_validated_before_any_use_refs_call(self):
        """A bad result faults ContractError directly — never use_refs's own
        DeclarationError, which must not leak mid-cycle (ERRORS_DESIGN)."""

        def bad(state):
            return [object()]

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "x",
            ref_schemes=bad,
        )
        with pytest.raises(ContractError):
            runner._resolve_ref_schemes("x")

    def test_render_error_path_never_the_fetch_path(self, capsys):
        """A resolution fault is a declaration-time fault, not a data fault —
        it must never be misclassified as a fetch failure (exit 1)."""

        def boom(state):
            raise RuntimeError("scheme boom")

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "x",
            ref_schemes=boom,
        )
        code = runner._run_static(_ansi_ctx())
        assert code == 2  # not 1 — never the fetch path

    def test_handler_mode_does_not_evaluate_a_callable(self, monkeypatch):
        """Handler paths are excluded: the framework neither fetches nor
        renders there, so a callable has no state boundary to evaluate."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        called = {"v": False}

        def never_called(state):
            called["v"] = True
            return []

        def handler(ctx: CliContext) -> int:
            return 0

        result = run_cli(
            ["-i"],
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
            fetch=lambda: "data",
            handlers={OutputMode.INTERACTIVE: handler},
            ref_schemes=never_called,
        )
        assert result == 0
        assert called["v"] is False

    def test_handler_mode_installs_a_static_declaration(self, monkeypatch):
        """A static sequence needs no state and installs around the handler
        invocation like any other declared scope."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen: dict[str, set[str]] = {}

        def handler(ctx: CliContext) -> int:
            seen["schemes"] = set(current_ref_schemes())
            return 0

        result = run_cli(
            ["-i"],
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
            fetch=lambda: "data",
            handlers={OutputMode.INTERACTIVE: handler},
            ref_schemes=[RefScheme("fact", lambda v: v)],
        )
        assert result == 0
        assert seen["schemes"] == {"fact"}
        assert current_ref_schemes() == {}  # released after the bracket exits

    def test_json_export_never_evaluates_ref_schemes(self, capsys, monkeypatch):
        """--json is excluded absolutely, static and callable alike: data
        export never renders, never serializes a Block."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        called = {"v": False}

        def never_called(state):
            called["v"] = True
            return []

        result = run_cli(
            ["--json"],
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
            fetch=lambda: {"a": 1},
            ref_schemes=never_called,
        )
        assert result == 0
        assert called["v"] is False
        assert json.loads(capsys.readouterr().out) == {"a": 1}


class TestRunCliHelp:
    """Integration tests for --help with command args."""

    def test_help_with_help_args_shows_command_args(self, capsys, monkeypatch):
        """--help with help_args shows command args prominently."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--help"],
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
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
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
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
            renderer=lambda data, fidelity, width: Block.text("unused", Style()),
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
            renderer=lambda data, fidelity, width: Block.text(str(data), Style()),
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
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "ok",
            handlers={OutputMode.INTERACTIVE: handler},
        )
        assert result == 0

    def test_json_format_implies_static(self, capsys, monkeypatch):
        """--json with AUTO mode resolves to STATIC."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--json"],
            renderer=lambda data, fidelity, width: Block.text(str(data), Style()),
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
            renderer=lambda data, fidelity, width: Block.text("hello", Style()),
            fetch=lambda: "ok",
        )
        assert result == 0

    def test_quiet_implies_static(self, monkeypatch):
        """Zoom.MINIMAL (-q) with AUTO mode resolves to STATIC."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["-q"],
            renderer=lambda data, fidelity, width: Block.text("minimal", Style()),
            fetch=lambda: "ok",
        )
        assert result == 0


class TestCliRunnerJsonPath:
    def test_json_non_dataclass_state(self, capsys, monkeypatch):
        """JSON mode handles non-dataclass state (dict, list, etc.)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        result = run_cli(
            ["--json"],
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
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
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: (_ for _ in ()).throw(IOError("disk full")),
        )
        assert result == 1
        captured = capsys.readouterr()
        assert json.loads(captured.err) == {"error": "disk full"}
        assert captured.out == ""


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
            renderer=lambda data, fidelity, width: Block.text("live-ok", Style()),
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
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
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

        def bad_render(data, fidelity, width):
            raise ValueError("render broke")

        runner = CliRunner(
            renderer=bad_render,
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
            renderer=lambda data, fidelity, width: Block.text("interactive-fallback", Style()),
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
            renderer=lambda data, fidelity, width: Block.text(str(data), Style()),
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

        def maybe_bad_render(data, fidelity, width):
            if data == "boom":
                raise ValueError("render broke")
            return Block.text(str(data), Style())

        runner = CliRunner(
            renderer=maybe_bad_render,
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
            renderer=lambda data, fidelity, width: Block.text(str(data), Style()),
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
        """ctx.args is surfaced to an arity-1 fetch (TestFetchArityShim) — the
        same ctx a renderer= caller never sees, so probing it here goes
        through fetch rather than the legacy render= form."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def add_args(p):
            p.add_argument("--frame", type=int, default=0)

        def fetch(ctx):
            seen["frame"] = ctx.args.frame
            seen["has_quiet"] = "quiet" in ctx.args
            return "d"

        run_cli(["--frame", "5"], renderer=_renderer, fetch=fetch, add_args=add_args)
        assert seen["frame"] == 5
        # framework flags are owned by the framework, not surfaced as args
        assert seen["has_quiet"] is False

    def test_declared_dest_excluded_from_args(self, monkeypatch):
        from painted.cli import Tag

        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def fetch(ctx):
            seen["has_thinking"] = "thinking" in ctx.args
            return "d"

        run_cli(
            ["--thinking"],
            renderer=_renderer,
            fetch=fetch,
            tags=[Tag("thinking", "reasoning")],
        )
        # the tag compiles into fidelity, not ctx.args
        assert seen["has_thinking"] is False

    def test_empty_args_on_bare_invocation(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def fetch(ctx):
            seen["len"] = len(ctx.args)
            return "d"

        run_cli([], renderer=_renderer, fetch=fetch)
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

        run_cli([], renderer=lambda data, fidelity, width: Block.text(data, Style()), fetch=fetch)
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
            renderer=lambda data, fidelity, width: Block.text(data, Style()),
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
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=fetch,
        )
        assert code == 0
        assert seen["called"] is True
