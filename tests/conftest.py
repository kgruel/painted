"""Root test configuration — suite-wide flags and ambient-state isolation."""

import pytest

from painted.theme import reset_theme


def pytest_addoption(parser):
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Regenerate golden files instead of comparing against them",
    )
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
    resets the three ContextVars as a unit, so this fixture automatically tracks
    any future ambient concern wired into a Theme. Promoted here from the
    per-directory fixtures it replaces (property + golden) so isolation is a
    property of the whole suite, not something each test directory remembers.
    """
    reset_theme()
    yield
    reset_theme()
