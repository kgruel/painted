"""painted's exception hierarchy — see docs/ERRORS_DESIGN.md.

One root, three leaves. Each leaf also inherits the stdlib type it replaces
(``ValueError``/``RuntimeError``), the same dual-inheritance pattern as
``json.JSONDecodeError(ValueError)``: every existing ``except ValueError`` and
``pytest.raises(ValueError)`` keeps working, so naming these faults is
semver-MINOR, not a break. The class an app catches encodes *when the fault
fires and what the fix is*; the message text is not the contract.

This module lives at the bottom of the import graph (zero imports beyond
stdlib — it needs none) because both the renderer and the CLI framework raise
these, and ``cli`` may import from ``core`` but never the reverse.
"""

from __future__ import annotations


class PaintedError(Exception):
    """Root of every fault painted itself detects.

    Never raised directly — it exists so a consumer can write ``except
    PaintedError`` and mean "any painted fault", letting non-painted bugs
    surface instead of being swallowed. Carries no fields in v1; structure can
    be added additively later if a consumer demonstrates the need.
    """


class DeclarationError(PaintedError, ValueError):
    """A malformed declaration, caught at construction/registration time.

    Fires before any rendering happens — parser construction, runner
    ``__post_init__``, command registration — so an app that starts cleanly
    never sees one at runtime. Behavioral contract: *fix your code*.
    Production code must not catch it; tests assert it.
    """


class ContractError(PaintedError, ValueError):
    """An API contract violated at call time by a bad value.

    A value passed to a render-path function that the contract rules out — a
    two-character ``Cell.char``, a ``Block`` row wider than its declared width,
    an unknown wrap mode. Behavioral contract: *usually fix your code*, but an
    app feeding semi-trusted data into a render path may legitimately catch it
    and fall back.
    """


class LifecycleError(PaintedError, RuntimeError):
    """The right call in the wrong state.

    An ``InPlaceRenderer.render()`` outside its context manager, say.
    Behavioral contract: fix the call *sequence*, not the value.
    """
