"""Primitives: Style, Cell, and EMPTY_CELL."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ContractError

# Color can be:
#   - Named string: "red", "green", "blue", etc.
#   - 256-color int: 0-255
#   - Hex RGB string: "#ff0000"
Color = str | int | None

NAMED_COLORS = {
    "black": 0,
    "red": 1,
    "green": 2,
    "yellow": 3,
    "blue": 4,
    "magenta": 5,
    "cyan": 6,
    "white": 7,
}


@dataclass(frozen=True, slots=True)
class Style:
    """Immutable text style with color and attribute flags."""

    fg: Color = None
    bg: Color = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    reverse: bool = False
    dim: bool = False

    def merge(self, other: Style) -> Style:
        """Combine styles. `other` overrides non-None/non-False fields."""
        key = (self, other)
        cached = _merge_cache.get(key)
        if cached is not None:
            return cached
        result = Style(
            fg=other.fg if other.fg is not None else self.fg,
            bg=other.bg if other.bg is not None else self.bg,
            bold=other.bold or self.bold,
            italic=other.italic or self.italic,
            underline=other.underline or self.underline,
            reverse=other.reverse or self.reverse,
            dim=other.dim or self.dim,
        )
        if len(_merge_cache) < 1024:
            _merge_cache[key] = result
        return result


_merge_cache: dict[tuple[Style, Style], Style] = {}


def scrub_control(text: str) -> str:
    """Replace C0/C1 control characters with a space, leaving all else intact.

    The neutralization :class:`Cell` applies, factored to a string so text paths
    that emit strings *without* building Cells — the LINE prompt writer, which
    concatenates ``Span.text`` straight to stderr — share the exact same rule
    rather than reimplementing (and drifting from) it. Single source of truth:
    ``Cell.__post_init__`` calls this too.

    A control char in a display cell is emitted verbatim by the writer and
    corrupts the grid: a TAB expands at the terminal (breaking the width
    contract), and a raw ESC issues cursor/erase sequences out from under the
    diff renderer. The C0/C1 ranges (U+0000–U+001F, U+007F–U+009F) ARE exactly
    Unicode category Cc, so an ordinal test — no ``unicodedata`` import — lets
    zero-width joiners (Cf, emoji glue), private-use icon glyphs (Co), box-
    drawing, and combining marks pass through. Width stays stable: a control char
    already measures as one column, as does the replacement space. Mirrors
    render_big's \t\n\r→space, generalized.
    """
    return "".join(" " if (o := ord(c)) < 0x20 or 0x7F <= o <= 0x9F else c for c in text)


@dataclass(frozen=True, slots=True)
class Cell:
    """Atomic display unit: a single character with style."""

    char: str
    style: Style

    def __post_init__(self):
        if len(self.char) != 1:
            raise ContractError(f"Cell char must be a single character, got {self.char!r}")
        scrubbed = scrub_control(self.char)
        if scrubbed != self.char:
            object.__setattr__(self, "char", scrubbed)


EMPTY_CELL = Cell(" ", Style())
