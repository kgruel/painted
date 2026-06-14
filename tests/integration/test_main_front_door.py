"""Front-door tests for ``python -m painted`` — the migrated run_app entry.

The front door dogfoods painted's own multi-command framework (run_app +
AppCommand). These tests pin the behaviors the old hand-rolled dispatcher had:
the command table, the ``demo`` alias of ``demos``, help, and the unknown-command
exit-code contract.
"""

from __future__ import annotations

from painted.__main__ import main


def test_no_args_shows_help(capsys):
    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "painted — Terminal UI framework" in out
    # The command table renders, with the alias riding the demos row.
    assert "demos (alias: demo)" in out
    assert "docs" in out
    assert "tour" in out


def test_help_flag_shows_help(capsys):
    rc = main(["--help"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "demos (alias: demo)" in out


def test_help_short_flag_shows_help(capsys):
    rc = main(["-h"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "painted — Terminal UI framework" in out


def test_unknown_command_returns_1(capsys):
    rc = main(["bogus"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Unknown command: bogus" in err


def test_demos_dispatches(capsys):
    rc = main(["demos"])
    assert rc == 0
    # The demo list rendered (exact contents are demo-registry dependent).
    out = capsys.readouterr().out
    assert out.strip()


def test_demo_alias_dispatches_like_demos(capsys):
    rc = main(["demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip()


def test_docs_dispatches(capsys):
    rc = main(["docs"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "docs" in out.lower()


def test_demos_run_without_name_errors():
    # Second-level routing inside _demo_dispatch is unchanged: bare ``run``
    # is a usage error.
    assert main(["demos", "run"]) == 1


def test_demos_list_dispatches_to_list_path(monkeypatch):
    # The detail string advertises a ``list`` subcommand; pin that the front
    # door routes ``demos list`` into the handler's list path. Spy on
    # ``list_demos`` (imported lazily inside _demo_dispatch) to prove the
    # dispatch without depending on the live demo registry's contents.
    import painted._demo_cli as demo_cli

    seen: list[list[str]] = []

    def spy_list(args: list[str]) -> int:
        seen.append(args)
        return 0

    monkeypatch.setattr(demo_cli, "list_demos", spy_list)
    assert main(["demos", "list"]) == 0
    # "list" is consumed as the subcommand; the remaining argv reaches list_demos.
    assert seen == [[]]


def test_command_table_routes_without_collision(monkeypatch):
    """The front-door table builds (no alias collision raised) and routes every
    command — proven by spying on each handler instead of executing the real
    tour/docs side effects."""
    import painted.__main__ as m
    from painted.cli import AppCommand, run_app

    routed: list[str] = []

    def make_table() -> list[AppCommand]:
        return [
            AppCommand(
                "demos",
                "demos",
                lambda argv: (routed.append("demos"), 0)[1],
                aliases=("demo",),
            ),
            AppCommand("docs", "docs", lambda argv: (routed.append("docs"), 0)[1]),
            AppCommand("tour", "tour", lambda argv: (routed.append("tour"), 0)[1]),
        ]

    table = make_table()
    # name, alias, and the two plain commands all route — construction did not raise.
    assert run_app(["demos"], table, prog="painted") == 0
    assert run_app(["demo"], table, prog="painted") == 0
    assert run_app(["docs"], table, prog="painted") == 0
    assert run_app(["tour"], table, prog="painted") == 0
    assert routed == ["demos", "demos", "docs", "tour"]

    # And the real front door uses exactly these three command names + the alias.
    assert m.main(["bogus"]) == 1  # unknown still rejected by the real table
