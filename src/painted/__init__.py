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

# --- Eager: core primitives (always cheap, no higher-layer deps) ---

from .core.block import Block, Wrap
from .core.borders import ASCII, DOUBLE, HEAVY, LIGHT, ROUNDED, BorderChars
from .core.cell import EMPTY_CELL, Cell, Style
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
from .core.span import Line, Span
from .core.writer import ColorDepth, Writer, print_block
from .core.html import render_html
from .core.zoom import Zoom

# --- Eager: shared root primitives (leaf nodes, no higher-layer deps) ---

from .cursor import Cursor, CursorMode
from .viewport import Viewport

# --- Lazy: everything else (cli, views, aesthetic, display) ---
#
# This ensures `import painted.core` or `from painted import Block` does not
# pull in cli/, views/, or tui/. Higher-layer symbols are resolved on first
# access via __getattr__.

__all__ = [
    # Primitives (eager)
    "Style",
    "Cell",
    "EMPTY_CELL",
    "Span",
    "Line",
    "Block",
    "Wrap",
    "Zoom",
    # Composition (eager)
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
    # Output (eager)
    "Writer",
    "ColorDepth",
    "print_block",
    "render_html",
    # Display (lazy)
    "show",
    # CLI framework (lazy)
    "OutputMode",
    "Format",
    "CliContext",
    "CliRunner",
    "HelpArg",
    "HelpData",
    "HelpFlag",
    "HelpGroup",
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
    # In-place rendering (lazy)
    "InPlaceRenderer",
    # Aesthetic (lazy)
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

# Mapping from lazy symbol name → (module, name) for __getattr__
_LAZY_IMPORTS: dict[str, tuple[str, str]] = {}


def _register_lazy(module: str, names: list[str]) -> None:
    for name in names:
        _LAZY_IMPORTS[name] = (module, name)


_register_lazy(
    ".cli",
    [
        "CliContext",
        "CliRunner",
        "Format",
        "HelpArg",
        "HelpData",
        "HelpFlag",
        "HelpGroup",
        "OutputMode",
        "add_cli_args",
        "detect_context",
        "parse_format",
        "parse_mode",
        "parse_zoom",
        "resolve_mode",
        "run_cli",
        "AppCommand",
        "AppRunner",
        "run_app",
    ],
)

_register_lazy(
    ".icon_set",
    ["ASCII_ICONS", "IconSet", "current_icons", "reset_icons", "use_icons"],
)

_register_lazy(".inplace", ["InPlaceRenderer"])

_register_lazy(
    ".palette",
    [
        "DEFAULT_PALETTE",
        "MONO_PALETTE",
        "NORD_PALETTE",
        "Palette",
        "current_palette",
        "reset_palette",
        "use_palette",
    ],
)

_register_lazy(".display", ["show"])


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is not None:
        module_path, attr = spec
        import importlib

        mod = importlib.import_module(module_path, __name__)
        value = getattr(mod, attr)
        # Cache on module to avoid repeated __getattr__ calls
        globals()[name] = value
        return value
    raise AttributeError(f"module 'painted' has no attribute {name!r}")
