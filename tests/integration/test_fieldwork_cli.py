"""Fieldwork preserves argv intent across interactive disclosure changes."""

from pathlib import Path
import sys

import pytest

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
    assert "implied" in app.notice
    assert app.location.fidelity.visible == frozenset({"fields", "provenance"})
    app.on_key("V")
    assert not app.location.fidelity.visible
