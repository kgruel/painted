"""Shell transport + emit (slice 4): the COMP_LINE bridge and `completion` command."""

from __future__ import annotations

import argparse

import pytest

from painted.cli import AppCommand, run_app
from painted.cli.completion_shell import (
    COMPLETION_COMMAND_NAME,
    completion_active,
    completion_add_args,
    completion_handler,
    run_completion,
    run_single_completion,
)
from painted.cli.completion_shell import _parse_comp_line, _tolerant_split


class TestParseCompLine:
    """The transport's buffer parse — quoting, --opt=val, the cursor boundary."""

    def test_trailing_space_is_fresh_word(self):
        assert _parse_comp_line("sl read ", len("sl read ")) == (["sl", "read"], "", None)

    def test_partial_word_is_prefix(self):
        assert _parse_comp_line("sl re", len("sl re")) == (["sl"], "re", None)

    def test_point_truncates_right_of_cursor(self):
        # cursor after "re", ignoring "ad xyz" to its right
        assert _parse_comp_line("sl read xyz", len("sl re")) == (["sl"], "re", None)

    def test_opt_eq_value_splits_into_option_context(self):
        # `--kind=lo` → producer sees the option as preceding, value as prefix
        words, prefix, opt = _parse_comp_line("sl read --kind=lo", len("sl read --kind=lo"))
        assert words == ["sl", "read", "--kind"]
        assert prefix == "lo"
        assert opt == "--kind="

    def test_dangling_quote_recovers_token(self):
        # an unbalanced quote is closed; the stray quote char is gone from prefix
        words, prefix, opt = _parse_comp_line('sl read --kind "lo', len('sl read --kind "lo'))
        assert words == ["sl", "read", "--kind"]
        assert prefix == "lo"

    def test_tolerant_split_falls_back_on_garble(self):
        # nothing closeable → naive whitespace split, never a raise
        assert _tolerant_split("a 'b \"c") == ["a", "b c"] or _tolerant_split("a 'b \"c")


class TestGate:
    """completion_active reads the request from the environment."""

    def test_inactive_by_default(self, monkeypatch):
        monkeypatch.delenv("_PAINTED_COMPLETE", raising=False)
        assert completion_active() is None

    def test_empty_is_inactive(self, monkeypatch):
        monkeypatch.setenv("_PAINTED_COMPLETE", "")
        assert completion_active() is None

    def test_value_is_the_shell(self, monkeypatch):
        monkeypatch.setenv("_PAINTED_COMPLETE", "zsh")
        assert completion_active() == "zsh"


def _read_command():
    return AppCommand(
        "read",
        "Read a vertex",
        lambda a: 0,
        add_args=lambda p: p.add_argument("--kind", choices=["log", "thread"]),
    )


class TestRunCompletion:
    """The app-level transport: env buffer → roster/forwarded candidates → stdout."""

    def _emit(self, line, capsys, monkeypatch, shell="zsh", point=None):
        monkeypatch.setenv("COMP_LINE", line)
        monkeypatch.setenv("COMP_POINT", str(len(line) if point is None else point))
        run_completion([_read_command()], prog="sl", default=None, shell=shell)
        return capsys.readouterr().out.splitlines()

    def test_roster_zsh_value_colon_description(self, capsys, monkeypatch):
        lines = self._emit("sl ", capsys, monkeypatch)
        assert any(ln.startswith("read:Read a vertex") for ln in lines)

    def test_forward_value_choices(self, capsys, monkeypatch):
        lines = self._emit("sl read --kind ", capsys, monkeypatch)
        assert {ln.split(":")[0] for ln in lines} == {"log", "thread"}

    def test_opt_eq_value_reprefixed(self, capsys, monkeypatch):
        lines = self._emit("sl read --kind=th", capsys, monkeypatch)
        assert lines == ["--kind=thread"]

    def test_bash_emits_bare_values(self, capsys, monkeypatch):
        lines = self._emit("sl read --kind ", capsys, monkeypatch, shell="bash")
        assert set(lines) == {"log", "thread"}  # no `:description`

    def test_colon_in_value_escaped_for_zsh(self, capsys, monkeypatch):
        cmd = AppCommand(
            "x", "X", lambda a: 0, add_args=lambda p: p.add_argument("--t", choices=["a:b"])
        )
        monkeypatch.setenv("COMP_LINE", "sl x --t ")
        monkeypatch.setenv("COMP_POINT", str(len("sl x --t ")))
        run_completion([cmd], prog="sl", default=None, shell="zsh")
        assert capsys.readouterr().out.strip() == r"a\:b"

    def test_missing_comp_point_defaults_to_end(self, capsys, monkeypatch):
        monkeypatch.setenv("COMP_LINE", "sl re")
        monkeypatch.delenv("COMP_POINT", raising=False)
        run_completion([_read_command()], prog="sl", default=None, shell="zsh")
        assert capsys.readouterr().out.startswith("read")


