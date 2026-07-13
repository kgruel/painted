"""Tests for the fidelity module: Zoom, OutputMode, Format, help-doc construction.

End-to-end run_cli dispatch lives in tests/integration/test_run_cli_dispatch.py."""

import argparse

import pytest

from painted import Block, Style
from painted.core.fidelity import Fidelity
from painted.cli import (
    CliContext,
    CliRunner,
    Format,
    HelpArg,
    OutputMode,
    Zoom,
    help_doc,
    add_cli_args,
    parse_fidelity,
    parse_format,
    parse_mode,
    parse_zoom,
    resolve_mode,
)
from painted.cli.help import _add_args_defs, _arg_def
from painted.core.doc import Defs, Section, doc_lens
from tests.helpers import block_to_text

# =============================================================================
# Zoom Tests
# =============================================================================


class TestZoom:
    """Tests for Zoom enum."""

    def test_ordering(self):
        """Zoom levels are ordered MINIMAL < SUMMARY < DETAILED < FULL."""
        assert Zoom.MINIMAL < Zoom.SUMMARY < Zoom.DETAILED < Zoom.FULL

    def test_values(self):
        """Zoom levels have correct integer values."""
        assert Zoom.MINIMAL == 0
        assert Zoom.SUMMARY == 1
        assert Zoom.DETAILED == 2
        assert Zoom.FULL == 3


class TestParseZoom:
    """Tests for parse_zoom function."""

    def test_quiet_flag(self):
        """--quiet/-q gives MINIMAL."""
        args = argparse.Namespace(quiet=True, verbose=0)
        assert parse_zoom(args) == Zoom.MINIMAL

    def test_default(self):
        """No flags gives SUMMARY (default)."""
        args = argparse.Namespace(quiet=False, verbose=0)
        assert parse_zoom(args) == Zoom.SUMMARY

    def test_single_verbose(self):
        """-v gives DETAILED."""
        args = argparse.Namespace(quiet=False, verbose=1)
        assert parse_zoom(args) == Zoom.DETAILED

    def test_double_verbose(self):
        """-vv gives FULL."""
        args = argparse.Namespace(quiet=False, verbose=2)
        assert parse_zoom(args) == Zoom.FULL

    def test_triple_verbose_caps_at_full(self):
        """-vvv still gives FULL (capped)."""
        args = argparse.Namespace(quiet=False, verbose=3)
        assert parse_zoom(args) == Zoom.FULL

    def test_custom_default(self):
        """Custom default zoom is respected."""
        args = argparse.Namespace(quiet=False, verbose=0)
        assert parse_zoom(args, default=Zoom.DETAILED) == Zoom.DETAILED


# =============================================================================
# OutputMode Tests
# =============================================================================


class TestParseMode:
    """Tests for parse_mode function."""

    def test_interactive_flag(self):
        """-i/--interactive gives INTERACTIVE."""
        args = argparse.Namespace(interactive=True, static=False, live=False)
        assert parse_mode(args) == OutputMode.INTERACTIVE

    def test_static_flag(self):
        """--static gives STATIC."""
        args = argparse.Namespace(interactive=False, static=True, live=False)
        assert parse_mode(args) == OutputMode.STATIC

    def test_live_flag(self):
        """--live gives LIVE."""
        args = argparse.Namespace(interactive=False, static=False, live=True)
        assert parse_mode(args) == OutputMode.LIVE

    def test_no_flag_gives_auto(self):
        """No flags gives AUTO."""
        args = argparse.Namespace(interactive=False, static=False, live=False)
        assert parse_mode(args) == OutputMode.AUTO


class TestResolveMode:
    """Tests for resolve_mode function."""

    def test_explicit_mode_preserved(self):
        """Non-AUTO modes are returned unchanged."""
        assert resolve_mode(OutputMode.STATIC, is_tty=True, is_pipe=False) == OutputMode.STATIC
        assert resolve_mode(OutputMode.LIVE, is_tty=False, is_pipe=True) == OutputMode.LIVE
        assert (
            resolve_mode(OutputMode.INTERACTIVE, is_tty=False, is_pipe=True)
            == OutputMode.INTERACTIVE
        )

    def test_auto_tty_gives_live(self):
        """AUTO resolves to LIVE for TTY (default)."""
        assert resolve_mode(OutputMode.AUTO, is_tty=True, is_pipe=False) == OutputMode.LIVE

    def test_auto_pipe_gives_static(self):
        """AUTO resolves to STATIC for pipe."""
        assert resolve_mode(OutputMode.AUTO, is_tty=False, is_pipe=True) == OutputMode.STATIC

    def test_auto_tty_with_default_mode_static(self):
        """AUTO on TTY respects default_mode override."""
        assert (
            resolve_mode(
                OutputMode.AUTO, is_tty=True, is_pipe=False, default_mode=OutputMode.STATIC
            )
            == OutputMode.STATIC
        )

    def test_auto_pipe_ignores_default_mode(self):
        """Pipe always gets STATIC regardless of default_mode."""
        assert (
            resolve_mode(OutputMode.AUTO, is_tty=False, is_pipe=True, default_mode=OutputMode.LIVE)
            == OutputMode.STATIC
        )


