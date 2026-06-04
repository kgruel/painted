"""Big text rendering using block characters.

Two formats, and the FILLED one rests on a small dissolution:

A glyph is an 8×8 **bitmap**; rendering it is "pack that bitmap into terminal
cells at a chosen **density**". Density is how many sub-pixels each cell encodes,
spent through the Unicode block characters:

    FULL     (1×1)  one pixel per cell    space █                → 8×8 cells
    HALF     (1×2)  two stacked pixels    space ▀ ▄ █            → 8×4 cells
    QUADRANT (2×2)  four pixels per cell  the 16 quadrant blocks → 4×4 cells

The *same* glyph at a denser packing is smaller — so `size` is not a second font,
it is a density choice over one font. ``size=1`` → HALF (compact, the default),
``size=2`` → FULL (large). Both keep full cell width (8 wide per glyph); `size` is a
purely vertical dial — 4 cells tall vs 8. QUADRANT remains in the packer as a
capability (halving both axes to 4×4) but is no longer bound to a ``size``: its
1px strokes collapse to half-blocks, which read thin and muddy, so HALF — whose
vertical strokes stay full-cell-width — is the legible compact default. The glyphs
are the public-domain IBM PC 8×8 font (legibility-proven, complete).

OUTLINE is a *different model*: box-drawing strokes at **cell** resolution, not a
pixel fill — the box characters *are* the outline, one stroke per cell, so there
is no bitmap to pack. It keeps its own hand-encoded glyph tables and its own
(3-row / 5-row) sizes. FILLED and OUTLINE therefore have different natural
heights; they are two different lenses on "big text", not two packings of one grid.
"""

from __future__ import annotations

from enum import Enum

from ..core.block import Block
from ..core.cell import Cell, Style
from ..core.compose import join_horizontal


class BigTextFormat(Enum):
    """Rendering format for big text."""

    FILLED = "filled"  # Solid blocks, packed from the 8×8 bitmap font
    OUTLINE = "outline"  # Hollow box-drawing strokes at cell resolution


