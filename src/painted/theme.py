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

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import MappingProxyType

from .core.borders import BorderChars, ROUNDED, use_borders, reset_borders
from .core.cell import Style
from .icon_set import IconSet, use_icons, reset_icons
from .palette import (
    Palette,
    DEFAULT_PALETTE,
    NORD_PALETTE,
    MONO_PALETTE,
    PAINTED_PALETTE,
    use_palette,
    reset_palette,
)
from .vocabulary import use_role_overrides, reset_role_overrides


@dataclass(frozen=True)
class Theme:
    """Bundled aesthetic configuration.

    Composes the ambient aesthetic concerns — color semantics (Palette), glyph
    vocabulary (IconSet), box chrome (BorderChars), and role overrides — into a
    single frozen value that can be applied or scoped as a unit.

    ``roles`` overrides the style of any role by name — a core role
    (``"accent"``) or an app role declared by a vocabulary (``"stale"``). This is
    the public path to re-tinting a declared vocabulary's roles: an app role
    themes exactly like a core role. An override beats the role's declared style
    at ``mark_style`` time.

    Role overrides are **forward-tolerant by design**: an override for a role
    nothing currently binds is inert, not an error. A theme applies independent
    of declaration order (``use_theme`` before ``use_vocabularies`` must work)
    and may carry overrides for vocabularies an app declares later — the
    override activates the moment the role is bound. The cost of that tolerance
    is that a misspelled override name is silently inert; role *names* are
    still validated where roles are declared (``Role``/``Vocabulary``).

    The ``roles`` mapping makes ``Theme`` **un-hashable** by design (it is stored
    as a ``MappingProxyType``, which is not hashable). ``Theme`` value-equality
    still holds; hashability was incidental and no consumer relied on it.
    """

    palette: Palette = field(default_factory=Palette)
    icons: IconSet = field(default_factory=IconSet)
    borders: BorderChars = field(default_factory=lambda: ROUNDED)
    roles: Mapping[str, Style] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Coerce the caller-owned mapping to an immutable proxy so this frozen
        # value cannot be mutated through a retained reference — mutating the dict
        # passed as ``roles=`` after construction must not change the Theme. (The
        # proxy is not hashable, unlike IconSet's tuple coercion; that trade-off
        # is a reviewed decision — see the class docstring.)
        object.__setattr__(self, "roles", MappingProxyType(dict(self.roles)))


# --- Presets ---
# Themes COMPOSE palette presets; they never redefine palette colors inline.
# An inline copy would silently desync from palette.py (e.g. the `series` ramp),
# so the palette module stays the single source of truth.

DEFAULT_THEME = Theme(palette=DEFAULT_PALETTE)

NORD_THEME = Theme(palette=NORD_PALETTE)

MONO_THEME = Theme(
    palette=MONO_PALETTE,
    borders=BorderChars("+", "+", "+", "+", "-", "|", "+"),
)

PAINTED_THEME = Theme(palette=PAINTED_PALETTE)


# --- ContextVar delivery ---
# Theme itself has no ContextVar — it composes the three existing ones.
# use_theme() sets all three atomically; the context manager restores all three.


class _ThemeOverride(AbstractContextManager[None]):
    def __init__(
        self,
        palette_cm: AbstractContextManager[None],
        icons_cm: AbstractContextManager[None],
        borders_cm: AbstractContextManager[None],
        roles_cm: AbstractContextManager[None],
    ) -> None:
        self._palette_cm = palette_cm
        self._icons_cm = icons_cm
        self._borders_cm = borders_cm
        self._roles_cm = roles_cm
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            # Restore in reverse of set order (atomic-restore discipline).
            self._roles_cm.__exit__(exc_type, exc, tb)
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
    roles_cm = use_role_overrides(theme.roles)
    return _ThemeOverride(palette_cm, icons_cm, borders_cm, roles_cm)


def reset_theme() -> None:
    """Reset all ambient aesthetics to defaults."""

    reset_palette()
    reset_icons()
    reset_borders()
    reset_role_overrides()
