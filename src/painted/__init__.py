"""A semantic renderer for the terminal, built on cell buffers.

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
    # Errors
    "PaintedError",
    "DeclarationError",
    "ContractError",
    "LifecycleError",
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
    # Host rung — the omitted arm's viewport adapter (0.13)
    "ViewportAdapter",
    "RenderKey",
    "Plan",
    "RenderAction",
    "Frame",
    "FrameToken",
    "FrameRegion",
    "Hit",
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
    "paint",
    "show",
    # CLI framework
    "OutputMode",
    "Format",
    "Fidelity",
    "Tag",
    "CliContext",
    "CliRunner",
    "Renderer",
    "HeightRenderer",
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
    # Diagnostics
    "PaintedHandler",
    "install",
    "DEFAULT_THRESHOLDS",
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
    "Capabilities",
    "use_capabilities",
    "current_capabilities",
    "reset_capabilities",
    # Vocabularies
    "Role",
    "Vocabulary",
    "Thresholds",
    "use_vocabularies",
    "current_vocabularies",
    "reset_vocabularies",
    "mark_style",
    # Refs
    "RefScheme",
    "use_refs",
    "current_ref_schemes",
    "reset_refs",
    "resolve_ref",
]

from importlib import import_module as _import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # The root facade resolves names lazily through __getattr__, which types them
    # as Any — erasing run_cli's published @overloads (so `fetch` would look
    # optional) and the Renderer alias's shape. src/painted/CLAUDE.md Level 2
    # teaches `from painted import run_cli`, so this taught path must carry the
    # real types to checkers; re-import them here, runtime staying lazy.
    from .cli import (
        CliRunner as CliRunner,
        HeightRenderer as HeightRenderer,
        Renderer as Renderer,
        run_cli as run_cli,
    )

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Errors
    "PaintedError": (".core.errors", "PaintedError"),
    "DeclarationError": (".core.errors", "DeclarationError"),
    "ContractError": (".core.errors", "ContractError"),
    "LifecycleError": (".core.errors", "LifecycleError"),
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
    # Host rung
    "ViewportAdapter": (".host", "ViewportAdapter"),
    "RenderKey": (".host", "RenderKey"),
    "Plan": (".host", "Plan"),
    "RenderAction": (".host", "RenderAction"),
    "Frame": (".host", "Frame"),
    "FrameToken": (".host", "FrameToken"),
    "FrameRegion": (".host", "FrameRegion"),
    "Hit": (".host", "Hit"),
    # CLI
    "CliContext": (".cli", "CliContext"),
    "CliRunner": (".cli", "CliRunner"),
    "Renderer": (".cli", "Renderer"),
    "HeightRenderer": (".cli", "HeightRenderer"),
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
    "Capabilities": (".capabilities", "Capabilities"),
    "current_capabilities": (".capabilities", "current_capabilities"),
    "reset_capabilities": (".capabilities", "reset_capabilities"),
    "use_capabilities": (".capabilities", "use_capabilities"),
    "InPlaceRenderer": (".inplace", "InPlaceRenderer"),
    "PaintedHandler": (".diagnostics", "PaintedHandler"),
    "install": (".diagnostics", "install"),
    "DEFAULT_THRESHOLDS": (".diagnostics", "DEFAULT_THRESHOLDS"),
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
    "Role": (".vocabulary", "Role"),
    "Vocabulary": (".vocabulary", "Vocabulary"),
    "Thresholds": (".vocabulary", "Thresholds"),
    "use_vocabularies": (".vocabulary", "use_vocabularies"),
    "current_vocabularies": (".vocabulary", "current_vocabularies"),
    "reset_vocabularies": (".vocabulary", "reset_vocabularies"),
    "mark_style": (".vocabulary", "mark_style"),
    "RefScheme": (".refs", "RefScheme"),
    "use_refs": (".refs", "use_refs"),
    "current_ref_schemes": (".refs", "current_ref_schemes"),
    "reset_refs": (".refs", "reset_refs"),
    "resolve_ref": (".refs", "resolve_ref"),
    "paint": (".display", "paint"),
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
