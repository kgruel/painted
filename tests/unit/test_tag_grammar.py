"""Compilation laws for the disclosure grammar (docs/FIDELITY_DESIGN.md §4).

Tag declarations and depth aliases compile into Fidelity: flags generate from
declarations, implications resolve at compile time, collisions raise at parser
construction, and budgets gate the density flags. The acceptance classes pin
§6: siftd's and loops' hand-rolled fidelity parsers must be expressible as
declarations (plus their documented residue hooks), or the grammar is wrong.
"""

import argparse
from dataclasses import replace

import pytest

from painted import Block, Style
from painted.cli import (
    CliRunner,
    OutputMode,
    Tag,
    Zoom,
    add_cli_args,
    help_doc,
    parse_fidelity,
    parse_zoom,
    run_cli,
)
from painted.cli.help import framework_sections
from painted.core.doc import Defs, Section


def _parse(argv, *, tags=None, depth_aliases=None, budgets=True, add_args=None):
    """add_cli_args → parse_args → parse_fidelity, the function-altitude path."""
    parser = argparse.ArgumentParser()
    add_cli_args(
        parser,
        modes={OutputMode.STATIC},
        tags=tags,
        depth_aliases=depth_aliases,
        budgets=budgets,
    )
    if add_args is not None:
        add_args(parser)
    parsed = parser.parse_args(argv)
    zoom = parse_zoom(parsed)
    return parsed, parse_fidelity(parsed, zoom, tags=tags, depth_aliases=depth_aliases)


# =============================================================================
# Tag declaration
# =============================================================================


class TestTag:
    def test_frozen(self):
        tag = Tag("thinking", "Show model reasoning")
        with pytest.raises(AttributeError):
            tag.name = "other"  # type: ignore

    def test_defaults(self):
        tag = Tag("thinking", "Show model reasoning")
        assert tag.implied_at is None

    def test_top_level_export(self):
        from painted import Tag as TopLevelTag

        assert TopLevelTag is Tag


# =============================================================================
# Collision checks — declarations are promises, checked at construction
# =============================================================================


class TestCollisionChecks:
    def _build(self, *, tags=None, depth_aliases=None):
        parser = argparse.ArgumentParser()
        add_cli_args(parser, tags=tags, depth_aliases=depth_aliases)

    def test_tag_vs_framework_flag(self):
        with pytest.raises(ValueError, match="framework flag"):
            self._build(tags=[Tag("json", "x")])

    def test_alias_vs_framework_flag(self):
        with pytest.raises(ValueError, match="framework flag"):
            self._build(depth_aliases={"quiet": 0})

    def test_budget_names_reserved_even_without_budgets(self):
        """max-chars is reserved regardless of the budgets= setting, so a
        declaration that works in one configuration cannot break in another."""
        parser = argparse.ArgumentParser()
        with pytest.raises(ValueError, match="framework flag"):
            add_cli_args(parser, tags=[Tag("max-chars", "x")], budgets=False)

    def test_tag_vs_tag(self):
        with pytest.raises(ValueError, match="another declaration"):
            self._build(tags=[Tag("refs", "x"), Tag("refs", "y")])

    def test_tag_vs_alias(self):
        with pytest.raises(ValueError, match="another declaration"):
            self._build(tags=[Tag("brief", "x")], depth_aliases={"brief": 0})

    @pytest.mark.parametrize("bad", ["Thinking", "show_refs", "-refs", "refs-", "a b"])
    def test_malformed_names_rejected(self, bad):
        with pytest.raises(ValueError, match="kebab-case"):
            self._build(tags=[Tag(bad, "x")])

    def test_kebab_case_accepted(self):
        self._build(tags=[Tag("march-stats", "x")])


# =============================================================================
# Compilation laws
# =============================================================================


