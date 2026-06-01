"""Behavioral unit tests for the DeployApp in demos/patterns/testing.py.

Graduated from the demo-golden `test_demo_testing.py`, which snapshotted
stripped frame TEXT. These assert on the app's STATE and EMISSIONS instead:
the deploy emission protocol (`deploy.select`, `deploy.confirmed`) and the
confirm-modal push/pop lifecycle, replayed through TestSurface.

Emission kinds verified by reading demos/patterns/testing.py:
    - `deploy.select`  emitted in DeployApp.on_key on j/k at base depth
      (carries `service`, `index`).
    - `deploy.confirmed` emitted on a non-None pop result (carries `service`,
      the confirm layer's state, which is the selected service name).
The confirm-modal label "Deploy {svc}? (y/n)" comes from `_confirm_layer`.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Import the demo module without sys.path mutation (mirrors the old golden).
_PROJECT = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "_demo_testing",
    _PROJECT / "demos" / "patterns" / "testing.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

DeployApp = _mod.DeployApp
SERVICES = _mod.SERVICES

from painted.tui import TestSurface  # noqa: E402


def _run(keys: list[str]) -> TestSurface:
    app = DeployApp()
    harness = TestSurface(app, width=40, height=8, input_queue=keys)
    harness.run_to_completion()
    return harness


def _kinds(harness: TestSurface) -> list[str]:
    return [kind for kind, _ in harness.emissions]


def _emissions_of(harness: TestSurface, kind: str) -> list[dict]:
    return [data for k, data in harness.emissions if k == kind]


def test_confirming_emits_select_then_confirmed_with_chosen_service():
    # 'j' selects the second service (index 1), 'enter' opens confirm,
    # 'y' confirms the deploy, 'q' quits.
    harness = _run(["j", "enter", "y", "q"])
    kinds = _kinds(harness)

    assert "deploy.select" in kinds
    assert "deploy.confirmed" in kinds
    # select precedes confirmed.
    assert kinds.index("deploy.select") < kinds.index("deploy.confirmed")

    chosen = SERVICES[1]
    select = _emissions_of(harness, "deploy.select")
    assert select == [{"service": chosen, "index": 1}]

    confirmed = _emissions_of(harness, "deploy.confirmed")
    assert confirmed == [{"service": chosen}]


def test_declining_emits_select_but_not_confirmed():
    # 'n' on the confirm modal cancels: select fired, confirmed must not.
    harness = _run(["j", "enter", "n", "q"])
    kinds = _kinds(harness)

    assert "deploy.select" in kinds
    assert "deploy.confirmed" not in kinds

    assert _emissions_of(harness, "deploy.select") == [{"service": SERVICES[1], "index": 1}]


def test_enter_pushes_confirm_layer_then_pop_returns_to_base():
    app = DeployApp()
    layers = _mod._get_layers(app.state)
    assert len(layers) == 1
    assert layers[0].name == "base"

    # enter pushes the confirm layer on top of base.
    app.on_key("enter")
    layers = _mod._get_layers(app.state)
    assert len(layers) == 2
    assert layers[-1].name == "confirm"
    # Confirm layer carries the selected service as its state.
    assert layers[-1].state == SERVICES[0]

    # A decline ('n') pops back to the base layer.
    app.on_key("n")
    layers = _mod._get_layers(app.state)
    assert len(layers) == 1
    assert layers[0].name == "base"


def test_confirm_modal_label_is_shown_then_dismissed():
    # Structural frame facts: the modal prompt appears after 'enter' and the
    # final frame is back to the base service list (no modal prompt).
    app = DeployApp()
    harness = TestSurface(app, width=40, height=8, input_queue=["j", "enter", "y", "q"])
    frames = harness.run_to_completion()

    chosen = SERVICES[1]
    modal_label = f"Deploy {chosen}? (y/n)"

    # frames: [initial, after 'j', after 'enter', after 'y', after 'q']
    assert modal_label in frames[2].text
    # Final frame: modal dismissed, base list visible again.
    assert modal_label not in frames[-1].text
    assert SERVICES[0] in frames[-1].text


def test_quit_stops_the_run():
    app = DeployApp()
    harness = TestSurface(app, width=40, height=8, input_queue=["q"])
    harness.run_to_completion()
    assert app._running is False
