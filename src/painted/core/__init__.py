"""painted.core — sub-millisecond cell buffer renderer.

Pure rendering primitives: no CLI framework, no TUI, no runtime dependencies
beyond wcwidth. Import from here when you just want the renderer.

    from painted.core import Block, Style, join_horizontal, border, Buffer
"""

# Primitives
from .cell import EMPTY_CELL, Cell, Style

# Blocks
from .block import Block, Wrap

# Composition
from .compose import (
    Align,
    border,
    join_horizontal,
    join_responsive,
    join_vertical,
    pad,
    truncate,
    vslice,
)

# Borders
from .borders import ASCII, DOUBLE, HEAVY, LIGHT, ROUNDED, BorderChars

# Buffer
from .buffer import Buffer, BufferView, CellWrite

# Text primitives
from .span import Line, Span

# Rendering constraint
from .zoom import Zoom

# Output
from .writer import ColorDepth, Writer, print_block
from .html import render_html

__all__ = [
    # Primitives
    "Style",
    "Cell",
    "EMPTY_CELL",
    # Blocks
    "Block",
    "Wrap",
    # Composition
    "Align",
    "join_horizontal",
    "join_vertical",
    "join_responsive",
    "pad",
    "border",
    "truncate",
    "vslice",
    # Borders
    "BorderChars",
    "ROUNDED",
    "HEAVY",
    "DOUBLE",
    "LIGHT",
    "ASCII",
    # Buffer
    "Buffer",
    "BufferView",
    "CellWrite",
    # Text primitives
    "Span",
    "Line",
    # Rendering constraint
    "Zoom",
    # Output
    "Writer",
    "ColorDepth",
    "print_block",
    "render_html",
]