# =============================================================================
# Format Tests
# =============================================================================


class TestParseFormat:
    """Tests for parse_format function."""

    def test_json_flag(self):
        """--json gives JSON."""
        args = argparse.Namespace(json=True, plain=False)
        assert parse_format(args) == Format.JSON

    def test_plain_flag(self):
        """--plain gives PLAIN."""
        args = argparse.Namespace(json=False, plain=True)
        assert parse_format(args) == Format.PLAIN

    def test_no_flag_gives_auto(self):
        """No flags gives AUTO."""
        args = argparse.Namespace(json=False, plain=False)
        assert parse_format(args) == Format.AUTO


class TestParseFidelity:
    """Tests for parse_fidelity function."""

    def test_no_flags_gives_zero_limits(self):
        """No density flags gives Fidelity with chars=0, lines=0 (unlimited)."""
        args = argparse.Namespace(max_chars=None, max_lines=None)
        fid = parse_fidelity(args)
        assert fid.chars == 0
        assert fid.lines == 0

    def test_max_chars_only(self):
        """--max-chars without --max-lines gives Fidelity with chars set, lines=0."""
        args = argparse.Namespace(max_chars=50, max_lines=None)
        fid = parse_fidelity(args)
        assert fid.chars == 50
        assert fid.lines == 0

    def test_max_lines_only(self):
        """--max-lines without --max-chars gives Fidelity with lines set, chars=0."""
        args = argparse.Namespace(max_chars=None, max_lines=10)
        fid = parse_fidelity(args)
        assert fid.lines == 10
        assert fid.chars == 0

    def test_both_flags(self):
        """Both --max-chars and --max-lines produces Fidelity with both."""
        args = argparse.Namespace(max_chars=100, max_lines=5)
        fid = parse_fidelity(args)
        assert fid.chars == 100
        assert fid.lines == 5

    def test_missing_attrs_gives_zero_limits(self):
        """Namespace without density attrs gives Fidelity with zeros."""
        args = argparse.Namespace()
        fid = parse_fidelity(args)
        assert fid.chars == 0
        assert fid.lines == 0

    def test_depth_from_zoom(self):
        """parse_fidelity picks up depth from the zoom argument."""
        args = argparse.Namespace(max_chars=None, max_lines=None)
        fid = parse_fidelity(args, Zoom.DETAILED)
        assert fid.depth == int(Zoom.DETAILED)


class TestUseAnsiResolution:
    """Tests for use_ansi resolution via detect_context.

    Format dissolved: resolve_format removed, use_ansi derived from
    force_plain + TTY detection + mode in detect_context.
    """

    def test_force_plain_gives_no_ansi(self, monkeypatch):
        """force_plain=True always produces use_ansi=False."""
        from painted.cli import detect_context

        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        ctx = detect_context(Fidelity(depth=int(Zoom.SUMMARY)), OutputMode.STATIC, force_plain=True)
        assert ctx.use_ansi is False

    def test_tty_gives_ansi(self, monkeypatch):
        """TTY without force_plain produces use_ansi=True."""
        from painted.cli import detect_context

        monkeypatch.setattr("sys.stdout.isatty", lambda: True)
        ctx = detect_context(Fidelity(depth=int(Zoom.SUMMARY)), OutputMode.STATIC)
        assert ctx.use_ansi is True

    def test_pipe_gives_no_ansi(self, monkeypatch):
        """Pipe without force_plain produces use_ansi=False."""
        from painted.cli import detect_context

        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        ctx = detect_context(Fidelity(depth=int(Zoom.SUMMARY)), OutputMode.STATIC)
        assert ctx.use_ansi is False

    def test_interactive_always_ansi(self, monkeypatch):
        """INTERACTIVE mode forces use_ansi=True even on pipe."""
        from painted.cli import detect_context

        monkeypatch.setattr("sys.stdout.isatty", lambda: False)
        ctx = detect_context(Fidelity(depth=int(Zoom.SUMMARY)), OutputMode.INTERACTIVE)
        assert ctx.use_ansi is True


# =============================================================================
# Argument Parsing Integration
# =============================================================================


