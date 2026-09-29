"""Fieldwork preserves argv intent across interactive disclosure changes."""

import io
from pathlib import Path
import sys

import pytest

from painted import Fidelity, print_block
from painted.tui import TestSurface
from tools.capture import import_module_by_path

ROOT = Path(__file__).resolve().parents[2]
F = import_module_by_path(ROOT / "demos/examples/fieldwork.py", module_name="_fieldwork_cli_tests")


@pytest.fixture
def cli_app(monkeypatch):
    records = tuple(
        F._record(
            {
                "id": str(i),
                "kind": "incident",
                "ts": i,
                "payload": {
                    "name": f"subject {i}",
                    "message": "synthetic account " * 80,
                    "next_ref": str(1 - i),
                },
            }
        )
        for i in range(2)
    )
    archive = F.Archive("synthetic", records)
    monkeypatch.setattr(F, "load_archive", lambda store=None: archive)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    apps = []

    async def capture(app):
        apps.append(app)

    monkeypatch.setattr(F.Fieldwork, "run", capture)

    def launch(*args):
        monkeypatch.setattr(sys, "argv", ["fieldwork.py", "-i", "--record", "0", *args])
        assert F.main() == 0
        return apps[-1]

    return launch


def test_cli_and_key_depth_lowering_have_identical_facets(cli_app):
    cli = cli_app("-vv")
    keys = cli_app()
    keys.on_key("v")
    keys.on_key("v")
    assert (
        cli.location.fidelity.visible
        == keys.location.fidelity.visible
        == frozenset({"fields", "provenance"})
    )
    for depth in (2, 1, 0):
        cli.on_key("V")
        keys.on_key("V")
        assert cli.location.fidelity == keys.location.fidelity
        assert cli.location.fidelity.depth == depth
        assert not cli.location.fidelity.visible


@pytest.mark.parametrize(
    "flag,tag,key",
    [
        ("--provenance", "provenance", "p"),
        ("--fields", "fields", "f"),
        ("--checks", "checks", "c"),
        ("--matches", "matches", "m"),
    ],
)
def test_explicit_high_depth_flags_survive_lowering_and_toggle_off(cli_app, flag, tag, key):
    app = cli_app("-vv", flag)
    app.on_key("V")
    assert app.location.fidelity.visible == frozenset({tag})
    app.on_key(key)
    assert not app.location.fidelity.visible
    app.on_key(key)
    assert app.location.fidelity.visible == frozenset({tag})


def test_implied_facet_toggle_keeps_explicit_intent_and_follow_back_restores_it(cli_app):
    app = cli_app("-vv")
    app.on_key("p")  # explicitly request the facet even though depth already shows it
    assert app.notice == "provenance is now explicit; it stays shown when V reduces depth."
    app.on_key("V")
    assert app.location.fidelity.visible == frozenset({"provenance"})
    TestSurface(app, width=80, height=12, input_queue=["page_down", "tab"]).run_to_completion()
    original = app.location
    assert original.scroll > 0
    app.on_key("enter")
    assert app.view.selected.id == "1"
    app.on_key("p")
    app.on_key("v")
    app.on_key("backspace")
    assert app.location == original
    app.on_key("v")
    app.on_key("p")  # remove the explicit request; implication still applies
    assert app.notice == "provenance is also implied at depth 3; V reduces depth."
    assert app.location.fidelity.visible == frozenset({"fields", "provenance"})
    app.on_key("V")
    assert not app.location.fidelity.visible


def test_interactive_off_a_tty_renders_the_static_reading_without_a_surface(
    capsys, cli_app, monkeypatch
):
    # Off a TTY there is no keyboard to end the loop: -i degrades to the
    # static reading of the requested location, at natural width.
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    started = []

    async def refuse(app):
        started.append(app)

    monkeypatch.setattr(F.Fieldwork, "run", refuse)
    monkeypatch.setattr(sys, "argv", ["fieldwork.py", "-i", "--record", "0", "-v", "--checks"])
    assert F.main() == 0
    assert not started
    archive = F.load_archive()
    location = F.Location(
        selected="0",
        fidelity=Fidelity(depth=2, visible=frozenset({"checks"})),
    )
    expected = io.StringIO()
    print_block(
        F._render(F.project(archive, location), location.fidelity, None),
        expected,
        use_ansi=False,
    )
    out = capsys.readouterr().out
    assert out == expected.getvalue()
    assert ("synthetic account " * 80).strip() in out.splitlines()
    assert "Questions to take back to the system" in out


@pytest.mark.parametrize("tag,key", [("provenance", "p"), ("fields", "f")])
def test_every_toggle_of_a_depth_implied_facet_says_what_changed(cli_app, tag, key):
    # At depth 3 the facet is already shown, so neither toggle changes the
    # frame; the notice is the only visible record of the recorded intent.
    app = cli_app("-vv")
    shown = app.location.fidelity.visible
    app.on_key(key)
    assert app.location.fidelity.visible == shown
    assert app.location.explicit_facets == frozenset({tag})
    assert app.notice == f"{tag} is now explicit; it stays shown when V reduces depth."
    app.on_key(key)
    assert app.location.fidelity.visible == shown
    assert app.location.explicit_facets == frozenset()
    assert app.notice == f"{tag} is also implied at depth 3; V reduces depth."
