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

# Root package is fully lazy. This keeps `import painted.core` and
# `from painted import ...` cold-start cost low by avoiding eager imports
# of renderer/framework modules until symbols are actually accessed.

__all__ = [
    # Primitives
    "Style",
    "Cell",
    "EMPTY_CELL",
    "Span",
    "Line",
    "Block",
    "Wrap",
    "Zoom",
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

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {}


def _register_lazy(module: str, names: list[str]) -> None:
    for name in names:
        _LAZY_IMPORTS[name] = (module, name)


_register_lazy(".core.cell", ["Cell", "EMPTY_CELL", "Style"])
_register_lazy(".core.span", ["Line", "Span"])
_register_lazy(".core.block", ["Block", "Wrap"])
_register_lazy(".core.zoom", ["Zoom"])
_register_lazy(
    ".core.compose",
    [
        "Align",
        "border",
        "join_horizontal",
        "join_responsive",
        "join_vertical",
        "pad",
        "truncate",
        "vslice",
    ],
)
_register_lazy(
    ".core.borders",
    ["ASCII", "DOUBLE", "HEAVY", "LIGHT", "ROUNDED", "BorderChars"],
)
_register_lazy(".core.writer", ["ColorDepth", "Writer", "print_block"])
_register_lazy(".core.html", ["render_html"])
_register_lazy(".cursor", ["Cursor", "CursorMode"])
_register_lazy(".viewport", ["Viewport"])

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


def __dir__():
    return list(__all__) + list(globals())


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is not None:
        module_path, attr = spec
        import importlib

        mod = importlib.import_module(module_path, __name__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'painted' has no attribute {name!r}")