class TestTagCompilation:
    TAGS = [
        Tag("thinking", "Show model reasoning", implied_at=3),
        Tag("refs", "Show references"),
    ]

    def test_flag_sets_visible(self):
        _, fid = _parse(["--refs"], tags=self.TAGS)
        assert fid.shows("refs")
        assert not fid.shows("thinking")

    def test_default_is_empty(self):
        _, fid = _parse([], tags=self.TAGS)
        assert fid.visible == frozenset()

    def test_implied_at_resolves_from_verbose_depth(self):
        _, fid = _parse(["-vv"], tags=self.TAGS)
        assert fid.shows("thinking")
        assert not fid.shows("refs")  # no implied_at — never implied

    def test_implied_at_not_triggered_below_threshold(self):
        _, fid = _parse(["-v"], tags=self.TAGS)
        assert not fid.shows("thinking")

    def test_explicit_flag_at_low_depth(self):
        """The noun test: a named facet is reachable without dragging depth."""
        _, fid = _parse(["-q", "--thinking"], tags=self.TAGS)
        assert fid.depth == 0
        assert fid.shows("thinking")

    def test_implication_resolved_at_compile_time(self):
        """The spec stays dumb — visible is fully materialized, consumers
        never re-derive implications."""
        _, fid = _parse(["-vv"], tags=self.TAGS)
        assert "thinking" in fid.visible


class TestDepthAliasCompilation:
    ALIASES = {"brief": 0, "full": 3}

    def test_alias_sets_depth(self):
        _, fid = _parse(["--brief"], depth_aliases=self.ALIASES)
        assert fid.depth == 0
        _, fid = _parse(["--full"], depth_aliases=self.ALIASES)
        assert fid.depth == 3

    def test_alias_exclusive_with_verbose(self):
        with pytest.raises(SystemExit):
            _parse(["--full", "-v"], depth_aliases=self.ALIASES)

    def test_alias_exclusive_with_alias(self):
        with pytest.raises(SystemExit):
            _parse(["--full", "--brief"], depth_aliases=self.ALIASES)

    def test_alias_trips_implied_tags(self):
        """Pure spelling: --full is depth=3, which trips implied_at=3 tags
        exactly as -vv would."""
        tags = [Tag("thinking", "x", implied_at=3)]
        _, fid = _parse(["--full"], tags=tags, depth_aliases=self.ALIASES)
        assert fid.shows("thinking")


class TestBudgetsGate:
    def test_budgets_true_adds_flags(self):
        _, fid = _parse(["--max-chars", "50", "--max-lines", "10"], budgets=True)
        assert fid.chars == 50
        assert fid.lines == 10

    def test_budgets_false_omits_flags(self):
        with pytest.raises(SystemExit):
            _parse(["--max-chars", "50"], budgets=False)

    def test_budgets_false_yields_unlimited(self):
        _, fid = _parse([], budgets=False)
        assert fid.chars == 0
        assert fid.lines == 0


# =============================================================================
# Knob altitude — run_cli / CliRunner
# =============================================================================


