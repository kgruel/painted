"""Border character sets for styled block composition.

Usage:
    from painted.core.borders import current_borders, use_borders, ROUNDED

    b = current_borders()
    separator = b.horizontal * width

    # Override ambient borders (setter)
    use_borders(HEAVY)

    # Scoped override (context manager)
    with use_borders(HEAVY):
        ...
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class BorderChars:
    top_left: str
    top_right: str
    bottom_left: str
    bottom_right: str
    horizontal: str
    vertical: str
    crossing: str


ROUNDED = BorderChars("╭", "╮", "╰", "╯", "─", "│", "┼")
HEAVY = BorderChars("┏", "┓", "┗", "┛", "━", "┃", "╋")
DOUBLE = BorderChars("╔", "╗", "╚", "╝", "═", "║", "╬")
LIGHT = BorderChars("┌", "┐", "└", "┘", "─", "│", "┼")
ASCII = BorderChars("+", "+", "+", "+", "-", "|", "+")


# --- ContextVar delivery ---

_borders: ContextVar[BorderChars] = ContextVar("borders", default=ROUNDED)


class _BordersOverride(AbstractContextManager[None]):
    def __init__(self, token: Token[BorderChars]) -> None:
        self._token = token
        self._active = True

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._active:
            _borders.reset(self._token)
            self._active = False
        return False


def current_borders() -> BorderChars:
    """Get the ambient border character set."""

    return _borders.get()


def use_borders(borders: BorderChars) -> AbstractContextManager[None]:
    """Set the ambient border character set for the current context.

    The border set is set immediately (setter semantics) and the return value
    can be used as a context manager for scoped overrides:

        use_borders(HEAVY)  # global / ambient until changed again

        with use_borders(HEAVY):
            ...  # restored on exit
    """

    token = _borders.set(borders)
    return _BordersOverride(token)


def reset_borders() -> None:
    """Reset to the default border character set (ROUNDED)."""

    _borders.set(ROUNDED)