class TestAddCliArgs:
    """Tests for add_cli_args function."""

    def test_zoom_args(self):
        """Zoom arguments are added correctly."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser)

        # -q
        args = parser.parse_args(["-q"])
        assert args.quiet is True
        assert args.verbose == 0

        # -v
        args = parser.parse_args(["-v"])
        assert args.quiet is False
        assert args.verbose == 1

        # -vv
        args = parser.parse_args(["-v", "-v"])
        assert args.verbose == 2

    def test_mode_args(self):
        """Mode arguments are added correctly."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser)

        args = parser.parse_args(["-i"])
        assert args.interactive is True

        args = parser.parse_args(["--static"])
        assert args.static is True

        args = parser.parse_args(["--live"])
        assert args.live is True

    def test_mode_args_filtered(self):
        """Passing modes={STATIC, LIVE} omits -i."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser, modes={OutputMode.STATIC, OutputMode.LIVE})

        # --static and --live available
        args = parser.parse_args(["--static"])
        assert args.static is True

        args = parser.parse_args(["--live"])
        assert args.live is True

        # -i not recognized
        with pytest.raises(SystemExit):
            parser.parse_args(["-i"])

    def test_mode_args_static_only(self):
        """Mode group omitted entirely when only STATIC."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser, modes={OutputMode.STATIC})

        # No mode flags at all
        with pytest.raises(SystemExit):
            parser.parse_args(["-i"])
        with pytest.raises(SystemExit):
            parser.parse_args(["--live"])
        with pytest.raises(SystemExit):
            parser.parse_args(["--static"])

    def test_format_args(self):
        """Format arguments are added correctly."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser)

        args = parser.parse_args(["--json"])
        assert args.json is True

        args = parser.parse_args(["--plain"])
        assert args.plain is True

    def test_density_args(self):
        """Density arguments are added when budgets are declared."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser, budgets=True)

        args = parser.parse_args(["--max-chars", "50"])
        assert args.max_chars == 50
        assert args.max_lines is None

        args = parser.parse_args(["--max-lines", "10"])
        assert args.max_lines == 10
        assert args.max_chars is None

        args = parser.parse_args(["--max-chars", "100", "--max-lines", "5"])
        assert args.max_chars == 100
        assert args.max_lines == 5

    def test_density_args_defaults(self):
        """Density arguments default to None."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser, budgets=True)

        args = parser.parse_args([])
        assert args.max_chars is None
        assert args.max_lines is None

    def test_density_args_absent_by_default(self):
        """The honesty rule: undeclared budgets means no --max-chars/--max-lines."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser)

        with pytest.raises(SystemExit):
            parser.parse_args(["--max-chars", "50"])

    def test_zoom_mutual_exclusion(self):
        """Cannot combine -q and -v."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser)

        with pytest.raises(SystemExit):
            parser.parse_args(["-q", "-v"])

    def test_mode_mutual_exclusion(self):
        """Cannot combine -i, --static, --live."""
        parser = argparse.ArgumentParser()
        add_cli_args(parser)

        with pytest.raises(SystemExit):
            parser.parse_args(["-i", "--static"])


# =============================================================================
# CliContext Tests
# =============================================================================


class TestCliContext:
    """Tests for CliContext dataclass."""

    def test_frozen(self):
        """CliContext is immutable (zoom property has no setter)."""
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=24,
        )
        with pytest.raises(AttributeError):
            ctx.zoom = Zoom.FULL  # type: ignore

    def test_zoom_property_returns_correct_level(self):
        """ctx.zoom is a backward-compat property derived from fidelity.depth."""
        ctx = CliContext(
            fidelity=Fidelity(depth=int(Zoom.SUMMARY)),
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=24,
        )
        assert ctx.zoom == Zoom.SUMMARY

    def test_fidelity_is_primary_field(self):
        """CliContext.fidelity is the canonical field, always set."""
        fid = Fidelity(depth=1, chars=50, lines=10)
        ctx = CliContext(
            fidelity=fid,
            mode=OutputMode.STATIC,
            use_ansi=True,
            is_tty=True,
            width=80,
            height=24,
        )
        assert ctx.fidelity is fid
        assert ctx.fidelity.chars == 50
        assert ctx.fidelity.lines == 10


# =============================================================================
# HelpArg and help augmentation tests
# =============================================================================


class TestHelpArg:
    """Tests for HelpArg dataclass."""

    def test_frozen(self):
        arg = HelpArg(name="--since", description="Time range")
        with pytest.raises(AttributeError):
            arg.name = "--other"  # type: ignore

    def test_defaults(self):
        arg = HelpArg(name="vertex")
        assert arg.description == ""
        assert arg.default is None
        assert arg.positional is False


class TestArgToDef:
    """HelpArg → Def keeps the term intact (the lossy help_args_to_flags is gone)."""

    def test_positional_arg(self):
        d = _arg_def(HelpArg("vertex", "Vertex name", positional=True))
        assert d.term == "vertex"
        assert d.summary == "Vertex name"

    def test_optional_arg(self):
        d = _arg_def(HelpArg("--since", "Time range"))
        assert d.term == "--since"
        assert d.summary == "Time range"

    def test_default_appended(self):
        d = _arg_def(HelpArg("--since", "Time range", default="7d"))
        assert "(default: 7d)" in d.summary

    def test_default_only_no_description(self):
        d = _arg_def(HelpArg("--since", default="7d"))
        assert d.summary == "(default: 7d)"


class TestAddArgsDefs:
    """add_args introspection → Defs, keeping the full term (both aliases)."""

    def test_extracts_positional(self):
        def add_args(parser):
            parser.add_argument("name", help="The name")

        defs = _add_args_defs(add_args)
        assert len(defs) == 1
        assert defs[0].term == "name"
        assert defs[0].summary == "The name"

    def test_keeps_both_aliases(self):
        """The old bridge dropped one alias; the term now carries -k, --kind."""

        def add_args(parser):
            parser.add_argument("-k", "--kind", help="Filter by kind")

        defs = _add_args_defs(add_args)
        assert len(defs) == 1
        assert "-k" in defs[0].term
        assert "--kind" in defs[0].term
        assert defs[0].summary == "Filter by kind"

    def test_skips_suppressed(self):
        def add_args(parser):
            parser.add_argument("--internal", help=argparse.SUPPRESS)
            parser.add_argument("--visible", help="Shown")

        defs = _add_args_defs(add_args)
        assert len(defs) == 1
        assert defs[0].term == "--visible"


def _sections(doc):
    return [n for n in doc.body if isinstance(n, Section)]


def _first_defs(doc):
    return next(n for n in doc.body if isinstance(n, Defs))


class TestHelpDoc:
    """help_doc(runner) builds the help document — the dissolution of HelpData."""

    def test_no_command_args_framework_leads(self):
        """Without command args, the framework groups are the primary content
        (min_depth 0) so they expand at the default help view."""
        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "ok",
            prog="test",
        )
        doc = help_doc(runner)
        assert doc.title == "test"
        for section in _sections(doc):
            assert section.min_depth == Zoom.MINIMAL

    def test_command_args_subordinate_framework(self):
        """With command args, those lead (a top-level Defs) and framework groups
        step back to min_depth=SUMMARY (the terse default line)."""
        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "ok",
            prog="test",
            help_args=[
                HelpArg("vertex", "Vertex name", positional=True),
                HelpArg("--since", "Time range", default="7d"),
            ],
        )
        doc = help_doc(runner)

        cmd_defs = _first_defs(doc)
        assert [d.term for d in cmd_defs.items] == ["vertex", "--since"]
        assert cmd_defs.min_depth == Zoom.MINIMAL  # always expanded

        for section in _sections(doc):
            assert section.min_depth == Zoom.SUMMARY

    def test_add_args_become_command_defs(self):
        def add_args(parser):
            parser.add_argument("file", help="Input file")
            parser.add_argument("--format", help="Output format")

        runner = CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "ok",
            prog="test",
            add_args=add_args,
        )
        doc = help_doc(runner)
        cmd_defs = _first_defs(doc)
        assert len(cmd_defs.items) == 2
        for section in _sections(doc):
            assert section.min_depth == Zoom.SUMMARY


class TestHelpDocRendering:
    """The four help tiers fall out of the doc-IR disclosure tier, projected
    through doc_lens — no bespoke help renderer."""

    def _runner(self):
        return CliRunner(
            renderer=lambda data, fidelity, width: Block.text("x", Style()),
            fetch=lambda: "ok",
            prog="myapp",
            description="A test app",
            help_args=[HelpArg("vertex", "Vertex name", positional=True)],
        )

    def _text(self, depth):
        block = doc_lens(help_doc(self._runner()), fidelity=Fidelity(depth=depth), width=80)
        return block_to_text(block)

    def test_default_framework_compact_command_expanded(self):
        """At the default view: command args expanded, framework groups terse
        (heading + names line, no per-flag summaries)."""
        text = self._text(Zoom.SUMMARY)
        # Command arg expanded.
        assert "vertex" in text and "Vertex name" in text
        # Framework group heading present, but its flags are names-only.
        assert "Zoom" in text
        assert "-q, --quiet" in text
        assert "Minimal output" not in text  # summary withheld at the compact tier

    def test_verbose_expands_framework(self):
        text = self._text(Zoom.DETAILED)
        assert "Zoom (what to show)" in text  # hint revealed at tier 1
        assert "Minimal output" in text  # flag summaries now shown

    def test_full_reveals_detail(self):
        text = self._text(Zoom.FULL)
        assert "Also implies --static" in text  # flag detail at tier 2
        assert "Controls how much detail" in text  # group detail prose at tier 2
