"""Theme: bundled aesthetic configuration.

Composes Palette + IconSet + BorderChars into a single ambient unit.

Usage:
    from painted.theme import Theme, use_theme

    sleek = Theme(
        palette=Palette(accent=Style(fg=110, bold=True)),
        borders=HEAVY,
    )

    use_theme(sleek)          # set all three globally
    with use_theme(sleek):    # scoped override — all three restored on exit
        ...
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from .core.borders import BorderChars, ROUNDED, use_borders, reset_borders
from .core.cell import Style
from .icon_set import IconSet, use_icons, reset_icons
from .palette import Palette, use_palette, reset_palette


@dataclass(frozen=True)
class Theme:
    """Bundled aesthetic configuration.

    Composes the three ambient concerns — color semantics (Palette),
    glyph vocabulary (IconSet), and box chrome (BorderChars) — into a
    single frozen value that can be applied or scoped as a unit.
    """

    palette: Palette = field(default_factory=Palette)
    icons: IconSet = field(default_factory=IconSet)
    borders: BorderChars = field(default_factory=lambda: ROUNDED)


# --- Presets ---

DEFAULT_THEME = Theme()

NORD_THEME = Theme(
    palette=Palette(
        success=Style(fg=108),
        warning=Style(fg=179),
        error=Style(fg=174),
        accent=Style(fg=110),
        muted=Style(fg=60),
    ),
)

MONO_THEME = Theme(
    palette=Palette(
        success=Style(bold=True),
        warning=Style(underline=True),
        error=Style(bold=True, reverse=True),
        accent=Style(bold=True),
        muted=Style(dim=True),
    ),
    borders=BorderChars("+", "+", "+", "+", "-", "|", "+"),
)


# --- ContextVar delivery ---
# Theme itself has no ContextVar — it composes the three existing ones.
# use_theme() sets all three atomically; the context manager restores all three.


class _ThemeOverride(AbstractContextManager[None]):
    def __init__(
        self,
        palette_cm: AbstractContextManager[None],
        icons_cm: AbstractContextManager[None],
        borders_cm: AbstractContextManager[None],
    ) -> None:
        self._palette_cm = palette_cm
        self._icons_cm = icons_cm
        self._borders_cm = borders_cm
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            self._borders_cm.__exit__(exc_type, exc, tb)
            self._icons_cm.__exit__(exc_type, exc, tb)
            self._palette_cm.__exit__(exc_type, exc, tb)
            self._active = False
        return False


def use_theme(theme: Theme) -> AbstractContextManager[None]:
    """Set all ambient aesthetics from a Theme.

    The theme is applied immediately (setter semantics) and the return value
    can be used as a context manager for scoped overrides:

        use_theme(NORD_THEME)  # global / ambient until changed again

        with use_theme(NORD_THEME):
            ...  # all three restored on exit
    """

    palette_cm = use_palette(theme.palette)
    icons_cm = use_icons(theme.icons)
    borders_cm = use_borders(theme.borders)
    return _ThemeOverride(palette_cm, icons_cm, borders_cm)


def reset_theme() -> None:
    """Reset all ambient aesthetics to defaults."""

    reset_palette()
    reset_icons()
    reset_borders()
