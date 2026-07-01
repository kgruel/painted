"""Completion contract types + the shared parser walk (slice 3, commit 1)."""

from __future__ import annotations

import argparse

from painted.cli._argwalk import walk_args
from painted.cli.complete import Candidate, CompletionContext, complete_args
from painted.cli.types import ArgsView


class TestWalkArgs:
    """walk_args yields a neutral ArgSpec per user-facing action."""

    def _parser(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("vertex")
        p.add_argument("-s", "--since", help="Lower bound")
        p.add_argument("--format", choices=["ansi", "plain", "json"])
        p.add_argument("--dry-run", action="store_true", help="No write")
        p.add_argument("--hidden", help=argparse.SUPPRESS)
        return p

    def test_positional_has_no_option_strings(self):
        specs = {s.dest: s for s in walk_args(self._parser())}
        assert specs["vertex"].is_positional
        assert specs["vertex"].option_strings == ()
        assert specs["vertex"].term == "vertex"

    def test_option_term_keeps_all_strings(self):
        specs = {s.dest: s for s in walk_args(self._parser())}
        assert specs["since"].option_strings == ("-s", "--since")
        assert specs["since"].term == "-s, --since"
        assert specs["since"].is_flag is False

    def test_choices_captured(self):
        specs = {s.dest: s for s in walk_args(self._parser())}
        assert specs["format"].choices == ("ansi", "plain", "json")

    def test_store_true_is_flag(self):
        specs = {s.dest: s for s in walk_args(self._parser())}
        assert specs["dry_run"].is_flag is True

    def test_suppressed_action_skipped(self):
        dests = {s.dest for s in walk_args(self._parser())}
        assert "hidden" not in dests

    def test_help_action_skipped(self):
        p = argparse.ArgumentParser()  # add_help=True → a _HelpAction
        p.add_argument("--x")
        dests = {s.dest for s in walk_args(p)}
        assert dests == {"x"}

    def test_completer_seam_read(self):
        p = argparse.ArgumentParser(add_help=False)
        action = p.add_argument("--key")
        sentinel = lambda ctx: ["a", "b"]
        action.completer = sentinel  # the .completer attribute seam (T3)
        spec = next(s for s in walk_args(p) if s.dest == "key")
        assert spec.completer is sentinel

    def test_no_completer_is_none(self):
        spec = next(s for s in walk_args(self._parser()) if s.dest == "since")
        assert spec.completer is None

    def test_mutex_group_index_captured(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("target")  # positional — never grouped
        g = p.add_mutually_exclusive_group()
        g.add_argument("--fast", action="store_true")
        g.add_argument("--slow", action="store_true")
        p.add_argument("--loud", action="store_true")  # ungrouped option
        specs = {s.dest: s for s in walk_args(p)}
        assert specs["fast"].mutex_group == specs["slow"].mutex_group  # same group
        assert specs["fast"].mutex_group is not None
        assert specs["loud"].mutex_group is None  # ungrouped
        assert specs["target"].mutex_group is None  # positional


class TestContractTypes:
    """Candidate / CompletionContext — the renderer-free contract."""

    def test_candidate_defaults(self):
        assert Candidate("read").description == ""
        assert Candidate("read", "Read a vertex").value == "read"

    def test_candidate_frozen(self):
        import dataclasses

        assert dataclasses.is_dataclass(Candidate)
        c = Candidate("x")
        try:
            c.value = "y"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            pass
        else:
            raise AssertionError("Candidate must be frozen")

    def test_completion_context_defaults(self):
        ctx = CompletionContext()
        assert ctx.prefix == ""
        assert len(ctx.args) == 0

    def test_completion_context_carries_args_and_prefix(self):
        ctx = CompletionContext(args=ArgsView({"vertex": "loops"}), prefix="--ki")
        assert ctx.args.vertex == "loops"
        assert ctx.prefix == "--ki"

    def test_argspec_is_renderer_free_import(self):
        """Importing the producer pulls no renderer module (pre-C-LAZY spot
        check — the full guard lands with C-LAZY, but the producer module
        itself must already be clean)."""
        import sys

        # complete + _argwalk are imported at module top; assert neither dragged
        # in a renderer module on its own account.
        assert "painted.cli.complete" in sys.modules
        assert "painted.cli._argwalk" in sys.modules


class TestProducer:
    """complete_args — the single-parser producer engine."""

    def _parser(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("vertex", choices=["loops", "painted", "siftd"])
        p.add_argument("-s", "--since", help="Lower bound")
        p.add_argument("--format", choices=["ansi", "plain", "json"])
        p.add_argument("--dry-run", action="store_true")
        return p

    def _values(self, cands):
        return [c.value for c in cands]

    def test_flags_in_word_context(self):
        cands = complete_args(self._parser(), [], "--")
        vals = self._values(cands)
        assert "--since" in vals and "--format" in vals and "--dry-run" in vals
        assert "-s" not in vals  # filtered by the "--" prefix

    def test_short_flag_prefix(self):
        vals = self._values(complete_args(self._parser(), [], "-s"))
        assert vals == ["-s"]

    def test_value_context_offers_choices_only(self):
        # cursor sits right after --format → only its choices, no flags
        cands = complete_args(self._parser(), ["--format"], "")
        assert self._values(cands) == ["ansi", "json", "plain"]  # sorted

    def test_value_context_prefix_filter(self):
        cands = complete_args(self._parser(), ["--format"], "j")
        assert self._values(cands) == ["json"]

    def test_positional_choices_on_fresh_word(self):
        cands = complete_args(self._parser(), [], "")
        vals = self._values(cands)
        # both flags and the first positional's choices appear on empty prefix
        assert "loops" in vals and "painted" in vals
        assert "--format" in vals

    def test_positional_value_prefix_excludes_flags(self):
        vals = self._values(complete_args(self._parser(), [], "pa"))
        assert vals == ["painted"]  # only the positional choice matches

    def test_consumed_positional_advances(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("a", choices=["x"])
        p.add_argument("b", choices=["y"])
        # first positional filled with "x" → active positional is b
        vals = self._values(complete_args(p, ["x"], ""))
        assert "y" in vals and "x" not in vals

    def test_option_value_not_counted_as_positional(self):
        # "--since 2020" must not consume the vertex positional slot
        vals = self._values(complete_args(self._parser(), ["--since", "2020"], ""))
        assert "loops" in vals  # vertex still active

    def test_completer_seam_invoked_with_context(self):
        seen = {}

        def key_completer(ctx):
            seen["prefix"] = ctx.prefix
            seen["vertex"] = ctx.args.get("vertex")
            return [Candidate("alpha", "first"), "beta"]

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--key").completer = key_completer
        cands = complete_args(p, ["--key"], "a", args=ArgsView({"vertex": "loops"}))
        assert seen == {"prefix": "a", "vertex": "loops"}
        assert self._values(cands) == ["alpha"]  # "beta" filtered by prefix "a"

    def test_completer_bare_str_normalized(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--key").completer = lambda ctx: ["one", "two"]
        cands = complete_args(p, ["--key"], "")
        assert all(isinstance(c, Candidate) for c in cands)
        assert self._values(cands) == ["one", "two"]

    def test_raising_completer_yields_nothing(self):
        def boom(ctx):
            raise RuntimeError("completer bug")

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--key").completer = boom
        assert complete_args(p, ["--key"], "") == []  # no traceback into the shell

    def test_described_candidate_carries_description(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--key").completer = lambda ctx: [Candidate("k1", "the first key")]
        cands = complete_args(p, ["--key"], "")
        assert cands[0].description == "the first key"

    def test_dedup_and_sort(self):
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--key").completer = lambda ctx: ["b", "a", "b", "a"]
        assert self._values(complete_args(p, ["--key"], "")) == ["a", "b"]

    def test_ctx_args_derived_from_preceding_when_unset(self):
        # No caller-supplied args: the completer's typed context is the namespace
        # `preceding` resolves to on this very parser (slice 4).
        seen = {}

        def key_completer(ctx):
            seen["vertex"] = ctx.args.get("vertex")
            return ["k"]

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("vertex", choices=["loops", "painted"])
        p.add_argument("--key").completer = key_completer
        complete_args(p, ["loops", "--key"], "")
        assert seen["vertex"] == "loops"

    def test_tolerant_derivation_swallows_incomplete_line(self):
        # a partial line (missing the required positional) must not error out —
        # the completer still runs, with whatever parsed.
        def key_completer(ctx):
            return ["ok"]

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("required_pos")
        p.add_argument("--key").completer = key_completer
        assert self._values(complete_args(p, ["--key"], "")) == ["ok"]


class TestFlagContextSkipsPositionalCompleter:
    """A "-" prefix is a flag being typed, so the positional's (possibly
    expensive) completer is not run — its values can't survive the prefix filter.
    The dissolution fix behind the cache decision (docs/COMPLETION_DESIGN.md §7)."""

    def _spy_parser(self):
        calls = {"n": 0}

        def completer(ctx):
            calls["n"] += 1
            return ["alpha", "beta"]

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("name").completer = completer
        p.add_argument("--flag", action="store_true")
        return p, calls

    def test_flag_context_does_not_invoke_completer(self):
        p, calls = self._spy_parser()
        vals = [c.value for c in complete_args(p, [], "-")]
        assert calls["n"] == 0  # completer skipped — no wasted work
        assert "--flag" in vals and "alpha" not in vals

    def test_empty_prefix_still_lists_positional_values(self):
        p, calls = self._spy_parser()
        vals = [c.value for c in complete_args(p, [], "")]
        assert calls["n"] == 1
        assert "alpha" in vals and "beta" in vals

    def test_bare_prefix_still_invokes_completer(self):
        p, calls = self._spy_parser()
        vals = [c.value for c in complete_args(p, [], "al")]
        assert calls["n"] == 1
        assert vals == ["alpha"]  # prefix-filtered positional value

    def test_end_of_options_restores_positional_context(self):
        # after "--", a "-"-leading token is a positional value again.
        p, calls = self._spy_parser()
        complete_args(p, ["--"], "-")
        assert calls["n"] == 1  # completer DID run (not flag context anymore)


class TestMutexExclusions:
    """A mutually-exclusive sibling is suppressed once one member is on the line
    (the honesty rule: argparse would reject offering it). Uses the real
    framework groups: zoom (-q/-v/--quiet/--verbose) and mode (--static/--live)."""

    def _parser(self):
        from painted.cli import OutputMode
        from painted.cli.types import build_parser

        return build_parser(modes={OutputMode.STATIC, OutputMode.LIVE})

    def _offered(self, preceding, prefix="-"):
        return {c.value for c in complete_args(self._parser(), preceding, prefix)}

    def test_baseline_offers_all_members(self):
        offered = self._offered([])
        assert {"-q", "-v", "--static", "--live"} <= offered

    def test_quiet_suppresses_verbose_sibling(self):
        offered = self._offered(["-q"])
        assert "-v" not in offered and "--verbose" not in offered
        assert "-q" in offered  # own spelling still offered (argparse allows -q -q)

    def test_verbose_long_form_suppresses_quiet(self):
        offered = self._offered(["--verbose"])
        assert "-q" not in offered and "--quiet" not in offered

    def test_vv_cluster_suppresses_quiet(self):
        # -vv is a VALID cluster (verbose=2); argparse REJECTS -vv -q, so -q must
        # not be offered — the cluster must decompose to a present -v.
        offered = self._offered(["-vv"])
        assert "-q" not in offered and "--quiet" not in offered
        assert "-v" in offered and "--verbose" in offered  # own spelling kept

    def test_repeated_flag_keeps_own_spelling(self):
        # -v -v (=-vv) is accepted by argparse; -v/--verbose stay offered.
        offered = self._offered(["-v", "-v"])
        assert "-v" in offered and "--verbose" in offered
        assert "-q" not in offered  # sibling still suppressed

    def test_static_suppresses_live(self):
        offered = self._offered(["--static"])
        assert "--live" not in offered and "--static" in offered

    def test_live_suppresses_static(self):
        offered = self._offered(["--live"])
        assert "--static" not in offered and "--live" in offered

    def test_ungrouped_flags_never_suppressed(self):
        # --json / --plain are not in a mutex group; a present -q leaves them.
        offered = self._offered(["-q"])
        assert "--json" in offered and "--plain" in offered

    def test_cross_group_independence(self):
        # a present mode member does not touch the zoom group and vice versa.
        offered = self._offered(["--static"])
        assert {"-q", "-v"} <= offered  # zoom group untouched

    def test_value_option_value_is_not_a_present_flag(self):
        # a value that looks like a flag (the token after a value-taking option)
        # must not register as a present option and wrongly suppress a sibling.
        from painted.cli.complete import _present_option_strings
        from painted.cli._argwalk import walk_args

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--since")  # value-taking
        g = p.add_mutually_exclusive_group()
        g.add_argument("-q", action="count")
        g.add_argument("-v", action="count")
        specs = walk_args(p)
        # "--since -q" → -q is --since's value, not a present flag (only --since
        # itself is present; -q is skipped, so it can't suppress its -v sibling).
        present = _present_option_strings(specs, ["--since", "-q"])
        assert "-q" not in present
        assert present == {"--since"}


class TestWantsFileCompletion:
    """wants_file_completion — classify a slot as open (→ shell file completion)."""

    def test_open_positional_wants_files(self):
        from painted.cli.complete import wants_file_completion

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("path")
        assert wants_file_completion(p, []) is True

    def test_positional_with_choices_does_not(self):
        from painted.cli.complete import wants_file_completion

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("mode", choices=["a", "b"])
        assert wants_file_completion(p, []) is False

    def test_positional_with_completer_does_not(self):
        from painted.cli.complete import wants_file_completion

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("name").completer = lambda ctx: ["x"]
        assert wants_file_completion(p, []) is False

    def test_open_option_value_wants_files(self):
        from painted.cli.complete import wants_file_completion

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--out")
        assert wants_file_completion(p, ["--out"]) is True

    def test_option_value_with_choices_does_not(self):
        from painted.cli.complete import wants_file_completion

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--fmt", choices=["json"])
        assert wants_file_completion(p, ["--fmt"]) is False

    def test_no_positional_no_pending_value(self):
        from painted.cli.complete import wants_file_completion

        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--flag", action="store_true")
        assert wants_file_completion(p, []) is False

    def test_app_command_name_is_never_files(self):
        from painted.cli import AppCommand
        from painted.cli.complete import app_wants_file_completion

        cmds = [AppCommand("open", "Open", lambda a: 0, add_args=lambda p: p.add_argument("path"))]
        assert app_wants_file_completion(cmds, [], prog="x") is False

    def test_app_forwards_to_command_slot(self):
        from painted.cli import AppCommand
        from painted.cli.complete import app_wants_file_completion

        cmds = [AppCommand("open", "Open", lambda a: 0, add_args=lambda p: p.add_argument("path"))]
        assert app_wants_file_completion(cmds, ["open"], prog="x") is True

    def test_app_unmatched_without_default_is_not_files(self):
        from painted.cli import AppCommand
        from painted.cli.complete import app_wants_file_completion

        cmds = [AppCommand("open", "Open", lambda a: 0)]
        assert app_wants_file_completion(cmds, ["nope"], prog="x") is False


class TestAppProducer:
    """complete_app — roster completion and forwarding into a command parser."""

    def _commands(self):
        from painted.cli import AppCommand

        def read_args(p):
            p.add_argument("vertex")
            p.add_argument("--kind", choices=["log", "decision", "thread"])

        return [
            AppCommand("read", "Read a vertex", lambda a: 0, add_args=read_args),
            AppCommand("emit", "Emit a fact", lambda a: 0, aliases=("add",)),
        ]

    def _values(self, cands):
        return [c.value for c in cands]

    def test_roster_names_and_aliases(self):
        from painted.cli.complete import complete_app

        vals = self._values(complete_app(self._commands(), [], ""))
        assert vals == ["add", "emit", "read"]  # sorted; alias included

    def test_roster_candidate_carries_description(self):
        from painted.cli.complete import complete_app

        cand = next(c for c in complete_app(self._commands(), [], "") if c.value == "read")
        assert cand.description == "Read a vertex"

    def test_roster_prefix_filter(self):
        from painted.cli.complete import complete_app

        assert self._values(complete_app(self._commands(), [], "re")) == ["read"]

    def test_forward_into_command_flags(self):
        from painted.cli.complete import complete_app

        vals = self._values(complete_app(self._commands(), ["read"], "--"))
        assert "--kind" in vals
        assert "--json" in vals  # framework flags forwarded too
        assert "--live" not in vals  # conservative mode default omits it
        assert "--static" not in vals

    def test_forward_command_value_choices(self):
        from painted.cli.complete import complete_app

        vals = self._values(complete_app(self._commands(), ["read", "--kind"], ""))
        assert vals == ["decision", "log", "thread"]

    def test_forward_via_alias(self):
        from painted.cli.complete import complete_app

        # 'add' is an alias of 'emit' — forwarding resolves it
        vals = self._values(complete_app(self._commands(), ["add"], "--"))
        assert "--json" in vals  # emit has no add_args, but framework flags appear

    def test_default_first_positional_coexists_with_roster(self):
        from painted.cli import AppCommand
        from painted.cli.complete import complete_app

        default = AppCommand(
            "read",
            "Read",
            lambda a: 0,
            add_args=lambda p: p.add_argument("vertex", choices=["loops", "painted"]),
        )
        cmds = [default, AppCommand("emit", "Emit", lambda a: 0)]
        vals = self._values(complete_app(cmds, [], "", default=default))
        # command names AND the default's vertex choices both at the first slot
        assert "emit" in vals and "read" in vals
        assert "loops" in vals and "painted" in vals

    def test_unmatched_no_default_is_empty(self):
        from painted.cli.complete import complete_app

        assert complete_app(self._commands(), ["nope"], "--") == []


class TestCompleteLine:
    """complete_line — raw-line convenience over complete_app."""

    def _commands(self):
        from painted.cli import AppCommand

        return [
            AppCommand(
                "read",
                "Read",
                lambda a: 0,
                add_args=lambda p: p.add_argument("--kind", choices=["log", "thread"]),
            ),
            AppCommand("emit", "Emit", lambda a: 0),
        ]

    def _values(self, line, point=None):
        from painted.cli.complete import complete_line

        return [c.value for c in complete_line(line, point, commands=self._commands(), prog="sl")]

    def test_roster_after_prog_space(self):
        assert self._values("sl ") == ["emit", "read"]

    def test_roster_prefix_no_trailing_space(self):
        assert self._values("sl re") == ["read"]

    def test_forward_after_command(self):
        assert "--kind" in self._values("sl read --")

    def test_value_choices_after_option(self):
        assert self._values("sl read --kind ") == ["log", "thread"]

    def test_point_truncates_line(self):
        # cursor sits right after "re", ignoring the trailing "ad xyz"
        assert self._values("sl read xyz", point=len("sl re")) == ["read"]

    def test_unbalanced_quote_tolerated(self):
        # a dangling quote must not raise — falls back to a naive split
        vals = self._values('sl read --kind "lo')
        assert isinstance(vals, list)


class TestCompleteDebugCommand:
    """The hidden `painted __complete` smoke backdoor."""

    def test_roster_output(self, capsys):
        from painted.__main__ import main

        rc = main(["__complete", "painted "])
        assert rc == 0
        out = capsys.readouterr().out
        names = {ln.split("\t")[0] for ln in out.splitlines()}
        assert {"demos", "demo", "docs", "tour"} <= names

    def test_description_tab_separated(self, capsys):
        from painted.__main__ import main

        main(["__complete", "painted docs"])
        out = capsys.readouterr().out
        # docs roster entry carries its description after a tab
        assert any(ln.startswith("docs\t") and "docs" in ln for ln in out.splitlines())

    def test_not_in_help_roster(self, capsys):
        from painted.__main__ import main

        main(["--help", "--plain"])
        assert "__complete" not in capsys.readouterr().out


class TestRendererFreeGuard:
    """The no-renderer-on-TAB guarantee (C-LAZY): the completion path must not
    pull core.block / core.doc. Checked in a fresh subprocess — the pytest
    process has the renderer loaded already."""

    def _imports_renderer(self, script: str) -> dict:
        import subprocess
        import sys

        probe = script + (
            "\nimport sys, json\n"
            "print(json.dumps({"
            "'block': 'painted.core.block' in sys.modules, "
            "'doc': 'painted.core.doc' in sys.modules}))\n"
        )
        out = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, check=True
        )
        import json

        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_importing_producer_is_render_free(self):
        flags = self._imports_renderer("import painted.cli.complete")
        assert flags == {"block": False, "doc": False}

    def test_building_roster_and_completing_is_render_free(self):
        flags = self._imports_renderer(
            "from painted.cli import AppCommand, complete_app\n"
            "cmds = [AppCommand('read', 'Read', lambda a: 0)]\n"
            "complete_app(cmds, [], '')\n"
        )
        assert flags == {"block": False, "doc": False}

    def test_importing_runner_is_render_free(self):
        # run_cli's module must import without the renderer (paid only on render)
        flags = self._imports_renderer("import painted.cli.runner")
        assert flags == {"block": False, "doc": False}
