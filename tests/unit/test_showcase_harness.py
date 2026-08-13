"""Laws of the showcase harness (demos/showcase/_harness.py).

Two kinds of test here, and the split is the point. The first half pins what
the harness *does* — one declaration reaching both the parser and `--help`,
`prog` derived rather than typed. The second half is the ratchet: an
enumerable property over the showcase files on disk, with a shrink-only
allowlist, so the tier's conventions cannot drift one demo at a time.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

import pytest

_PROJECT = Path(__file__).resolve().parent.parent.parent
_SHOWCASE = _PROJECT / "demos" / "showcase"

# Resolves through the path tests/conftest.py sets for the suite.
import _harness as H  # noqa: E402


def _showcase_sources() -> list[Path]:
    return sorted(p for p in _SHOWCASE.glob("*.py") if not p.name.startswith("_"))


# --- What the harness does ---


@pytest.fixture
def spy(monkeypatch):
    """Capture the run_cli call the harness would have made."""
    seen: dict = {}

    def fake_run_cli(argv, **kwargs):
        seen["argv"] = argv
        seen.update(kwargs)
        return 0

    monkeypatch.setattr(H, "run_cli", fake_run_cli)
    return seen


def _run(spy_dict, monkeypatch, argv: list[str], **kw) -> dict:
    monkeypatch.setattr(H.sys, "argv", ["prog", *argv])
    H.showcase_main(
        doc="a docstring",
        file="/somewhere/donut.py",
        renderer=lambda *a: None,
        fetch=lambda ns: ns,
        **kw,
    )
    return spy_dict


def test_one_declaration_reaches_both_the_parser_and_help(spy, monkeypatch) -> None:
    """The whole reason the harness exists: an arg is written once.

    Before this, every showcase declared each argument twice — once for the
    pre-parser, once for HelpArg — with the default written out both times.
    Nothing had drifted; nothing can now.
    """
    arg = H.ShowcaseArg("--frame", "pose shown by static output", 400, type=int)
    seen = _run(spy, monkeypatch, ["--frame", "750"], args=(arg,))

    assert seen["fetch"]().frame == 750, "the parser did not receive the declaration"
    (help_arg,) = seen["help_args"]
    assert help_arg.name == "--frame"
    assert help_arg.default == "400", "the help default is the declared default, stringified once"


def test_declared_args_are_peeled_before_run_cli_sees_them(spy, monkeypatch) -> None:
    """Demo args must not reach the framework parser, which would reject them."""
    arg = H.ShowcaseArg("--frame", "h", 400, type=int)
    seen = _run(spy, monkeypatch, ["--frame", "750", "-vv", "--json"], args=(arg,))
    assert seen["argv"] == ["-vv", "--json"]


def test_prog_is_derived_from_the_file_not_typed(spy, monkeypatch) -> None:
    """Ten hand-maintained strings that could each drift from their filename."""
    seen = _run(spy, monkeypatch, [])
    assert seen["prog"] == "donut.py"


def test_the_tier_settings_are_fixed_by_the_harness(spy, monkeypatch) -> None:
    """Surface delivery is the showcase tier's defining property. It is not
    a per-demo choice, so it is not a per-demo line."""
    seen = _run(spy, monkeypatch, [])
    assert seen["live_delivery"] == "surface"
    assert seen["live_meter"] is True
    assert seen["description"] == "a docstring"


def test_a_showcase_without_a_stream_declares_no_stream(spy, monkeypatch) -> None:
    seen = _run(spy, monkeypatch, [])
    assert seen["fetch_stream"] is None


def test_choices_and_string_defaults_survive_the_round_trip(spy, monkeypatch) -> None:
    """life and wireworld pick from a named set; their default is already a str."""
    arg = H.ShowcaseArg("--circuit", "machine to run", "diodes", choices=("diodes", "clock"))
    seen = _run(spy, monkeypatch, ["--circuit", "clock"], args=(arg,))
    assert seen["fetch"]().circuit == "clock"
    assert seen["help_args"][0].default == "diodes"
    with pytest.raises(SystemExit):  # argparse rejects an undeclared choice
        _run(spy, monkeypatch, ["--circuit", "nonsense"], args=(arg,))


def test_the_harness_does_not_wire_args_into_fetch(spy, monkeypatch) -> None:
    """The namespace is handed over whole; which arg feeds which call is the
    demo's business. A harness guessing at that would be a worse contract."""
    arg = H.ShowcaseArg("--seed", "h", 7, type=int)
    seen = _run(spy, monkeypatch, [], args=(arg,))
    ns = seen["fetch"]()
    assert isinstance(ns, argparse.Namespace)
    assert ns.seed == 7


# --- The ratchet ---

# Shrink-only. A name here is a showcase that has not adopted the harness yet,
# never one that opted out. harmonograph.py is pre-listed because it is in
# flight on another branch (showcase-harmonograph): its merge should land one
# red — the ruled-wrong `implied_at=2` on its note Tag — and not a second one
# for work it simply has not done yet.
_UNMIGRATED = frozenset({"harmonograph.py"})


def test_every_showcase_enters_through_the_harness() -> None:
    """No showcase calls run_cli directly.

    This is the enumerable-property form of the tier boundary: a showcase's
    entry point is scaffolding, so it is shared. (A *pattern* demo's run_cli
    call is its lesson — hence this rule stops at showcase/.)
    """
    offenders = [
        p.name
        for p in _showcase_sources()
        if p.name not in _UNMIGRATED
        and any(
            isinstance(node, ast.Call) and getattr(node.func, "id", None) == "run_cli"
            for node in ast.walk(ast.parse(p.read_text(encoding="utf-8")))
        )
    ]
    assert not offenders, f"showcases must enter through showcase_main: {offenders}"


def test_the_allowlist_sheds_names_that_adopted() -> None:
    """A shrink-only allowlist that keeps names past their reason stops ratcheting.

    Scoped to exactly what it checks: a listed file that HAS adopted must leave
    the list. It deliberately does not check that every listed name exists —
    harmonograph is pre-listed from another branch, so absence is expected and
    is not evidence of anything.
    """
    for name in _UNMIGRATED:
        path = _SHOWCASE / name
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        assert "showcase_main" not in source, (
            f"{name} adopted the harness; drop it from _UNMIGRATED"
        )


def test_no_showcase_declares_an_argument_twice() -> None:
    """The duplication the harness dissolved cannot come back by hand."""
    offenders = []
    for path in _showcase_sources():
        if path.name in _UNMIGRATED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "add_argument":
                offenders.append(f"{path.name} hand-rolls a pre-parser")
    assert not offenders, "; ".join(offenders)


def test_a_stats_facet_is_always_implied_at_full_depth() -> None:
    """Shared *shape*, not shared content — so a ratchet, not a shared object.

    Three showcases declare `stats`, each with its own help text (march
    internals, trace internals, raster occupancy). The words are the demo's;
    the rung is the tier's, and `-vv` is it. Contrast NOTE_TAG, where the
    content is shared too and so the Tag itself is the single source.
    """
    offenders = []
    for path in _showcase_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Tag"):
                continue
            named = [node.args[0]] if node.args else []
            named += [kw.value for kw in node.keywords if kw.arg == "name"]
            if not any(isinstance(n, ast.Constant) and n.value == "stats" for n in named):
                continue
            implied = next((kw.value for kw in node.keywords if kw.arg == "implied_at"), None)
            if not (isinstance(implied, ast.Constant) and implied.value == 3):
                offenders.append(f"{path.name} declares stats outside -vv")
    assert not offenders, "; ".join(offenders)
