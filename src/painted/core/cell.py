"""Primitives: Style, Cell, and EMPTY_CELL."""

from __future__ import annotations

from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class Cell:
    """Atomic display unit: a single character with style."""

    char: str
    style: Style

    def __post_init__(self):
        if len(self.char) != 1:
            raise ValueError(f"Cell char must be a single character, got {self.char!r}")
        # Neutralize C0/C1 control characters to a space. A control char in a
        # display cell is emitted verbatim by the writer and corrupts the grid:
        # a TAB expands at the terminal (breaking the width contract), and a raw
        # ESC issues cursor/erase sequences out from under the diff renderer. The
        # C0/C1 ranges (U+0000–U+001F, U+007F–U+009F) ARE exactly Unicode
        # category Cc, so an ordinal test — no unicodedata import — lets zero-
        # width joiners (Cf, emoji glue), private-use icon glyphs (Co), box-
        # drawing, and combining marks pass through. Width stays stable: a
        # control char already measures as one column (char_width), as does the
        # replacement space. Mirrors render_big's \t\n\r→space, generalized.
        o = ord(self.char)
        if o < 0x20 or 0x7F <= o <= 0x9F:
            object.__setattr__(self, "char", " ")


EMPTY_CELL = Cell(" ", Style())
