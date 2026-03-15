"""Cell-buffer rendering system.

CLI core: styled output primitives for dressing up scripts.

For interactive TUI apps, import from submodules:
    from painted.tui import Surface, Layer
    from painted.views import shape_lens
    from painted.views import spinner, list_view
    from painted.tui import MouseEvent
    from painted.views import render_big

For aesthetic customization:
    from painted import current_palette, use_palette, MONO_PALETTE
    from painted import current_icons, use_icons, ASCII_ICONS

For CLI harness and in-place rendering:
    from painted.cli import run_cli, CliRunner
    from painted.inplace import InPlaceRenderer
"""

# Primitives
from .core.block import Block, Wrap
from .core.borders import ASCII, DOUBLE, HEAVY, LIGHT, ROUNDED, BorderChars
from .core.cell import EMPTY_CELL, Cell, Style

# Composition
from .core.compose import (
    Align,
    border,
    join_horizontal,
    join_responsive,
    join_vertical,
    pad,
    truncate,
    vslice,
)
from .cursor import Cursor, CursorMode

# CLI framework
from .cli import (
    CliContext,
    CliRunner,
    Format,
    HelpArg,
    HelpData,
    HelpFlag,
    HelpGroup,
    OutputMode,
    Zoom,
    add_cli_args,
    detect_context,
    parse_format,
    parse_mode,
    parse_zoom,
    resolve_mode,
    run_cli,
)

# App runner (multi-command routing)
from .cli import AppCommand, AppRunner, run_app
from .icon_set import (
    ASCII_ICONS,
    IconSet,
    current_icons,
    reset_icons,
    use_icons,
)

# In-place rendering
from .inplace import InPlaceRenderer

# Aesthetic
from .palette import (
    DEFAULT_PALETTE,
    MONO_PALETTE,
    NORD_PALETTE,
    Palette,
    current_palette,
    reset_palette,
    use_palette,
)
from .core.span import Line, Span
from .viewport import Viewport

# Output
from .core.writer import ColorDepth, Writer, print_block
from .core.html import render_html

# Display
from .display import show

__all__ = [
    # Primitives
    "Style",
    "Cell",
    "EMPTY_CELL",
    "Span",
    "Line",
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
    "Cursor",
    "CursorMode",
    "Viewport",
    "BorderChars",
    "ROUNDED",
    "HEAVY",
    "DOUBLE",
    "LIGHT",
    "ASCII",
    # Output
    "Writer",
    "ColorDepth",
    "print_block",
    "render_html",
    # Display
    "show",
    # CLI framework
    "Zoom",
    "OutputMode",
    "Format",
    "CliContext",
    "CliRunner",
    "HelpArg",
    "run_cli",
    "AppCommand",
    "AppRunner",
    "run_app",
    "add_cli_args",
    "parse_zoom",
    "parse_mode",
    "parse_format",
    "resolve_mode",
    "detect_context",
    # In-place rendering
    "InPlaceRenderer",
    # Aesthetic
    "Palette",
    "DEFAULT_PALETTE",
    "NORD_PALETTE",
    "MONO_PALETTE",
    "current_palette",
    "use_palette",
    "reset_palette",
    "IconSet",
    "ASCII_ICONS",
    "current_icons",
    "use_icons",
    "reset_icons",
]