# --- FILLED: the 8×8 master font ----------------------------------------------
#
# Public-domain IBM PC BIOS 8×8 font (via Daniel Hepper's font8x8, itself the IBM
# VGA fonts — Public Domain). Each glyph is 8 bytes, one per pixel row; bit ``c``
# (value ``1 << c``) is column ``c``, LSB = leftmost pixel. Lowercase keys map to
# the UPPERCASE letterforms so block text reads as caps (the wordmark look);
# render_big lower-cases its input before lookup, so only these keys are hit.
_IBM_8X8: dict[str, tuple[int, ...]] = {
    "a": (0x0C, 0x1E, 0x33, 0x33, 0x3F, 0x33, 0x33, 0x00),
    "b": (0x3F, 0x66, 0x66, 0x3E, 0x66, 0x66, 0x3F, 0x00),
    "c": (0x3C, 0x66, 0x03, 0x03, 0x03, 0x66, 0x3C, 0x00),
    "d": (0x1F, 0x36, 0x66, 0x66, 0x66, 0x36, 0x1F, 0x00),
    "e": (0x7F, 0x46, 0x16, 0x1E, 0x16, 0x46, 0x7F, 0x00),
    "f": (0x7F, 0x46, 0x16, 0x1E, 0x16, 0x06, 0x0F, 0x00),
    "g": (0x3C, 0x66, 0x03, 0x03, 0x73, 0x66, 0x7C, 0x00),
    "h": (0x33, 0x33, 0x33, 0x3F, 0x33, 0x33, 0x33, 0x00),
    "i": (0x1E, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00),
    "j": (0x78, 0x30, 0x30, 0x30, 0x33, 0x33, 0x1E, 0x00),
    "k": (0x67, 0x66, 0x36, 0x1E, 0x36, 0x66, 0x67, 0x00),
    "l": (0x0F, 0x06, 0x06, 0x06, 0x46, 0x66, 0x7F, 0x00),
    "m": (0x63, 0x77, 0x7F, 0x7F, 0x6B, 0x63, 0x63, 0x00),
    "n": (0x63, 0x67, 0x6F, 0x7B, 0x73, 0x63, 0x63, 0x00),
    "o": (0x1C, 0x36, 0x63, 0x63, 0x63, 0x36, 0x1C, 0x00),
    "p": (0x3F, 0x66, 0x66, 0x3E, 0x06, 0x06, 0x0F, 0x00),
    "q": (0x1E, 0x33, 0x33, 0x33, 0x3B, 0x1E, 0x38, 0x00),
    "r": (0x3F, 0x66, 0x66, 0x3E, 0x36, 0x66, 0x67, 0x00),
    "s": (0x1E, 0x33, 0x07, 0x0E, 0x38, 0x33, 0x1E, 0x00),
    "t": (0x3F, 0x2D, 0x0C, 0x0C, 0x0C, 0x0C, 0x1E, 0x00),
    "u": (0x33, 0x33, 0x33, 0x33, 0x33, 0x33, 0x3F, 0x00),
    "v": (0x33, 0x33, 0x33, 0x33, 0x33, 0x1E, 0x0C, 0x00),
    "w": (0x63, 0x63, 0x63, 0x6B, 0x7F, 0x77, 0x63, 0x00),
    "x": (0x63, 0x63, 0x36, 0x1C, 0x1C, 0x36, 0x63, 0x00),
    "y": (0x33, 0x33, 0x33, 0x1E, 0x0C, 0x0C, 0x1E, 0x00),
    "z": (0x7F, 0x63, 0x31, 0x18, 0x4C, 0x66, 0x7F, 0x00),
    "0": (0x3E, 0x63, 0x73, 0x7B, 0x6F, 0x67, 0x3E, 0x00),
    "1": (0x0C, 0x0E, 0x0C, 0x0C, 0x0C, 0x0C, 0x3F, 0x00),
    "2": (0x1E, 0x33, 0x30, 0x1C, 0x06, 0x33, 0x3F, 0x00),
    "3": (0x1E, 0x33, 0x30, 0x1C, 0x30, 0x33, 0x1E, 0x00),
    "4": (0x38, 0x3C, 0x36, 0x33, 0x7F, 0x30, 0x78, 0x00),
    "5": (0x3F, 0x03, 0x1F, 0x30, 0x30, 0x33, 0x1E, 0x00),
    "6": (0x1C, 0x06, 0x03, 0x1F, 0x33, 0x33, 0x1E, 0x00),
    "7": (0x3F, 0x33, 0x30, 0x18, 0x0C, 0x0C, 0x0C, 0x00),
    "8": (0x1E, 0x33, 0x33, 0x1E, 0x33, 0x33, 0x1E, 0x00),
    "9": (0x1E, 0x33, 0x33, 0x3E, 0x30, 0x18, 0x0E, 0x00),
    " ": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    "!": (0x18, 0x3C, 0x3C, 0x18, 0x18, 0x00, 0x18, 0x00),
    '"': (0x36, 0x36, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    "#": (0x36, 0x36, 0x7F, 0x36, 0x7F, 0x36, 0x36, 0x00),
    "$": (0x0C, 0x3E, 0x03, 0x1E, 0x30, 0x1F, 0x0C, 0x00),
    "%": (0x00, 0x63, 0x33, 0x18, 0x0C, 0x66, 0x63, 0x00),
    "&": (0x1C, 0x36, 0x1C, 0x6E, 0x3B, 0x33, 0x6E, 0x00),
    "'": (0x06, 0x06, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00),
    "(": (0x18, 0x0C, 0x06, 0x06, 0x06, 0x0C, 0x18, 0x00),
    ")": (0x06, 0x0C, 0x18, 0x18, 0x18, 0x0C, 0x06, 0x00),
    "*": (0x00, 0x66, 0x3C, 0xFF, 0x3C, 0x66, 0x00, 0x00),
    "+": (0x00, 0x0C, 0x0C, 0x3F, 0x0C, 0x0C, 0x00, 0x00),
    ",": (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x06),
    "-": (0x00, 0x00, 0x00, 0x3F, 0x00, 0x00, 0x00, 0x00),
    ".": (0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x00),
    "/": (0x60, 0x30, 0x18, 0x0C, 0x06, 0x03, 0x01, 0x00),
    ":": (0x00, 0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x00),
    ";": (0x00, 0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x06),
    "<": (0x18, 0x0C, 0x06, 0x03, 0x06, 0x0C, 0x18, 0x00),
    "=": (0x00, 0x00, 0x3F, 0x00, 0x00, 0x3F, 0x00, 0x00),
    ">": (0x06, 0x0C, 0x18, 0x30, 0x18, 0x0C, 0x06, 0x00),
    "?": (0x1E, 0x33, 0x30, 0x18, 0x0C, 0x00, 0x0C, 0x00),
    "@": (0x3E, 0x63, 0x7B, 0x7B, 0x7B, 0x03, 0x1E, 0x00),
    "[": (0x1E, 0x06, 0x06, 0x06, 0x06, 0x06, 0x1E, 0x00),
    "\\": (0x03, 0x06, 0x0C, 0x18, 0x30, 0x60, 0x40, 0x00),
    "]": (0x1E, 0x18, 0x18, 0x18, 0x18, 0x18, 0x1E, 0x00),
    "^": (0x08, 0x1C, 0x36, 0x63, 0x00, 0x00, 0x00, 0x00),
    "_": (0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF),
    "`": (0x0C, 0x0C, 0x18, 0x00, 0x00, 0x00, 0x00, 0x00),
    "{": (0x38, 0x0C, 0x0C, 0x07, 0x0C, 0x0C, 0x38, 0x00),
    "|": (0x18, 0x18, 0x18, 0x00, 0x18, 0x18, 0x18, 0x00),
    "}": (0x07, 0x0C, 0x0C, 0x38, 0x0C, 0x0C, 0x07, 0x00),
    "~": (0x6E, 0x3B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00),
    # Fallback for unknown characters: a hollow box.
    "\x00": (0x7E, 0x42, 0x42, 0x42, 0x42, 0x42, 0x7E, 0x00),
}

# Public export: the master 8×8 bitmap font (8 bytes per glyph; bit c = column c,
# LSB = leftmost). Pack it at any density via render_big, or read it directly.
BIG_GLYPHS = _IBM_8X8


class _Density(Enum):
    """Sub-pixel packing density: ``(cols, rows)`` of pixels encoded per cell."""

    FULL = (1, 1)  # space █
    HALF = (1, 2)  # space ▀ ▄ █
    QUADRANT = (2, 2)  # the 16 quadrant blocks


# Sub-pixel patterns → block glyph, keyed by the lit pixels in row-major order
# (the same order _pack assembles them). FULL: (px,). HALF: (top, bottom).
# QUADRANT: (top-left, top-right, bottom-left, bottom-right).
_FULL_CHARS: dict[tuple[int, ...], str] = {(0,): " ", (1,): "█"}
_HALF_CHARS: dict[tuple[int, ...], str] = {
    (0, 0): " ",
    (1, 0): "▀",
    (0, 1): "▄",
    (1, 1): "█",
}
_QUAD_CHARS: dict[tuple[int, ...], str] = {
    (0, 0, 0, 0): " ",
    (1, 0, 0, 0): "▘",
    (0, 1, 0, 0): "▝",
    (0, 0, 1, 0): "▖",
    (0, 0, 0, 1): "▗",
    (1, 1, 0, 0): "▀",
    (0, 0, 1, 1): "▄",
    (1, 0, 1, 0): "▌",
    (0, 1, 0, 1): "▐",
    (1, 0, 0, 1): "▚",
    (0, 1, 1, 0): "▞",
    (1, 1, 1, 0): "▛",
    (1, 1, 0, 1): "▜",
    (1, 0, 1, 1): "▙",
    (0, 1, 1, 1): "▟",
    (1, 1, 1, 1): "█",
}
_DENSITY_CHARS: dict[_Density, dict[tuple[int, ...], str]] = {
    _Density.FULL: _FULL_CHARS,
    _Density.HALF: _HALF_CHARS,
    _Density.QUADRANT: _QUAD_CHARS,
}

# size → density. size=1 is HALF (the compact default); size=2 is the large
# full-pixel one. QUADRANT is no longer on the size ladder (it stays in the packer).
_SIZE_DENSITY: dict[int, _Density] = {1: _Density.HALF, 2: _Density.FULL}

# Cells between adjacent glyphs. The IBM font carries its own side-bearing (most
# letters leave their right column blank), so one cell of gap reads as a clean,
# even word space without crowding the bearing-less glyphs (M, W).
_GLYPH_GAP = 1


# --- OUTLINE: hand-encoded box-drawing glyphs (cell-resolution strokes) -------

# Size 1 OUTLINE: 3-row box-drawing letterforms. NOTE: a few glyphs embed literal
# ASCII (v, x, the `o`/`,` punctuation) rather than constructed strokes — a known
# rough edge in the OUTLINE set, independent of the FILLED path.
_GLYPHS_3ROW_OUTLINE: dict[str, tuple[str, str, str]] = {
    "a": ("┌─┐", "├─┤", "│ │"),
    "b": ("├─┐", "├─┤", "├─┘"),
    "c": ("┌─┐", "│  ", "└─┘"),
    "d": ("┌─┐", "│ │", "└─┘"),
    "e": ("┌─┐", "├─ ", "└─┘"),
    "f": ("┌─┐", "├─ ", "│  "),
    "g": ("┌─┐", "│ ─", "└─┘"),
    "h": ("│ │", "├─┤", "│ │"),
    "i": (" │ ", " │ ", " │ "),
    "j": ("  │", "  │", "└─┘"),
    "k": ("│ ╱", "├─ ", "│ ╲"),
    "l": ("│  ", "│  ", "└─┘"),
    "m": ("┌┬┐", "│││", "│ │"),
    "n": ("┌─┐", "│ │", "│ │"),
    "o": ("┌─┐", "│ │", "└─┘"),
    "p": ("┌─┐", "├─┘", "│  "),
    "q": ("┌─┐", "│ │", "└─┼"),
    "r": ("┌─┐", "├─┘", "│ ╲"),
    "s": ("┌─┐", "└─┐", "└─┘"),
    "t": ("───", " │ ", " │ "),
    "u": ("│ │", "│ │", "└─┘"),
    "v": ("│ │", "│ │", " v "),
    "w": ("│ │", "│┬│", "└┴┘"),
    "x": ("╲ ╱", " x ", "╱ ╲"),
    "y": ("│ │", " │ ", " │ "),
    "z": ("──┐", " ╱ ", "└──"),
    "0": ("┌─┐", "│ │", "└─┘"),
    "1": (" │ ", " │ ", " │ "),
    "2": ("──┐", "┌─┘", "└──"),
    "3": ("──┐", " ─┤", "──┘"),
    "4": ("│ │", "└─┤", "  │"),
    "5": ("┌──", "└─┐", "──┘"),
    "6": ("┌─┐", "├─┐", "└─┘"),
    "7": ("──┐", "  │", "  │"),
    "8": ("┌─┐", "├─┤", "└─┘"),
    "9": ("┌─┐", "└─┤", "──┘"),
    " ": ("   ", "   ", "   "),
    ".": ("   ", "   ", " o "),
    ",": ("   ", "   ", " , "),
    "!": (" │ ", " │ ", " o "),
    "?": ("──┐", " ┌┘", " o "),
    "-": ("   ", "───", "   "),
    ":": (" o ", "   ", " o "),
    ";": (" o ", "   ", " , "),
    "'": (" │ ", "   ", "   "),
    '"': ("│ │", "   ", "   "),
    "/": ("  ╱", " ╱ ", "╱  "),
    "\\": ("╲  ", " ╲ ", "  ╲"),
    "(": (" ╱ ", " │ ", " ╲ "),
    ")": (" ╲ ", " │ ", " ╱ "),
    "[": ("┌─ ", "│  ", "└─ "),
    "]": (" ─┐", "  │", " ─┘"),
    "{": (" ┌─", "─┤ ", " └─"),
    "}": ("─┐ ", " ├─", "─┘ "),
    "<": ("  ╱", " < ", "  ╲"),
    ">": ("╲  ", " > ", "╱  "),
    "#": ("┼─┼", "─┼─", "┼─┼"),
    "@": ("┌─┐", "│@│", "└──"),
    "*": ("╲│╱", "─┼─", "╱│╲"),
    "+": ("   ", "─┼─", "   "),
    "=": ("───", "   ", "───"),
    "_": ("   ", "   ", "───"),
    "&": ("┌─ ", "├─╱", "└─┘"),
    "%": ("o ╱", " ╱ ", "╱ o"),
    "$": ("┌┼─", " │ ", "─┼┘"),
    "^": (" ╱╲", "   ", "   "),
    "~": ("   ", "╱╲╱", "   "),
    "`": ("╲  ", "   ", "   "),
    "\x00": ("┌─┐", "│ │", "└─┘"),
}

# Size 2 OUTLINE: 5-row box-drawing letterforms.
_GLYPHS_5ROW_OUTLINE: dict[str, tuple[str, str, str, str, str]] = {
    "a": ("┌───┐", "│   │", "├───┤", "│   │", "│   │"),
    "b": ("├───┐", "│   │", "├───┤", "│   │", "├───┘"),
    "c": ("┌────", "│    ", "│    ", "│    ", "└────"),
    "d": ("├───┐", "│   │", "│   │", "│   │", "├───┘"),
    "e": ("┌────", "│    ", "├──  ", "│    ", "└────"),
    "f": ("┌────", "│    ", "├──  ", "│    ", "│    "),
    "g": ("┌────", "│    ", "│  ──", "│   │", "└───┘"),
    "h": ("│   │", "│   │", "├───┤", "│   │", "│   │"),
    "i": ("─────", "  │  ", "  │  ", "  │  ", "─────"),
    "j": ("  ───", "    │", "    │", "│   │", "└───┘"),
    "k": ("│   │", "│  ╱ ", "├─<  ", "│  ╲ ", "│   │"),
    "l": ("│    ", "│    ", "│    ", "│    ", "└────"),
    "m": ("│   │", "├─┬─┤", "│ │ │", "│   │", "│   │"),
    "n": ("│   │", "├─┐ │", "│ │ │", "│ └─┤", "│   │"),
    "o": ("┌───┐", "│   │", "│   │", "│   │", "└───┘"),
    "p": ("├───┐", "│   │", "├───┘", "│    ", "│    "),
    "q": ("┌───┐", "│   │", "│ │ │", "│  ╲ ", "└──╲│"),
    "r": ("├───┐", "│   │", "├───┘", "│  ╲ ", "│   │"),
    "s": ("┌────", "│    ", "└───┐", "    │", "────┘"),
    "t": ("─────", "  │  ", "  │  ", "  │  ", "  │  "),
    "u": ("│   │", "│   │", "│   │", "│   │", "└───┘"),
    "v": ("│   │", "│   │", "│   │", " ╲ ╱ ", "  v  "),
    "w": ("│   │", "│   │", "│ │ │", "│ │ │", "└─┴─┘"),
    "x": ("╲   ╱", " ╲ ╱ ", "  X  ", " ╱ ╲ ", "╱   ╲"),
    "y": ("│   │", " ╲ ╱ ", "  │  ", "  │  ", "  │  "),
    "z": ("─────", "   ╱ ", "  ╱  ", " ╱   ", "─────"),
    "0": ("┌───┐", "│   │", "│ │ │", "│   │", "└───┘"),
    "1": ("  │  ", " ─┤  ", "  │  ", "  │  ", "─────"),
    "2": ("┌───┐", "    │", "┌───┘", "│    ", "└────"),
    "3": ("────┐", "    │", " ───┤", "    │", "────┘"),
    "4": ("│   │", "│   │", "└───┤", "    │", "    │"),
    "5": ("┌────", "│    ", "└───┐", "    │", "────┘"),
    "6": ("┌───┐", "│    ", "├───┐", "│   │", "└───┘"),
    "7": ("─────", "    │", "   ╱ ", "  ╱  ", "  │  "),
    "8": ("┌───┐", "│   │", "├───┤", "│   │", "└───┘"),
    "9": ("┌───┐", "│   │", "└───┤", "    │", "────┘"),
    " ": ("     ", "     ", "     ", "     ", "     "),
    ".": ("     ", "     ", "     ", "  o  ", "     "),
    ",": ("     ", "     ", "     ", "  ,  ", "     "),
    "!": ("  │  ", "  │  ", "  │  ", "     ", "  o  "),
    "?": ("┌───┐", "    │", "  ┌─┘", "     ", "  o  "),
    "-": ("     ", "     ", "─────", "     ", "     "),
    ":": ("     ", "  o  ", "     ", "  o  ", "     "),
    "'": ("  │  ", "  │  ", "     ", "     ", "     "),
    '"': (" │ │ ", " │ │ ", "     ", "     ", "     "),
    "/": ("    ╱", "   ╱ ", "  ╱  ", " ╱   ", "╱    "),
    "(": ("  ╱  ", " │   ", " │   ", " │   ", "  ╲  "),
    ")": ("  ╲  ", "   │ ", "   │ ", "   │ ", "  ╱  "),
    "+": ("     ", "  │  ", "──┼──", "  │  ", "     "),
    "=": ("     ", "─────", "     ", "─────", "     "),
    "_": ("     ", "     ", "     ", "     ", "─────"),
    "#": (" │ │ ", "─┼─┼─", " │ │ ", "─┼─┼─", " │ │ "),
    "@": ("┌───┐", "│┌──┤", "│├──┤", "│└──┘", "└────"),
    "*": ("╲ │ ╱", " ╲│╱ ", "──┼──", " ╱│╲ ", "╱ │ ╲"),
    "\x00": ("┌───┐", "│   │", "│   │", "│   │", "└───┘"),
}


# --- Rendering ----------------------------------------------------------------


def _normalize(text: str) -> str:
    """Lowercase and collapse interior whitespace to single spaces."""
    text = text.lower()
    return "".join(" " if c in "\t\n\r" else c for c in text)


def _glyph_bits(char: str) -> list[list[int]]:
    """The char's 8×8 pixel grid (rows of 0/1), falling back to the box glyph."""
    glyph = _IBM_8X8.get(char, _IBM_8X8["\x00"])
    return [[(byte >> col) & 1 for col in range(8)] for byte in glyph]


def _pack(bits: list[list[int]], style: Style, density: _Density) -> Block:
    """Pack a pixel grid into cells at ``density``.

    Each cell encodes a ``(cols × rows)`` sub-grid of pixels; the lit pattern
    selects a Unicode block glyph. The grid's dimensions must divide evenly by the
    density (the 8×8 font does, for all three densities)."""
    cols_per, rows_per = density.value
    height = len(bits)
    width = len(bits[0]) if height else 0
    table = _DENSITY_CHARS[density]
    rows: list[list[Cell]] = []
    for cy in range(0, height, rows_per):
        row: list[Cell] = []
        for cx in range(0, width, cols_per):
            key = tuple(bits[cy + dy][cx + dx] for dy in range(rows_per) for dx in range(cols_per))
            row.append(Cell(table[key], style))
        rows.append(row)
    return Block(rows, width // cols_per)


def _render_filled(text: str, style: Style, size: int) -> Block:
    """Pack each glyph's 8×8 bitmap at the density `size` selects, then join."""
    density = _SIZE_DENSITY.get(size, _Density.QUADRANT)
    cell_height = 8 // density.value[1]
    if not text:
        return Block.empty(0, cell_height)
    glyphs = [_pack(_glyph_bits(c), style, density) for c in _normalize(text)]
    return join_horizontal(*glyphs, gap=_GLYPH_GAP)


def _render_outline(text: str, style: Style, size: int) -> Block:
    """Lay out hand-encoded box-drawing glyphs (3-row, or 5-row at size 2)."""
    if size == 2:
        glyphs = _GLYPHS_5ROW_OUTLINE
        glyph_width = 5
    else:
        glyphs = _GLYPHS_3ROW_OUTLINE
        glyph_width = 3
    glyph_height = glyph_width  # both outline sets are square
    if not text:
        return Block.empty(0, glyph_height)
    fallback = glyphs["\x00"]
    blocks: list[Block] = []
    for char in _normalize(text):
        glyph = glyphs.get(char, fallback)
        rows = [[Cell(c, style) for c in row_str] for row_str in glyph]
        blocks.append(Block(rows, glyph_width))
    return join_horizontal(*blocks, gap=1)


def render_big(
    text: str,
    style: Style = Style(),
    *,
    size: int = 1,
    format: BigTextFormat = BigTextFormat.FILLED,
) -> Block:
    """Render text as large block characters.

    Args:
        text: String to render (lower-cased; whitespace collapsed to spaces).
        style: Style applied to every lit cell.
        size: 1 (compact) or 2 (large). For FILLED these are densities over one
            8×8 font — size=1 packs at HALF (4 cells tall), size=2 at FULL
            (8 cells tall); both are 8 cells wide per glyph. For OUTLINE they are
            the 3-row and 5-row glyph sets.
        format: FILLED (solid blocks packed from the bitmap font) or OUTLINE
            (box-drawing strokes).

    Returns:
        A Block whose height depends on format and size:
        FILLED  size=1 → 4 cells tall, glyphs 8 wide (width 9n−1 with gaps);
                size=2 → 8 cells tall, glyphs 8 wide (width 9n−1);
                (both FILLED sizes share width 9n−1; they differ only in height);
        OUTLINE size=1 → 3 cells tall; size=2 → 5 cells tall.
        (FILLED and OUTLINE are different models and do not share a height.)
    """
    if format == BigTextFormat.OUTLINE:
        return _render_outline(text, style, size)
    return _render_filled(text, style, size)
