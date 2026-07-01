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
from painted.cli.completion_shell import (
    _detect_shell,
    _install_target,
    _parse_comp_line,
    _tolerant_split,
    install_completion,
)


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


class TestFileDirective:
    """The file/dir directive — an open slot tells the glue to add files."""

    def _open_cmd(self):
        return AppCommand("open", "Open", lambda a: 0, add_args=lambda p: p.add_argument("path"))

    def _lines(self, line, cmds, capsys, monkeypatch, shell="zsh"):
        monkeypatch.setenv("COMP_LINE", line)
        monkeypatch.setenv("COMP_POINT", str(len(line)))
        run_completion(cmds, prog="x", default=None, shell=shell)
        return capsys.readouterr().out.splitlines()

    def test_directive_emitted_for_open_slot(self, capsys, monkeypatch):
        from painted.cli.completion_shell import _FILE_DIRECTIVE

        lines = self._lines("x open ", [self._open_cmd()], capsys, monkeypatch)
        assert _FILE_DIRECTIVE in lines

    def test_no_directive_for_choices_slot(self, capsys, monkeypatch):
        from painted.cli.completion_shell import _FILE_DIRECTIVE

        cmd = AppCommand(
            "fmt", "F", lambda a: 0, add_args=lambda p: p.add_argument("m", choices=["a"])
        )
        lines = self._lines("x fmt ", [cmd], capsys, monkeypatch)
        assert _FILE_DIRECTIVE not in lines

    def test_directive_starts_with_unit_separator(self, capsys, monkeypatch):
        # control-char prefix can't collide with a real candidate value
        lines = self._lines("x open ", [self._open_cmd()], capsys, monkeypatch)
        assert any(ln.startswith("\x1f") for ln in lines)

    def test_no_directive_when_completing_command_name(self, capsys, monkeypatch):
        from painted.cli.completion_shell import _FILE_DIRECTIVE

        lines = self._lines("x ", [self._open_cmd()], capsys, monkeypatch)
        assert _FILE_DIRECTIVE not in lines

    def test_directive_suppressed_under_opt_eq_value(self, capsys, monkeypatch):
        from painted.cli.completion_shell import _FILE_DIRECTIVE

        cmd = AppCommand("o", "O", lambda a: 0, add_args=lambda p: p.add_argument("--out"))
        lines = self._lines("x o --out=fo", [cmd], capsys, monkeypatch)
        assert _FILE_DIRECTIVE not in lines


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
        assert "_files" in out  # the file directive triggers filesystem completion

    def test_no_arg_falls_back_to_zsh_when_shell_unknown(self, capsys, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        completion_handler("sl")([])
        assert capsys.readouterr().out.startswith("#compdef sl")

    def test_no_arg_detects_shell_from_env(self, capsys, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/bash")
        completion_handler("sl")([])
        assert "complete -F _sl_complete sl" in capsys.readouterr().out

    def test_explicit_shell_overrides_detection(self, capsys, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/bash")
        completion_handler("sl")(["zsh"])
        assert capsys.readouterr().out.startswith("#compdef sl")

    def test_emits_bash_complete_script(self, capsys):
        rc = completion_handler("sl")(["bash"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "complete -F _sl_complete sl" in out
        assert "_PAINTED_COMPLETE=bash" in out
        assert "COMPREPLY" in out
        assert "compopt -o default" in out  # the file directive path

    def test_bash_is_an_offered_shell(self):
        parser = argparse.ArgumentParser(add_help=False)
        completion_add_args(parser)
        action = next(a for a in parser._actions if a.dest == "shell")
        assert action.choices is not None and {"bash", "zsh"} <= set(action.choices)

    def test_unsupported_shell_errors(self, capsys):
        rc = completion_handler("sl")(["fish"])
        assert rc == 1
        assert "invalid choice" in capsys.readouterr().err  # rejected by the declared grammar

    def test_handler_rejects_malformed_invocations(self, capsys, monkeypatch):
        # the handler parses with its OWN declared grammar — no lenient hand-scan.
        monkeypatch.setenv("SHELL", "/bin/zsh")
        for argv in (["--install=x"], ["--frobnicate"], ["bash", "zsh"]):
            assert completion_handler("sl")(argv) == 1, argv
            capsys.readouterr()  # drain

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


class TestCompletionInstall:
    """`completion --install` writes an owned completion file (never a dotfile)."""

    def test_detect_shell_from_env(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/opt/homebrew/bin/zsh")
        assert _detect_shell() == "zsh"
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert _detect_shell() == "bash"

    def test_detect_shell_none_when_unknown(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/usr/bin/fish")  # not an emitter
        assert _detect_shell() is None
        monkeypatch.delenv("SHELL", raising=False)
        assert _detect_shell() is None

    def test_install_refuses_when_shell_undetected(self, monkeypatch, tmp_path, capsys):
        # a fish user running `completion --install` must NOT get a silent zsh
        # file written — the auto-detect fallback refuses rather than guess.
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        monkeypatch.setenv("ZDOTDIR", str(tmp_path))
        rc = completion_handler("sl")(["--install"])
        assert rc == 1
        assert "detect your shell" in capsys.readouterr().err
        assert not (tmp_path / ".zsh" / "completions" / "_sl").exists()

    def test_install_target_zsh_honors_zdotdir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZDOTDIR", str(tmp_path))
        assert _install_target("zsh", "sl") == tmp_path / ".zsh" / "completions" / "_sl"

    def test_install_target_bash_xdg(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BASH_COMPLETION_USER_DIR", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        expected = tmp_path / "bash-completion" / "completions" / "sl"
        assert _install_target("bash", "sl") == expected

    def test_install_target_unknown_shell_is_none(self):
        assert _install_target("fish", "sl") is None

    def test_install_writes_the_file(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("ZDOTDIR", str(tmp_path))
        rc = install_completion("zsh", "sl")
        target = tmp_path / ".zsh" / "completions" / "_sl"
        assert rc == 0
        assert target.read_text(encoding="utf-8").startswith("#compdef sl")
        assert str(target) in capsys.readouterr().out  # hint names the file

    def test_dry_run_writes_nothing(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setenv("ZDOTDIR", str(tmp_path))
        rc = install_completion("zsh", "sl", dry_run=True)
        target = tmp_path / ".zsh" / "completions" / "_sl"
        out = capsys.readouterr().out
        assert rc == 0
        assert not target.exists()
        assert "Would write" in out and str(target) in out and "#compdef sl" in out

    def test_idempotent_reinstall(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZDOTDIR", str(tmp_path))
        install_completion("zsh", "sl")
        install_completion("zsh", "sl")
        target = tmp_path / ".zsh" / "completions" / "_sl"
        assert target.is_file()  # single file, no .tmp residue
        assert not (target.parent / "_sl.tmp").exists()

    def test_unsupported_install_shell_refuses(self, capsys):
        rc = install_completion("fish", "sl")
        assert rc == 1
        assert "installable" in capsys.readouterr().err

    def test_write_error_degrades_to_advice(self, monkeypatch, tmp_path, capsys):
        # make the target dir unwritable-into by pointing at a file, not a dir
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        monkeypatch.setenv("ZDOTDIR", str(blocker))  # .zsh under a file -> OSError
        rc = install_completion("zsh", "sl")
        assert rc == 1
        assert "manually" in capsys.readouterr().err  # falls back to advice

    def test_flags_declared_and_shell_default_none(self):
        parser = argparse.ArgumentParser(add_help=False)
        completion_add_args(parser)
        dests = {a.dest for a in parser._actions}
        assert {"install", "dry_run", "shell"} <= dests
        shell_action = next(a for a in parser._actions if a.dest == "shell")
        assert shell_action.default is None
        assert shell_action.choices is not None and {"bash", "zsh"} <= set(shell_action.choices)

    def test_install_flags_complete_honestly(self):
        from painted.cli.complete import complete_app

        cmd = AppCommand("completion", "setup", lambda a: 0, add_args=completion_add_args)
        vals = {c.value for c in complete_app([cmd], ["completion"], "--")}
        assert "--install" in vals and "--dry-run" in vals


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

    def test_install_is_render_free(self):
        # writing the glue must not pull the renderer either (dry_run avoids the
        # actual filesystem write in the probe).
        flags = self._imports_renderer(
            "import os, tempfile\n"
            "os.environ['ZDOTDIR']=tempfile.mkdtemp()\n"
            "from painted.cli.completion_shell import install_completion\n"
            "install_completion('zsh','sl', dry_run=True)\n"
        )
        assert flags == {"block": False, "doc": False}


class TestZshGlueCommandScope:
    """_zsh_script must reconstruct COMP_LINE from $words/$CURRENT, not from
    $BUFFER/$CURSOR — Finding 1: compound-line bug on `git pull && painted dem`."""

    def _script(self):
        from painted.cli.completion_shell import _zsh_script

        return _zsh_script("sl")

    def test_no_buffer_in_zsh_script(self):
        # $BUFFER is the ENTIRE edit buffer (compound line); using it with
        # && or ; sequences sends the wrong line to the transport.
        assert "$BUFFER" not in self._script()

    def test_no_cursor_in_zsh_script(self):
        assert "$CURSOR" not in self._script()

    def test_words_array_used(self):
        # $words is the zsh completion array for the current command only.
        assert "$words" in self._script() or "${words" in self._script()

    def test_current_index_used(self):
        # $CURRENT is the index of the word under the cursor in $words.
        assert "$CURRENT" in self._script()

    def test_comp_line_comp_point_still_present(self):
        # The transport still reads COMP_LINE/COMP_POINT; they must be set
        # (just sourced from the command-scoped reconstruction, not from $BUFFER).
        script = self._script()
        assert "COMP_LINE=" in script
        assert "COMP_POINT=" in script

    def test_script_uses_words_1_as_program(self):
        # ${words[1]} is the program as actually invoked — still correct.
        assert "${words[1]}" in self._script()

    def test_explicit_return_status(self):
        # The function must return 0 when it added matches. `(( files )) && _files`
        # as the last line returns 1 when files=0, making compsys retry the
        # function once per matcher-list entry and duplicate every candidate.
        script = self._script()
        assert "return ret" in script
        assert not script.rstrip().endswith("_files")

    def test_tolerant_split_still_importable_from_shell(self):
        # completion_shell.py re-exports _tolerant_split (from complete.py);
        # the existing import in tests and potential external consumers must work.
        from painted.cli.completion_shell import _tolerant_split  # noqa: F401


@pytest.mark.parametrize("dangle", ['"', "'"])
def test_no_raise_on_any_dangling_quote(dangle):
    # property-ish: a dangling quote of either kind never raises
    _, prefix, _ = _parse_comp_line(f"sl read {dangle}lo", len(f"sl read {dangle}lo"))
    assert prefix == "lo"
