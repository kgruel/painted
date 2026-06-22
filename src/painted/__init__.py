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
    "rule",
    "truncate",
    "fit_to_width",
    "vslice",
    "budget_fields",
    "BudgetFit",
    "Cursor",
    "CursorMode",
    "Viewport",
    "BorderChars",
    "ROUNDED",
    "HEAVY",
    "DOUBLE",
    "LIGHT",
    "ASCII",
    "current_borders",
    "use_borders",
    "reset_borders",
    # Theme
    "Theme",
    "DEFAULT_THEME",
    "NORD_THEME",
    "MONO_THEME",
    "PAINTED_THEME",
    "use_theme",
    "reset_theme",
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
    "Fidelity",
    "Tag",
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
    "parse_fidelity",
    "resolve_mode",
    "detect_context",
    # In-place rendering
    "InPlaceRenderer",
    # Aesthetic
    "Palette",
    "DEFAULT_PALETTE",
    "NORD_PALETTE",
    "MONO_PALETTE",
    "PAINTED_PALETTE",
    "current_palette",
    "use_palette",
    "reset_palette",
    "IconSet",
    "ASCII_ICONS",
    "current_icons",
    "use_icons",
    "reset_icons",
]

from importlib import import_module as _import_module

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Core
    "Cell": (".core.cell", "Cell"),
    "EMPTY_CELL": (".core.cell", "EMPTY_CELL"),
    "Style": (".core.cell", "Style"),
    "Line": (".core.span", "Line"),
    "Span": (".core.span", "Span"),
    "Block": (".core.block", "Block"),
    "Wrap": (".core.block", "Wrap"),
    "Zoom": (".core.zoom", "Zoom"),
    "Align": (".core.compose", "Align"),
    "border": (".core.compose", "border"),
    "rule": (".core.compose", "rule"),
    "join_horizontal": (".core.compose", "join_horizontal"),
    "join_responsive": (".core.compose", "join_responsive"),
    "join_vertical": (".core.compose", "join_vertical"),
    "pad": (".core.compose", "pad"),
    "truncate": (".core.compose", "truncate"),
    "fit_to_width": (".core.compose", "fit_to_width"),
    "vslice": (".core.compose", "vslice"),
    "budget_fields": (".core.compose", "budget_fields"),
    "BudgetFit": (".core.compose", "BudgetFit"),
    "ASCII": (".core.borders", "ASCII"),
    "DOUBLE": (".core.borders", "DOUBLE"),
    "HEAVY": (".core.borders", "HEAVY"),
    "LIGHT": (".core.borders", "LIGHT"),
    "ROUNDED": (".core.borders", "ROUNDED"),
    "BorderChars": (".core.borders", "BorderChars"),
    "current_borders": (".core.borders", "current_borders"),
    "use_borders": (".core.borders", "use_borders"),
    "reset_borders": (".core.borders", "reset_borders"),
    "ColorDepth": (".core.writer", "ColorDepth"),
    "Writer": (".core.writer", "Writer"),
    "print_block": (".core.writer", "print_block"),
    "render_html": (".core.html", "render_html"),
    "Cursor": (".cursor", "Cursor"),
    "CursorMode": (".cursor", "CursorMode"),
    "Viewport": (".viewport", "Viewport"),
    # CLI
    "CliContext": (".cli", "CliContext"),
    "CliRunner": (".cli", "CliRunner"),
    "Fidelity": (".cli", "Fidelity"),
    "Format": (".cli", "Format"),
    "Tag": (".cli", "Tag"),
    "HelpArg": (".cli", "HelpArg"),
    "OutputMode": (".cli", "OutputMode"),
    "add_cli_args": (".cli", "add_cli_args"),
    "detect_context": (".cli", "detect_context"),
    "parse_fidelity": (".cli", "parse_fidelity"),
    "parse_format": (".cli", "parse_format"),
    "parse_mode": (".cli", "parse_mode"),
    "parse_zoom": (".cli", "parse_zoom"),
    "resolve_mode": (".cli", "resolve_mode"),
    "run_cli": (".cli", "run_cli"),
    "AppCommand": (".cli", "AppCommand"),
    "AppRunner": (".cli", "AppRunner"),
    "run_app": (".cli", "run_app"),
    # Aesthetic + display
    "ASCII_ICONS": (".icon_set", "ASCII_ICONS"),
    "IconSet": (".icon_set", "IconSet"),
    "current_icons": (".icon_set", "current_icons"),
    "reset_icons": (".icon_set", "reset_icons"),
    "use_icons": (".icon_set", "use_icons"),
    "InPlaceRenderer": (".inplace", "InPlaceRenderer"),
    "DEFAULT_PALETTE": (".palette", "DEFAULT_PALETTE"),
    "MONO_PALETTE": (".palette", "MONO_PALETTE"),
    "NORD_PALETTE": (".palette", "NORD_PALETTE"),
    "PAINTED_PALETTE": (".palette", "PAINTED_PALETTE"),
    "Palette": (".palette", "Palette"),
    "current_palette": (".palette", "current_palette"),
    "reset_palette": (".palette", "reset_palette"),
    "use_palette": (".palette", "use_palette"),
    "Theme": (".theme", "Theme"),
    "DEFAULT_THEME": (".theme", "DEFAULT_THEME"),
    "NORD_THEME": (".theme", "NORD_THEME"),
    "MONO_THEME": (".theme", "MONO_THEME"),
    "PAINTED_THEME": (".theme", "PAINTED_THEME"),
    "use_theme": (".theme", "use_theme"),
    "reset_theme": (".theme", "reset_theme"),
    "show": (".display", "show"),
}


def __dir__():
    return list(__all__) + list(globals())


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is not None:
        module_path, attr = spec
        mod = _import_module(module_path, __name__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'painted' has no attribute {name!r}")
