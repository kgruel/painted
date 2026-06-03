"""Theme — the ambient-aesthetic reset/override contract.

`reset_theme()` is what the suite-wide `_reset_ambient_state` fixture (root
`tests/conftest.py`) calls to keep tests order-independent. That makes its
*completeness* load-bearing: if it stopped resetting one of the three ambient
ContextVars, ambient state would leak between tests again.

The adversarial review of that fixture found the gap it closed — borders, which
the old per-directory golden fixture never reset — was guarded by no test. These
tests close that: `reset_theme()` must restore all three (palette, icons, AND
borders), order-independently. We assert the property directly rather than via a
leaky cross-test canary, so the guard does not depend on test execution order.
"""

from __future__ import annotations

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
    current_borders,
    current_icons,
    current_palette,
    reset_theme,
    use_borders,
    use_icons,
    use_palette,
    use_theme,
)


def test_reset_theme_restores_all_three_ambient_contextvars() -> None:
    """reset_theme() restores palette, icons, AND borders to their defaults.

    The autouse fixture guarantees we start at defaults, so capture them, push
    all three off-default, and assert reset_theme() brings every one back.
    """
    default_palette = current_palette()
    default_icons = current_icons()
    default_borders = current_borders()

    use_palette(MONO_PALETTE)
    use_icons(ASCII_ICONS)
    use_borders(HEAVY)
    # Sanity: all three really moved off their defaults (else the test is vacuous).
    assert current_palette() is MONO_PALETTE
    assert current_icons() is ASCII_ICONS
    assert current_borders() is HEAVY

    reset_theme()

    assert current_palette() == default_palette
    assert current_icons() == default_icons
    assert current_borders() == default_borders
    # Borders specifically — the gap the suite-wide reset closed. If a future
    # edit drops reset_borders() from reset_theme(), this line goes red.
    assert current_borders() is ROUNDED


def test_use_theme_scoped_restores_all_three_on_exit() -> None:
    """`with use_theme(...)` applies all three aesthetics and restores on exit."""
    assert current_borders() is ROUNDED  # fixture default

    with use_theme(MONO_THEME):
        assert current_palette() == MONO_THEME.palette
        assert current_icons() == MONO_THEME.icons
        assert current_borders() == MONO_THEME.borders
        assert current_borders() is not ROUNDED  # MONO_THEME sets custom borders

    # All three restored after the block.
    assert current_palette() == DEFAULT_PALETTE
    assert current_borders() is ROUNDED


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
