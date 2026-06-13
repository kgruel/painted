"""Tests for AppRunner: app-level command routing through painted."""

import json

import pytest

from painted.cli import AppCommand, AppRunner, run_app
from painted.cli import HelpArg, Zoom
from painted.core.doc import Defs, Section


class TestAppCommand:
    """AppCommand is a frozen dataclass."""

    def test_frozen(self):
        cmd = AppCommand("test", "A test", lambda argv: 0)
        with pytest.raises(AttributeError):
            cmd.name = "other"  # type: ignore[misc]

    def test_fields(self):
        handler = lambda argv: 42
        cmd = AppCommand("status", "Show status", handler)
        assert cmd.name == "status"
        assert cmd.description == "Show status"
        assert cmd.handler is handler


class TestAppRunner:
    """AppRunner dispatches commands and renders help."""

    def _make_runner(self, **kwargs):
        commands = kwargs.pop(
            "commands",
            [
                AppCommand("status", "Show status", lambda argv: 0),
                AppCommand("log", "Show log", lambda argv: 0),
            ],
        )
        return AppRunner(
            commands=tuple(commands),
            prog=kwargs.get("prog", "test"),
            description=kwargs.get("description", "A test app"),
        )

    def test_dispatch_to_command(self):
        called_with = []

        def handler(argv):
            called_with.append(argv)
            return 0

        runner = AppRunner(
            commands=(AppCommand("go", "Do it", handler),),
            prog="test",
        )
        rc = runner.run(["go", "arg1", "arg2"])
        assert rc == 0
        assert called_with == [["arg1", "arg2"]]

    def test_exit_code_propagation(self):
        runner = AppRunner(
            commands=(AppCommand("fail", "Fail", lambda argv: 42),),
        )
        assert runner.run(["fail"]) == 42

    def test_no_args_shows_help(self, capsys):
        runner = self._make_runner()
        rc = runner.run([])
        assert rc == 0
        captured = capsys.readouterr()
        assert "status" in captured.out
        assert "log" in captured.out

    def test_help_flag(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["--help"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "status" in captured.out

    def test_help_short_flag(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["-h"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "status" in captured.out

    def test_unknown_command(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["bogus"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Unknown command: bogus" in captured.err

    def test_help_json(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["--help", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["title"] == "test"

    def test_help_plain(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["--help", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        # Plain output should not have ANSI codes
        assert "\033[" not in captured.out

    def test_help_verbose(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["--help", "-v"])
        assert rc == 0
        captured = capsys.readouterr()
        # At DETAILED, framework groups (min_zoom=SUMMARY) have eff=1: expanded but no detail
        assert "Zoom" in captured.out
        assert "-q, --quiet" in captured.out
        assert "Help" in captured.out

    def test_help_very_verbose(self, capsys):
        runner = self._make_runner()
        rc = runner.run(["--help", "-vv"])
        assert rc == 0
        captured = capsys.readouterr()
        # At FULL, framework groups (min_zoom=SUMMARY) have eff=2: expanded+detail
        assert "Controls how much detail" in captured.out
        assert "Add -v for more detail" in captured.out

    def test_help_shows_description(self, capsys):
        runner = self._make_runner(description="My great app")
        rc = runner.run(["--help", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "My great app" in captured.out

    def test_help_shows_prog(self, capsys):
        runner = self._make_runner(prog="myapp")
        rc = runner.run(["--help", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "myapp" in captured.out


class TestHelpDoc:
    """_help_doc produces the help document — the dissolution of HelpData."""

    def test_commands_lead_as_a_section(self):
        runner = AppRunner(
            commands=(
                AppCommand("a", "Do A", lambda argv: 0),
                AppCommand("b", "Do B", lambda argv: 0),
            ),
        )
        doc = runner._help_doc()
        sections = [n for n in doc.body if isinstance(n, Section)]
        commands = next(s for s in sections if s.heading == "Commands")
        assert commands.min_depth == Zoom.MINIMAL  # always expanded
        defs = next(n for n in commands.body if isinstance(n, Defs))
        assert [d.term for d in defs.items] == ["a", "b"]

    def test_framework_groups_subordinate(self):
        runner = AppRunner(
            commands=(AppCommand("a", "Do A", lambda argv: 0),),
        )
        doc = runner._help_doc()
        sections = [n for n in doc.body if isinstance(n, Section)]
        framework = {s.heading for s in sections if s.min_depth == Zoom.SUMMARY}
        assert {"Zoom", "Format", "Help"} <= framework

    def test_no_interaction_rules(self, capsys):
        """AppRunner help should not show interaction rules even at DETAILED."""
        runner = AppRunner(
            commands=(AppCommand("a", "Do A", lambda argv: 0),),
            prog="test",
        )
        rc = runner.run(["--help", "-v", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Interaction rules" not in captured.out


class TestRunApp:
    """Convenience function run_app."""

    def test_basic(self):
        called = []
        commands = [AppCommand("go", "Go", lambda argv: (called.append(1), 0)[1])]
        rc = run_app(["go"], commands, prog="test")
        assert rc == 0
        assert called == [1]

    def test_help(self, capsys):
        commands = [AppCommand("go", "Go", lambda argv: 0)]
        rc = run_app(["--help", "--plain"], commands, prog="test")
        assert rc == 0
        captured = capsys.readouterr()
        assert "go" in captured.out

    def test_accepts_list_or_tuple(self):
        commands = [AppCommand("go", "Go", lambda argv: 0)]
        assert run_app(["go"], commands) == 0
        assert run_app(["go"], tuple(commands)) == 0


class TestSubcommandHelp:
    """Subcommand help: AppRunner intercepts -h when help_args is set."""

    def _make_runner(self):
        called = []
        handler = lambda argv: (called.append(argv), 0)[1]
        commands = (
            # Display command — no help_args, handler sees -h
            AppCommand("status", "Show status", handler),
            # Action command — help_args set, AppRunner intercepts -h
            AppCommand(
                "emit",
                "Inject a fact",
                handler,
                help_args=[
                    HelpArg("vertex", "Vertex name", positional=True),
                    HelpArg("kind", "Fact kind", positional=True),
                    HelpArg("--observer", "Observer string", default=""),
                    HelpArg("--dry-run", "Print without storing"),
                ],
            ),
        )
        return AppRunner(commands=commands, prog="loops"), called

    def test_subcommand_help_intercept(self, capsys):
        """Handler not called when -h intercepted."""
        runner, called = self._make_runner()
        rc = runner.run(["emit", "-h", "--plain"])
        assert rc == 0
        assert called == []
        captured = capsys.readouterr()
        assert "Inject a fact" in captured.out

    def test_no_help_args_passes_through(self):
        """Display command pattern: handler sees -h."""
        runner, called = self._make_runner()
        runner.run(["status", "-h"])
        assert called == [["-h"]]

    def test_subcommand_help_no_framework_groups(self, capsys):
        """No Zoom/Format groups in subcommand help."""
        runner, _ = self._make_runner()
        rc = runner.run(["emit", "-h", "-vv", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "Zoom" not in captured.out
        assert "Format" not in captured.out

    def test_subcommand_help_shows_args(self, capsys):
        """Command args visible in help output."""
        runner, _ = self._make_runner()
        rc = runner.run(["emit", "-h", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "vertex" in captured.out
        assert "kind" in captured.out
        assert "--observer" in captured.out
        assert "--dry-run" in captured.out

    def test_subcommand_help_json(self, capsys):
        """--json serializes the help Doc node tree."""
        runner, _ = self._make_runner()
        rc = runner.run(["emit", "-h", "--json"])
        assert rc == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["title"] == "loops emit"
        # The description is the leading Prose; the only Section is Help.
        headings = [n.get("heading") for n in data["body"] if "heading" in n]
        assert headings == ["Help"]
        assert "Zoom" not in headings and "Format" not in headings

    def test_subcommand_help_prog(self, capsys):
        """Prog shows 'loops emit'."""
        runner, _ = self._make_runner()
        rc = runner.run(["emit", "-h", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "loops emit" in captured.out


class TestAliases:
    """AppCommand.aliases: alternate spellings that route to one command."""

    def test_alias_routes_to_handler(self):
        called = []
        cmd = AppCommand(
            "demos", "List demos", lambda argv: (called.append(argv), 0)[1], aliases=("demo",)
        )
        runner = AppRunner(commands=(cmd,), prog="painted")
        # Both the name and the alias dispatch to the same handler.
        assert runner.run(["demos", "x"]) == 0
        assert runner.run(["demo", "y"]) == 0
        assert called == [["x"], ["y"]]

    def test_alias_coerced_to_tuple(self):
        # A non-tuple sequence is coerced, mirroring help_args/tags.
        cmd = AppCommand("demos", "List demos", lambda argv: 0, aliases=["demo", "d"])
        assert cmd.aliases == ("demo", "d")

    def test_alias_appears_in_help(self, capsys):
        cmd = AppCommand("demos", "List demos", lambda argv: 0, aliases=("demo",))
        runner = AppRunner(commands=(cmd,), prog="painted")
        rc = runner.run(["--help", "--plain"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "demos (alias: demo)" in out

    def test_multiple_aliases_pluralize_in_help(self, capsys):
        cmd = AppCommand("demos", "List demos", lambda argv: 0, aliases=("demo", "d"))
        runner = AppRunner(commands=(cmd,), prog="painted")
        rc = runner.run(["--help", "--plain"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "demos (aliases: demo, d)" in out

    def test_alias_in_help_doc_term(self):
        cmd = AppCommand("demos", "List demos", lambda argv: 0, aliases=("demo",))
        runner = AppRunner(commands=(cmd,), prog="painted")
        doc = runner._help_doc()
        sections = [n for n in doc.body if isinstance(n, Section)]
        commands = next(s for s in sections if s.heading == "Commands")
        defs = next(n for n in commands.body if isinstance(n, Defs))
        assert defs.items[0].term == "demos (alias: demo)"

    def test_alias_collides_with_command_name_raises(self):
        with pytest.raises(ValueError, match="collides with command"):
            AppRunner(
                commands=(
                    AppCommand("demos", "List demos", lambda argv: 0, aliases=("docs",)),
                    AppCommand("docs", "List docs", lambda argv: 0),
                )
            )

    def test_alias_collides_with_other_alias_raises(self):
        with pytest.raises(ValueError, match="collides with the same alias"):
            AppRunner(
                commands=(
                    AppCommand("demos", "List demos", lambda argv: 0, aliases=("x",)),
                    AppCommand("docs", "List docs", lambda argv: 0, aliases=("x",)),
                )
            )

    def test_alias_duplicates_own_name_raises(self):
        with pytest.raises(ValueError, match="alias of itself"):
            AppRunner(
                commands=(AppCommand("demos", "List demos", lambda argv: 0, aliases=("demos",)),)
            )

    def test_command_lists_same_alias_twice_raises(self):
        # A single command repeating an alias is its own error class — the
        # message names the command, not a self-referential "other" owner.
        with pytest.raises(ValueError, match="lists alias 'x' more than once"):
            AppRunner(
                commands=(AppCommand("demos", "List demos", lambda argv: 0, aliases=("x", "x")),)
            )

    def test_run_app_routes_alias(self):
        called = []
        commands = [
            AppCommand(
                "demos", "List demos", lambda argv: (called.append(argv), 0)[1], aliases=("demo",)
            )
        ]
        assert run_app(["demo", "z"], commands, prog="painted") == 0
        assert called == [["z"]]


class TestNesting:
    """Composed AppRunners for nested dispatch."""

    def test_nested_dispatch(self):
        inner_called = []

        inner = AppRunner(
            commands=(
                AppCommand(
                    "start", "Start session", lambda argv: (inner_called.append(argv), 0)[1]
                ),
                AppCommand("stop", "Stop session", lambda argv: 1),
            ),
            prog="myapp session",
        )

        outer = AppRunner(
            commands=(
                AppCommand("status", "Show status", lambda argv: 0),
                AppCommand("session", "Session commands", inner.run),
            ),
            prog="myapp",
        )

        rc = outer.run(["session", "start", "foo"])
        assert rc == 0
        assert inner_called == [["foo"]]

    def test_nested_help(self, capsys):
        inner = AppRunner(
            commands=(AppCommand("start", "Start session", lambda argv: 0),),
            prog="myapp session",
            description="Session management",
        )
        outer = AppRunner(
            commands=(AppCommand("session", "Session commands", inner.run),),
            prog="myapp",
        )

        # Outer help
        rc = outer.run(["--help", "--plain"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "session" in captured.out

        # Inner help
        rc = outer.run(["session"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "start" in captured.out

    def test_nested_unknown(self, capsys):
        inner = AppRunner(
            commands=(AppCommand("start", "Start", lambda argv: 0),),
            prog="myapp session",
        )
        outer = AppRunner(
            commands=(AppCommand("session", "Session", inner.run),),
            prog="myapp",
        )
        rc = outer.run(["session", "bogus"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "Unknown command: bogus" in captured.err
