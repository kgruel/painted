"""Palette: semantic Style roles with ContextVar delivery."""

from __future__ import annotations

import pytest

from painted.core.cell import Style
from painted.palette import (
    DEFAULT_PALETTE,
    MONO_PALETTE,
    NORD_PALETTE,
    PAINTED_PALETTE,
    Palette,
    current_palette,
    reset_palette,
    use_palette,
)


def test_palette_is_frozen():
    p = Palette()
    with pytest.raises(AttributeError):
        p.accent = Style()  # type: ignore[misc]


def test_default_palette_roles_are_styles():
    p = DEFAULT_PALETTE
    for role in ("success", "warning", "error", "accent", "muted"):
        assert isinstance(getattr(p, role), Style)


def test_mono_palette_has_no_colors():
    """MONO_PALETTE uses modifiers only — no fg/bg."""
    p = MONO_PALETTE
    for role in ("success", "warning", "error", "accent", "muted"):
        s = getattr(p, role)
        assert s.fg is None, f"MONO_PALETTE.{role} should not set fg"
        assert s.bg is None, f"MONO_PALETTE.{role} should not set bg"


def test_mono_palette_roles_differ():
    """Each MONO_PALETTE role must be visually distinguishable."""
    p = MONO_PALETTE
    styles = {getattr(p, r) for r in ("success", "warning", "error", "accent", "muted")}
    # At least 4 distinct styles (muted=dim may overlap if another uses dim alone)
    assert len(styles) >= 4


def test_context_var_default():
    reset_palette()
    assert current_palette() is DEFAULT_PALETTE


def test_use_palette_sets_context():
    reset_palette()
    use_palette(MONO_PALETTE)
    assert current_palette() is MONO_PALETTE
    reset_palette()


def test_use_palette_context_manager_restores_previous():
    reset_palette()
    use_palette(NORD_PALETTE)

    with use_palette(MONO_PALETTE):
        assert current_palette() is MONO_PALETTE

    assert current_palette() is NORD_PALETTE
    reset_palette()


def test_reset_palette_restores_default():
    use_palette(MONO_PALETTE)
    reset_palette()
    assert current_palette() is DEFAULT_PALETTE


def test_palette_compose_with_merge():
    """Views compose palette roles with structural emphasis via Style.merge."""
    p = DEFAULT_PALETTE
    composed = p.accent.merge(Style(bold=True))
    assert composed.fg == p.accent.fg
    assert composed.bold is True


# --- series: the categorical ramp -------------------------------------------


def test_default_series_reproduces_legacy_flame_cycle():
    """DEFAULT.series is the warm (red, yellow, green, cyan) cycle.

    This ORDER is load-bearing: it reproduces the original flame output, which
    derived colors from roles in error/warning/success/accent order. Do not
    "tidy" it to match the role *declaration* order — that would silently change
    every DEFAULT flame render. Parity to the pre-`series` behavior depends on
    this tuple being byte-for-byte the old derived cycle.
    """
    assert DEFAULT_PALETTE.series == (
        Style(fg="red"),
        Style(fg="yellow"),
        Style(fg="green"),
        Style(fg="cyan"),
    )


def test_nord_series_carries_nord_hues():
    """NORD's ramp holds the Nord 256-color indices as ints, not the warm cycle.

    Ints (108/110/174/179) match how NORD's *roles* store fg, so flame routes
    them through the writer's 256-color path. (The pre-`series` code stringified
    role fg; a non-named/non-hex string renders as *no* color, so old NORD flame
    was effectively colorless. This carries real Nord hues — a fix, not parity.)
    """
    assert [s.fg for s in NORD_PALETTE.series] == [174, 179, 108, 110]


def test_mono_series_has_no_colors():
    """Honest monochrome: the ramp differentiates by modifier, never hue."""
    for s in MONO_PALETTE.series:
        assert s.fg is None
        assert s.bg is None
    # Ramp entries must be visually distinguishable from one another.
    assert len(set(MONO_PALETTE.series)) >= 3


def test_painted_palette_is_vivid_hex():
    """PAINTED_PALETTE roles and ramp are truecolor hex strings."""
    for role in ("success", "warning", "error", "accent", "muted"):
        fg = getattr(PAINTED_PALETTE, role).fg
        assert isinstance(fg, str) and fg.startswith("#")
    assert len(PAINTED_PALETTE.series) >= 5
    for s in PAINTED_PALETTE.series:
        assert isinstance(s.fg, str) and s.fg.startswith("#")
