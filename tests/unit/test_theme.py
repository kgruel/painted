"""Theme — the ambient-aesthetic reset/override contract.

`reset_theme()` is what the suite-wide `_reset_ambient_state` fixture (root
`tests/conftest.py`) calls to keep tests order-independent. That makes its
*completeness* load-bearing: if it stopped resetting one of the four ambient
ContextVars, ambient state would leak between tests again.

The adversarial review of that fixture found the gap it closed — borders, which
the old per-directory golden fixture never reset — was guarded by no test. These
tests close that: `reset_theme()` must restore all four (palette, icons, borders,
AND role overrides), order-independently. We assert the property directly rather
than via a leaky cross-test canary, so the guard does not depend on test
execution order.
"""

from __future__ import annotations

import pytest

from painted import (
    ASCII_ICONS,
    DEFAULT_PALETTE,
    DEFAULT_THEME,
    HEAVY,
    MONO_PALETTE,
    MONO_THEME,
    NORD_PALETTE,
    NORD_THEME,
    PAINTED_PALETTE,
    PAINTED_THEME,
    ROUNDED,
    Style,
    Theme,
    current_borders,
    current_icons,
    current_palette,
    reset_theme,
    use_borders,
    use_icons,
    use_palette,
    use_theme,
)

# The role-override channel is public-named but unexported (design doc D4); the
# public path to it is Theme(roles=...). Tests reach the seam directly.
from painted.vocabulary import current_role_overrides, use_role_overrides


def test_reset_theme_restores_all_four_ambient_contextvars() -> None:
    """reset_theme() restores palette, icons, borders, AND role overrides.

    The autouse fixture guarantees we start at defaults, so capture them, push
    all four off-default, and assert reset_theme() brings every one back.
    """
    default_palette = current_palette()
    default_icons = current_icons()
    default_borders = current_borders()

    use_palette(MONO_PALETTE)
    use_icons(ASCII_ICONS)
    use_borders(HEAVY)
    use_role_overrides({"stale": Style(fg="red")})
    # Sanity: all four really moved off their defaults (else the test is vacuous).
    assert current_palette() is MONO_PALETTE
    assert current_icons() is ASCII_ICONS
    assert current_borders() is HEAVY
    assert current_role_overrides() == {"stale": Style(fg="red")}

    reset_theme()

    assert current_palette() == default_palette
    assert current_icons() == default_icons
    assert current_borders() == default_borders
    # Borders specifically — the gap the suite-wide reset closed. If a future
    # edit drops reset_borders() from reset_theme(), this line goes red.
    assert current_borders() is ROUNDED
    # Role overrides — the fourth channel. If a future edit drops
    # reset_role_overrides() from reset_theme(), this line goes red.
    assert current_role_overrides() == {}


def test_use_theme_scoped_restores_all_four_on_exit() -> None:
    """`with use_theme(...)` applies all four aesthetics and restores on exit.

    The role-override channel restores to the *prior* value, not to empty: a
    scoped theme must not wipe an override that was in place before the block.
    """
    assert current_borders() is ROUNDED  # fixture default

    # A role override already in place before the scoped theme.
    use_role_overrides({"stale": Style(fg="blue")})
    assert current_role_overrides() == {"stale": Style(fg="blue")}

    themed = Theme(borders=HEAVY, roles={"stale": Style(fg="red")})
    with use_theme(themed):
        assert current_palette() == themed.palette
        assert current_icons() == themed.icons
        assert current_borders() == themed.borders
        assert current_borders() is not ROUNDED  # themed sets custom borders
        assert current_role_overrides() == {"stale": Style(fg="red")}

    # All four restored after the block — role overrides to their PRIOR value.
    assert current_palette() == DEFAULT_PALETTE
    assert current_borders() is ROUNDED
    assert current_role_overrides() == {"stale": Style(fg="blue")}


def test_theme_is_unhashable_but_value_equal() -> None:
    """Reviewed decision: the `roles` MappingProxyType makes Theme un-hashable,
    while value-equality still holds and a retained `roles=` dict cannot mutate
    the Theme after construction (see Theme's docstring / __post_init__)."""
    assert Theme() == Theme()

    with pytest.raises(TypeError):
        hash(Theme())

    passed = {"stale": Style(fg="red")}
    theme = Theme(roles=passed)
    passed["stale"] = Style(fg="green")  # mutate the caller-owned dict after the fact
    assert theme.roles == {"stale": Style(fg="red")}  # Theme is unaffected


def test_themes_reference_palette_presets_not_inline_copies() -> None:
    """Themes COMPOSE palette presets; they never redefine colors inline.

    Inline palette copies in theme.py would silently desync from palette.py
    (notably the `series` ramp), so each preset theme must hold the *same object*
    as its palette preset. Pin identity so a regression to inline definitions —
    the exact drift vector this dedup removed — goes red.
    """
    assert DEFAULT_THEME.palette is DEFAULT_PALETTE
    assert NORD_THEME.palette is NORD_PALETTE
    assert MONO_THEME.palette is MONO_PALETTE
    assert PAINTED_THEME.palette is PAINTED_PALETTE
