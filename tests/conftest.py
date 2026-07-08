"""Root test configuration — suite-wide flags and ambient-state isolation."""

import os

import pytest

from painted.refs import reset_refs
from painted.theme import reset_theme
from painted.vocabulary import reset_vocabularies


def pytest_addoption(parser):
    parser.addoption(
        "--update-appearance",
        action="store_true",
        default=False,
        help="Regenerate appearance snapshots (structured char+style) instead of comparing",
    )


@pytest.fixture(autouse=True)
def _reset_ambient_state():
    """Pin all ambient aesthetics to defaults around every test, suite-wide.

    painted's identity is immutability, but palette/icons/borders are its
    deliberately process-global *aesthetic* state — three module-level ContextVars
    (`palette`, `icons`, `borders`). A test that sets one and forgets to restore
    it would leak into whatever test runs next in the same interpreter, making
    the suite order-dependent. (Other process-global caches exist — e.g. the
    env-size cache — but they are self-invalidating, not order-leak vectors.)

    `reset_theme()` is the canonical "reset all ambient aesthetics" call — it
    resets the three ContextVars (plus the role-override channel) as a unit, so
    this fixture automatically tracks any future ambient concern wired into a
    Theme. `reset_vocabularies()` clears the declared-vocabulary app layer, which
    is ambient ContextVar state but not part of a Theme (a mark classifies data;
    it is not aesthetic). `reset_refs()` clears the declared ref-scheme registry —
    the same shape of leak vector, single-layer like `palette` rather than
    two-layer like `vocabularies` (there is no built-in ref scheme). All three are
    promoted here from the per-directory fixtures they replace so isolation is a
    property of the whole suite, not something each test directory remembers.

    `NO_COLOR` is scrubbed too: the writer resolves it *ambiently* at construction
    (`core/writer.py`), so a caller who runs the suite under `NO_COLOR=1` (or a
    test that leaks it) would silently strip fg/bg from every colour assertion.
    Deleting it makes the suite hermetic to the ambient environment — tests that
    genuinely exercise NO_COLOR set it explicitly via `monkeypatch.setenv`, which
    is applied after this fixture and torn down before it, so they are unaffected.
    """
    os.environ.pop("NO_COLOR", None)
    reset_theme()
    reset_vocabularies()
    reset_refs()
    yield
    os.environ.pop("NO_COLOR", None)
    reset_theme()
    reset_vocabularies()
    reset_refs()
