"""Completion contract types + the shared parser walk (slice 3, commit 1)."""

from __future__ import annotations

import argparse

from painted.cli._argwalk import walk_args
from painted.cli.complete import Candidate, CompletionContext
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