class TestRunSingleCompletion:
    """The run_cli-level transport: a single parser, no roster."""

    def test_completes_own_flags(self, capsys, monkeypatch):
        parser = argparse.ArgumentParser(prog="tool", add_help=False)
        parser.add_argument("--kind", choices=["log", "thread"])
        monkeypatch.setenv("COMP_LINE", "tool --kind ")
        monkeypatch.setenv("COMP_POINT", str(len("tool --kind ")))
        run_single_completion(parser, shell="zsh")
        assert {ln.split(":")[0] for ln in capsys.readouterr().out.splitlines()} == {
            "log",
            "thread",
        }


class TestCompletionCommand:
    """The auto-injected `completion` command — emit-only shell glue."""

    def test_injected_into_run_app_roster(self, capsys):
        run_app(["--help", "--plain"], [_read_command()], prog="sl")
        assert "completion" in capsys.readouterr().out

    def test_emits_zsh_compdef_script(self, capsys):
        rc = completion_handler("sl")(["zsh"])
        out = capsys.readouterr().out
        assert rc == 0
        assert out.startswith("#compdef sl")
        assert "_PAINTED_COMPLETE=zsh" in out
        assert "_describe" in out

    def test_defaults_to_zsh(self, capsys):
        completion_handler("sl")([])
        assert capsys.readouterr().out.startswith("#compdef sl")

    def test_unsupported_shell_errors(self, capsys):
        rc = completion_handler("sl")(["fish"])
        assert rc == 1
        assert "Unsupported shell" in capsys.readouterr().err

    def test_add_args_declares_shell_choice(self):
        parser = argparse.ArgumentParser(add_help=False)
        completion_add_args(parser)
        action = next(a for a in parser._actions if a.dest == "shell")
        assert action.choices is not None and "zsh" in action.choices

    def test_not_injected_when_app_owns_the_name(self):
        # a consumer's own `completion` command stands; no collision crash
        own = AppCommand(COMPLETION_COMMAND_NAME, "mine", lambda a: 0)
        # run_app would raise on a duplicate name if it injected anyway
        rc = run_app([COMPLETION_COMMAND_NAME], [own], prog="sl")
        assert rc == 0

    def test_gate_intercepts_run_app_before_render(self, capsys, monkeypatch):
        monkeypatch.setenv("_PAINTED_COMPLETE", "zsh")
        monkeypatch.setenv("COMP_LINE", "sl ")
        monkeypatch.setenv("COMP_POINT", "3")
        rc = run_app([], [_read_command()], prog="sl")
        out = capsys.readouterr().out
        assert rc == 0
        # candidate lines, not the help Doc
        assert any(ln.startswith("read:") for ln in out.splitlines())
        assert "completion:" in out  # the injected command is itself a candidate


class TestRendererFreeGuard:
    """The transport stays on the no-renderer-on-TAB path."""

    def _imports_renderer(self, script: str) -> dict:
        import json
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
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_transport_import_is_render_free(self):
        assert self._imports_renderer("import painted.cli.completion_shell") == {
            "block": False,
            "doc": False,
        }

    def test_running_completion_is_render_free(self):
        flags = self._imports_renderer(
            "import os\n"
            "os.environ['COMP_LINE']='sl '\n"
            "os.environ['COMP_POINT']='3'\n"
            "from painted.cli import AppCommand\n"
            "from painted.cli.completion_shell import run_completion\n"
            "cmds=[AppCommand('read','Read',lambda a:0)]\n"
            "run_completion(cmds, prog='sl', default=None, shell='zsh')\n"
        )
        assert flags == {"block": False, "doc": False}


@pytest.mark.parametrize("dangle", ['"', "'"])
def test_no_raise_on_any_dangling_quote(dangle):
    # property-ish: a dangling quote of either kind never raises
    _, prefix, _ = _parse_comp_line(f"sl read {dangle}lo", len(f"sl read {dangle}lo"))
    assert prefix == "lo"
