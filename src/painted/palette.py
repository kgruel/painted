"""Palette: ambient color policy — semantic roles + a categorical ramp.

Five semantic roles (meaning -> style) plus ``series``, a categorical
ramp (position -> style) for visually separating N peers. Both are Styles
(not Colors) so monochrome palettes differentiate with modifiers.

Usage:
    from painted.palette import current_palette, use_palette, MONO_PALETTE

    p = current_palette()
    fill_style = p.accent.merge(Style(bold=True))

    # Override ambient palette (setter)
    use_palette(MONO_PALETTE)

    # Scoped override (context manager)
    with use_palette(MONO_PALETTE):
        ...
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from contextlib import AbstractContextManager
from dataclasses import dataclass, field

from .core.cell import Style


@dataclass(frozen=True)
class Palette:
    """Ambient color policy: semantic roles plus a categorical ramp.

    Two distinct color concepts, both delivered as Styles (not Colors) so
    monochrome palettes can differentiate with modifiers (bold, underline,
    dim) instead of hue:

    * **Semantic roles** (``success``/``warning``/``error``/``accent``/
      ``muted``) map *meaning* to style — "what does this value signify?"
    * **``series``** is a *categorical* (qualitative) ramp — distinct,
      "just-different" styles indexed by *position*, with no inherent
      meaning — "make these N peers visually separable."

    The two are independent: a palette's ``series`` need not relate to its
    roles. (That DEFAULT's first four happen to echo the role hues is a
    historical coincidence — it reproduces the original flame cycle — not a
    coupling.) The label->index assignment that consumes ``series`` lives in
    ``flame_lens`` today; it is the general form a reusable ramp helper would
    factor out, once a second consumer exists.
    """

    success: Style = field(default_factory=lambda: Style(fg="green"))
    warning: Style = field(default_factory=lambda: Style(fg="yellow"))
    error: Style = field(default_factory=lambda: Style(fg="red"))
    accent: Style = field(default_factory=lambda: Style(fg="cyan"))
    muted: Style = field(default_factory=lambda: Style(dim=True))
    # Substrate ownership: the default style for otherwise-unstyled content.
    # ``text`` supplies a foreground (and any attributes) wherever a cell's
    # ``Style`` leaves ``fg`` unset; ``surface`` supplies a background wherever
    # ``bg`` is unset. Both default to ``None`` — the terminal's own fg/bg, i.e.
    # today's behavior byte-for-byte. An explicit ``fg``/``bg`` on the cell always
    # wins. This lets a Theme own "body text" (and optionally a base canvas)
    # rather than coloring only the five roles. See ``resolve_against`` and the
    # writer's emission boundary. (Roles are *meaning*; ``text``/``surface`` are
    # the *substrate* those roles sit on.)
    text: Style | None = None
    surface: Style | None = None
    series: tuple[Style, ...] = field(
        default_factory=lambda: (
            Style(fg="red"),
            Style(fg="yellow"),
            Style(fg="green"),
            Style(fg="cyan"),
        )
    )

    def resolve_style(self, style: Style) -> Style:
        """Resolve a cell ``Style`` against this palette's substrate defaults.

        ``text`` is layered *under* the cell style (so the cell's explicit
        ``fg``/attributes win) and ``surface`` supplies the base ``bg``. When
        both are ``None`` the input is returned unchanged — identity, so output
        is byte-identical to a palette without a substrate. This is the single
        point where the ambient palette reaches the SGR-emission boundary; the
        writer's ``Style → SGR`` conversion stays pure.
        """
        base: Style | None = self.text
        if self.surface is not None:
            base = self.surface if base is None else base.merge(self.surface)
        if base is None:
            return style
        return base.merge(style)


# --- Presets ---

DEFAULT_PALETTE = Palette()

NORD_PALETTE = Palette(
    success=Style(fg=108),
    warning=Style(fg=179),
    error=Style(fg=174),
    accent=Style(fg=110),
    muted=Style(fg=60),
    # Nord-hued categorical ramp (error/warning/success/accent order) — keeps
    # flame segments in the Nord palette rather than the default warm cycle.
    series=(Style(fg=174), Style(fg=179), Style(fg=108), Style(fg=110)),
)

MONO_PALETTE = Palette(
    success=Style(bold=True),
    warning=Style(underline=True),
    error=Style(bold=True, reverse=True),
    accent=Style(bold=True),
    muted=Style(dim=True),
    # Honest monochrome: categorical separation via modifiers, never hue. Flame
    # segments already carry reverse=True, so these layer on top of it (reverse
    # itself is omitted — double-reverse is a no-op). All four carry an explicit
    # attribute (dim/bold are intensity opposites) so no pair collapses to a bare
    # reversed cell on terminals where bold-on-reverse reads like plain.
    series=(
        Style(dim=True),
        Style(bold=True),
        Style(underline=True),
        Style(italic=True),
    ),
)

# The painted display palette: vivid, truecolor-first hues for the docs site and
# any truecolor terminal. The honest default (DEFAULT_PALETTE — named colors that
# downsample to what a real terminal shows) stays the default; this is the opt-in
# / live-toggle vivid skin. The hex VALUES are tunable; the NAME is the contract.
PAINTED_PALETTE = Palette(
    success=Style(fg="#4fdc82"),
    warning=Style(fg="#f5cf52"),
    error=Style(fg="#ff5b6a"),
    accent=Style(fg="#44e0e0"),
    muted=Style(fg="#79808f"),
    # Categorical ramp: the four role hues, then three more to extend the cycle.
    series=(
        Style(fg="#4fdc82"),  # green
        Style(fg="#f5cf52"),  # yellow
        Style(fg="#ff5b6a"),  # red
        Style(fg="#44e0e0"),  # cyan
        Style(fg="#5aa7ff"),  # blue
        Style(fg="#ff74c8"),  # magenta
        Style(fg="#ff9d4d"),  # orange
    ),
)

# --- ContextVar delivery ---

_palette: ContextVar[Palette] = ContextVar("palette", default=DEFAULT_PALETTE)


class _PaletteOverride(AbstractContextManager[None]):
    def __init__(self, token: Token[Palette]) -> None:
        self._token = token
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            _palette.reset(self._token)
            self._active = False
        return False


def current_palette() -> Palette:
    """Get the ambient palette."""

    return _palette.get()


def use_palette(palette: Palette) -> AbstractContextManager[None]:
    """Set the ambient palette for the current context.

    The palette is set immediately (setter semantics) and the return value can be
    used as a context manager for scoped overrides:

        use_palette(MONO_PALETTE)  # global / ambient until changed again

        with use_palette(MONO_PALETTE):
            ...  # restored on exit
    """

    token = _palette.set(palette)
    return _PaletteOverride(token)


def reset_palette() -> None:
    """Reset to the default palette."""

    _palette.set(DEFAULT_PALETTE)