class TestRunnerIntegration:
    TAGS = [Tag("stats", "Show internals", implied_at=3)]

    def _capture(self, argv, **kwargs):
        received = {}

        def render(ctx, data):
            received["fidelity"] = ctx.fidelity
            return Block.text(data, Style())

        result = run_cli(argv, render=render, fetch=lambda: "x", **kwargs)
        assert result == 0
        return received["fidelity"]

    def test_tag_flag_reaches_render(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        fid = self._capture(["--stats"], tags=self.TAGS)
        assert fid.shows("stats")

    def test_implied_tag_reaches_render(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        fid = self._capture(["-vv"], tags=self.TAGS)
        assert fid.shows("stats")

    def test_no_args_with_declarations_compiles(self, monkeypatch):
        """Declarations force the full parse path even for empty argv, so a
        default_zoom at the implication threshold still resolves the tag."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        fid = self._capture([], tags=self.TAGS, default_zoom=Zoom.FULL)
        assert fid.shows("stats")

    def test_build_fidelity_runs_after_compilation(self, monkeypatch):
        """The escape hatch sees the compiled spec — tags already in visible."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = {}

        def hook(_parsed, fid):
            seen["visible"] = fid.visible
            return replace(fid, visible=fid.visible | {"extra"})

        fid = self._capture(["--stats"], tags=self.TAGS, build_fidelity=hook)
        assert seen["visible"] == frozenset({"stats"})
        assert fid.visible == frozenset({"stats", "extra"})

    def test_depth_alias_zero_implies_static(self, monkeypatch):
        """An alias to depth 0 behaves like -q: AUTO collapses to STATIC."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        received = {}

        def render(ctx, data):
            received["mode"] = ctx.mode
            return Block.text(data, Style())

        run_cli(
            ["--brief"],
            render=render,
            fetch=lambda: "x",
            depth_aliases={"brief": 0},
        )
        assert received["mode"] == OutputMode.STATIC

    def test_collision_raises_before_dispatch(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.raises(ValueError, match="framework flag"):
            run_cli(
                [],
                render=lambda _ctx, _data: Block.text("x", Style()),
                fetch=lambda: "x",
                tags=[Tag("plain", "x")],
            )


# =============================================================================
# Help integration — a declaration buys flag + parse + help in one move
# =============================================================================


def _section_headings(nodes):
    return [n.heading for n in nodes if isinstance(n, Section)]


class TestHelpIntegration:
    def test_layers_section_when_tags_declared(self):
        sections = framework_sections(0, tags=[Tag("thinking", "Show reasoning")])
        assert "Layers" in _section_headings(sections)

    def test_no_layers_section_without_tags(self):
        sections = framework_sections(0)
        assert "Layers" not in _section_headings(sections)

    def test_layers_leads_and_never_steps_back(self):
        # Layers is app-declared vocabulary, not universal grammar: it renders
        # first among the groups and stays at MINIMAL even when the grammar
        # steps back behind command args (depth=1).
        sections = framework_sections(1, tags=[Tag("thinking", "Show reasoning")])
        headings = _section_headings(sections)
        assert headings[0] == "Layers"
        layers = next(n for n in sections if isinstance(n, Section) and n.heading == "Layers")
        zoom = next(n for n in sections if isinstance(n, Section) and n.heading == "Zoom")
        assert layers.min_depth == 0
        assert zoom.min_depth == 1

    def test_density_section_gated_on_budgets(self):
        assert "Density" in _section_headings(framework_sections(0, budgets=True))
        assert "Density" not in _section_headings(framework_sections(0, budgets=False))

    def test_alias_appears_in_zoom_group(self):
        sections = framework_sections(0, depth_aliases={"brief": 0})
        zoom = next(n for n in sections if isinstance(n, Section) and n.heading == "Zoom")
        terms = [d.term for defs in zoom.body if isinstance(defs, Defs) for d in defs.items]
        assert "--brief" in terms

    def test_help_doc_carries_declarations(self):
        runner = CliRunner(
            render=lambda _ctx, _data: Block.text("x", Style()),
            fetch=lambda: "ok",
            prog="test",
            tags=[Tag("thinking", "Show reasoning", implied_at=3)],
            depth_aliases={"brief": 0},
        )
        doc = help_doc(runner)
        headings = _section_headings(doc.body)
        assert "Layers" in headings

    def test_run_cli_help_renders_tag(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        result = run_cli(
            ["--help", "-v"],
            render=lambda _ctx, _data: Block.text("x", Style()),
            fetch=lambda: "ok",
            prog="myapp",
            tags=[Tag("thinking", "Show model reasoning")],
        )
        assert result == 0
        out = capsys.readouterr().out
        assert "--thinking" in out
        assert "Layers" in out


# =============================================================================
# Acceptance: siftd (§6 — the forcing-function spec)
# =============================================================================

# Declarations replacing siftd/cli/_common.py:add_fidelity_args + the depth
# half of fidelity_from_args. Ground truth extracted 2026-06-10 from
# _common.py:53-153.
SIFTD_TAGS = [
    Tag("thinking", "Show model reasoning", implied_at=3),
    Tag("tools", "Show tool calls and tool output", implied_at=3),
]
SIFTD_ALIASES = {"brief": 0, "full": 3}


def _siftd_add_args(parser):
    """siftd's app-specific --chars flag — acknowledged residue, stays on the
    add_args hook (their flag predates and differs from --max-chars)."""
    parser.add_argument("--chars", type=int, default=None)


def _siftd_residue(parsed, fid):
    """siftd's depth-derived chars defaults and 'text' baseline — the
    build_fidelity residue hook (_common.py:67,74-80). full ⇒ 0 beats an
    explicit --chars; explicit beats brief's 80."""
    if getattr(parsed, "full", False):
        chars = 0
    elif parsed.chars is not None:
        chars = parsed.chars
    elif getattr(parsed, "brief", False):
        chars = 80
    else:
        chars = 0
    return replace(fid, visible=fid.visible | {"text"}, chars=chars)


# (argv) → (depth, visible, chars). Long-form flags only: siftd's -b/-F short
# spellings are not expressible by depth_aliases (residue, noted in §6 review);
# --full --brief together is stricter here (argparse exclusive group) where
# siftd silently let --full win. siftd's --tools takes an optional FILTER
# value (nargs="?") — the boolean presence is the tag; the filter string is
# per-facet residue that stays on their namespace (§6, valued tags §7e).
SIFTD_TRUTH_TABLE = [
    ([], 1, {"text"}, 0),
    (["--brief"], 0, {"text"}, 80),
    (["--full"], 3, {"text", "thinking", "tools"}, 0),
    (["--thinking"], 1, {"text", "thinking"}, 0),
    (["--tools"], 1, {"text", "tools"}, 0),
    (["--thinking", "--tools"], 1, {"text", "thinking", "tools"}, 0),
    (["--brief", "--thinking"], 0, {"text", "thinking"}, 80),
    (["--brief", "--tools"], 0, {"text", "tools"}, 80),
    (["--brief", "--thinking", "--tools"], 0, {"text", "thinking", "tools"}, 80),
    (["--full", "--thinking"], 3, {"text", "thinking", "tools"}, 0),
    (["--chars", "50"], 1, {"text"}, 50),
    (["--chars", "0"], 1, {"text"}, 0),
    (["--brief", "--chars", "100"], 0, {"text"}, 100),
    (["--full", "--chars", "50"], 3, {"text", "thinking", "tools"}, 0),
]


class TestSiftdAcceptance:
    """siftd's fidelity_from_args becomes deletable: declarations + the
    documented residue hook reproduce its parser's output exactly."""

    @pytest.mark.parametrize("argv,depth,visible,chars", SIFTD_TRUTH_TABLE)
    def test_compiled_fidelity_matches_siftd_parser(self, argv, depth, visible, chars):
        parsed, fid = _parse(
            argv,
            tags=SIFTD_TAGS,
            depth_aliases=SIFTD_ALIASES,
            budgets=False,  # siftd has no --max-chars/--max-lines
            add_args=_siftd_add_args,
        )
        fid = _siftd_residue(parsed, fid)
        assert fid.depth == depth
        assert fid.visible == frozenset(visible)
        assert fid.chars == chars
        assert fid.lines == 0  # siftd never sets lines


# =============================================================================
# Acceptance: loops (§6)
# =============================================================================

# Declarations replacing loops/cli/fidelity.py:fidelity_from_args. Ground
# truth extracted 2026-06-10 from fidelity.py:33-95 + views/fold.py:96-147.
# The int-valued --refs N stays loops-side residue (§7e — tags are boolean
# layers); the grammar expresses the boolean presence.
LOOPS_TAGS = [
    Tag("facts", "Show source facts"),
    Tag("refs", "Show reference edges"),
]

LOOPS_TRUTH_TABLE = [
    ([], 1, set(), 0, 0),
    (["-q"], 0, set(), 0, 0),
    (["-v"], 2, set(), 0, 0),
    (["-vv"], 3, set(), 0, 0),
    (["-vvv"], 3, set(), 0, 0),  # clamped
    (["--facts"], 1, {"facts"}, 0, 0),
    (["--refs"], 1, {"refs"}, 0, 0),
    (["--facts", "--refs"], 1, {"facts", "refs"}, 0, 0),
    (["-v", "--facts"], 2, {"facts"}, 0, 0),
    (["-q", "--facts"], 0, {"facts"}, 0, 0),
    (["--max-chars", "100"], 1, set(), 100, 0),
    (["--max-lines", "20"], 1, set(), 0, 20),
    (
        ["-v", "--facts", "--refs", "--max-chars", "80", "--max-lines", "10"],
        2,
        {"facts", "refs"},
        80,
        10,
    ),
]


class TestLoopsAcceptance:
    """loops' cli/fidelity.py becomes deletable: pure declarations, no
    residue hook needed for the fidelity itself."""

    @pytest.mark.parametrize("argv,depth,visible,chars,lines", LOOPS_TRUTH_TABLE)
    def test_compiled_fidelity_matches_loops_parser(self, argv, depth, visible, chars, lines):
        _, fid = _parse(argv, tags=LOOPS_TAGS, budgets=True)
        assert fid.depth == depth
        assert fid.visible == frozenset(visible)
        assert fid.chars == chars
        assert fid.lines == lines


# =============================================================================
# Depth alias values — declarations are promises, including the depth
# =============================================================================


class TestDepthAliasValues:
    def test_negative_alias_rejected_at_construction(self):
        with pytest.raises(ValueError, match="non-negative"):
            _parse([], depth_aliases={"silent": -1})

    def test_alias_above_enum_compiles_open_and_clamps_at_porthole(self):
        """depth is an open int in the spec; the rung-1 porthole clamps."""
        from painted.cli import CliContext

        _, fid = _parse(["--forensic"], depth_aliases={"forensic": 5})
        assert fid.depth == 5
        ctx = CliContext(
            fidelity=fid, mode=OutputMode.STATIC, use_ansi=False, is_tty=False, width=80, height=24
        )
        assert ctx.zoom == Zoom.FULL

    def test_porthole_clamps_below_too(self):
        """A build_fidelity hook can hand back any int — the porthole never
        raises on it."""
        from painted.cli import CliContext
        from painted.core.fidelity import Fidelity

        ctx = CliContext(
            fidelity=Fidelity(depth=-2),
            mode=OutputMode.STATIC,
            use_ansi=False,
            is_tty=False,
            width=80,
            height=24,
        )
        assert ctx.zoom == Zoom.MINIMAL


# =============================================================================
# add_args dest collisions — the escape hatch can't shadow a declaration
# =============================================================================


class TestAddArgsDestCollision:
    def _run(self, argv, **kwargs):
        return run_cli(
            argv, render=lambda _ctx, _data: Block.text("x", Style()), fetch=lambda: "x", **kwargs
        )

    def test_positional_on_tag_dest_raises(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.raises(ValueError, match="collides with a declared tag"):
            self._run(
                ["data.csv"],
                tags=[Tag("stats", "x")],
                add_args=lambda p: p.add_argument("stats"),
            )

    def test_custom_dest_on_alias_raises(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.raises(ValueError, match="collides with a declared tag"):
            self._run(
                [],
                depth_aliases={"brief": 0},
                add_args=lambda p: p.add_argument("--terse", dest="brief"),
            )


# =============================================================================
# The help path obeys the same laws as the parse path
# =============================================================================


class TestHelpPathLaws:
    def test_collision_raises_on_help_path(self, monkeypatch):
        """A broken declaration must raise on -h too, not render the
        contradiction it would refuse to parse."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        with pytest.raises(ValueError, match="framework flag"):
            run_cli(
                ["-h"],
                render=lambda _ctx, _data: Block.text("x", Style()),
                fetch=lambda: "x",
                tags=[Tag("json", "x")],
            )

    def test_help_zoom_honors_depth_alias(self):
        """An alias is pure spelling on the help path too: -h --full ≡ -h -vv."""
        from painted.cli.help import scan_help_args

        aliases = {"brief": 0, "full": 3}
        assert scan_help_args(["-h", "--full"], depth_aliases=aliases)[0] == Zoom.FULL
        assert scan_help_args(["-h", "-vv"], depth_aliases=aliases)[0] == Zoom.FULL
        assert scan_help_args(["-h", "--brief"], depth_aliases=aliases)[0] == Zoom.MINIMAL
        assert scan_help_args(["-h"], depth_aliases=aliases)[0] == Zoom.SUMMARY

    def test_help_zoom_alias_end_to_end(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        def _help(argv):
            run_cli(
                argv,
                render=lambda _ctx, _data: Block.text("x", Style()),
                fetch=lambda: "x",
                depth_aliases={"full": 3},
            )
            return capsys.readouterr().out

        assert _help(["-h", "--full", "--plain"]) == _help(["-h", "-vv", "--plain"])

    def test_interactive_flag_in_help_for_surface_delivery(self, capsys, monkeypatch):
        """help_doc mirrors _get_parser: surface delivery makes -i exist, so
        it must appear in help (the help surface matches the flag surface)."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)

        async def stream():
            yield "x"

        run_cli(
            ["-h", "-v", "--plain"],
            render=lambda _ctx, _data: Block.text("x", Style()),
            fetch=lambda: "x",
            fetch_stream=stream,
            live_delivery="surface",
        )
        assert "--interactive" in capsys.readouterr().out


# =============================================================================
# Runner edge paths
# =============================================================================


class TestRunnerEdgePaths:
    def test_json_short_circuit_accepts_tag_flag(self, capsys, monkeypatch):
        """--json with a declared flag parses cleanly and exports data."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        result = run_cli(
            ["--json", "--stats"],
            render=lambda _ctx, _data: Block.text("x", Style()),
            fetch=lambda: {"ok": True},
            tags=[Tag("stats", "x")],
        )
        assert result == 0
        assert '"ok": true' in capsys.readouterr().out

    def test_parser_cache_reuse_across_runs(self, monkeypatch):
        """A cached parser still compiles declarations correctly on rerun."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        seen = []

        runner = CliRunner(
            render=lambda ctx, data: seen.append(ctx.fidelity) or Block.text("x", Style()),
            fetch=lambda: "x",
            tags=[Tag("stats", "x")],
        )
        assert runner.run(["--stats"]) == 0
        assert runner.run([]) == 0
        assert seen[0].shows("stats")
        assert not seen[1].shows("stats")


# =============================================================================
# Demo facet honesty — the declared capability changes output
# =============================================================================


def _load_demo(name):
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent.parent / "demos" / "patterns" / name
    spec = importlib.util.spec_from_file_location(f"_facet_{name[:-3]}", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestFidelityDemoFacet:
    def test_timestamp_facet_changes_output(self):
        """The honesty rule for the harness teaching demo: --timestamp adds
        the stamp at any depth; without the facet no renderer emits it."""
        from tests.helpers import block_to_text, static_ctx

        fid_demo = _load_demo("fidelity.py")
        data = replace(fid_demo.SAMPLE_DISK, timestamp="2026-06-10T12:00:00")

        for zoom in Zoom:
            base = block_to_text(fid_demo._render(static_ctx(zoom), data))
            faceted = block_to_text(
                fid_demo._render(static_ctx(zoom, visible=("timestamp",)), data)
            )
            assert "2026-06-10T12:00:00" not in base, zoom
            assert "2026-06-10T12:00:00" in faceted, zoom

    def test_timestamp_implied_at_detailed(self):
        from painted.cli import implied_visible

        fid_demo = _load_demo("fidelity.py")
        assert implied_visible(fid_demo._TAGS, int(Zoom.DETAILED)) == frozenset({"timestamp"})
        assert implied_visible(fid_demo._TAGS, int(Zoom.SUMMARY)) == frozenset()


# =============================================================================
# Docs CLI migration — page tags become declarations, --show is gone (§7d)
# =============================================================================


class TestDocsCliMigration:
    def test_pages_with_tagged_nodes_get_flags(self):
        """--rationale exists exactly on pages that have rationale nodes."""
        from painted._doc_pages import DOCS
        from painted._docs_cli import _collect_tags

        tag_names = {
            name: {t.name for t in _collect_tags(entry.build())} for name, entry in DOCS.items()
        }
        assert any("rationale" in names for names in tag_names.values())

    def test_tag_flag_changes_output(self, capsys, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from painted._doc_pages import DOCS
        from painted._docs_cli import _collect_tags, run_doc

        name = next(
            n
            for n, e in DOCS.items()
            if any(t.name == "rationale" for t in _collect_tags(e.build()))
        )
        assert run_doc(name, ["--plain"]) == 0
        base = capsys.readouterr().out
        assert run_doc(name, ["--rationale", "--plain"]) == 0
        faceted = capsys.readouterr().out
        assert base != faceted

    def test_show_flag_is_retired(self, monkeypatch):
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from painted._doc_pages import DOCS
        from painted._docs_cli import run_doc

        name = next(iter(DOCS))
        with pytest.raises(SystemExit):
            run_doc(name, ["--show", "rationale"])


# =============================================================================
# AppCommand — declarations surface in intercepted subcommand help
# =============================================================================


class TestAppCommandTags:
    def test_declared_tags_render_in_intercepted_help(self, capsys, monkeypatch):
        """A command with help_args + tags shows its Layers group on the
        intercepted -h path — the same group the handler's run_cli renders."""
        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        from painted.cli import AppCommand, HelpArg, run_app

        cmd = AppCommand(
            "march",
            "Render the march",
            handler=lambda argv: 0,
            help_args=[HelpArg("--frame", "pose to render")],
            tags=[Tag("stats", "Show march internals", implied_at=3)],
        )
        assert run_app(["march", "-h", "-v"], [cmd], prog="myapp") == 0
        out = capsys.readouterr().out
        assert "Layers" in out
        assert "--stats" in out

    def test_declarations_validated_at_construction(self):
        from painted.cli import AppCommand

        with pytest.raises(ValueError, match="framework flag"):
            AppCommand("x", "y", handler=lambda argv: 0, tags=[Tag("json", "z")])
