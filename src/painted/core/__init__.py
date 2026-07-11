"""painted.core — sub-millisecond cell buffer renderer.

Pure rendering primitives: no CLI framework, no TUI, no runtime dependencies
beyond wcwidth. Import from here when you just want the renderer.

    from painted.core import Block, Style, join_horizontal, border, Buffer
"""

from importlib import import_module as _import_module

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
    "rule",
    "truncate",
    "fit_to_width",
    "vslice",
    "budget_fields",
    "BudgetFit",
    # Borders
    "BorderChars",
    "ROUNDED",
    "HEAVY",
    "DOUBLE",
    "LIGHT",
    "ASCII",
    "current_borders",
    "use_borders",
    "reset_borders",
    # Buffer
    "Buffer",
    "BufferView",
    "CellWrite",
    # Text primitives
    "Span",
    "Line",
    # Measurement
    "display_width",
    # Rendering constraint
    "Zoom",
    # Doc-IR: node vocabulary + the document compositor (exported at 0.10;
    # the disclosure walk visible_body/capped stays unexported — painted's two
    # projectors are its only sanctioned readers)
    "Doc",
    "Section",
    "Prose",
    "Def",
    "Defs",
    "Items",
    "Code",
    "Figure",
    "Link",
    "doc_lens",
    # Output
    "Writer",
    "ColorDepth",
    "print_block",
    "render_html",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "PaintedError": (".errors", "PaintedError"),
    "DeclarationError": (".errors", "DeclarationError"),
    "ContractError": (".errors", "ContractError"),
    "LifecycleError": (".errors", "LifecycleError"),
    "Style": (".cell", "Style"),
    "Cell": (".cell", "Cell"),
    "EMPTY_CELL": (".cell", "EMPTY_CELL"),
    "Block": (".block", "Block"),
    "Wrap": (".block", "Wrap"),
    "Align": (".compose", "Align"),
    "join_horizontal": (".compose", "join_horizontal"),
    "join_vertical": (".compose", "join_vertical"),
    "join_responsive": (".compose", "join_responsive"),
    "pad": (".compose", "pad"),
    "border": (".compose", "border"),
    "rule": (".compose", "rule"),
    "truncate": (".compose", "truncate"),
    "fit_to_width": (".compose", "fit_to_width"),
    "vslice": (".compose", "vslice"),
    "budget_fields": (".compose", "budget_fields"),
    "BudgetFit": (".compose", "BudgetFit"),
    "BorderChars": (".borders", "BorderChars"),
    "ROUNDED": (".borders", "ROUNDED"),
    "HEAVY": (".borders", "HEAVY"),
    "DOUBLE": (".borders", "DOUBLE"),
    "LIGHT": (".borders", "LIGHT"),
    "ASCII": (".borders", "ASCII"),
    "current_borders": (".borders", "current_borders"),
    "use_borders": (".borders", "use_borders"),
    "reset_borders": (".borders", "reset_borders"),
    "Buffer": (".buffer", "Buffer"),
    "BufferView": (".buffer", "BufferView"),
    "CellWrite": (".buffer", "CellWrite"),
    "Span": (".span", "Span"),
    "Line": (".span", "Line"),
    "display_width": ("._text_width", "display_width"),
    "Zoom": (".zoom", "Zoom"),
    "Doc": (".doc", "Doc"),
    "Section": (".doc", "Section"),
    "Prose": (".doc", "Prose"),
    "Def": (".doc", "Def"),
    "Defs": (".doc", "Defs"),
    "Items": (".doc", "Items"),
    "Code": (".doc", "Code"),
    "Figure": (".doc", "Figure"),
    "Link": (".doc", "Link"),
    "doc_lens": (".doc", "doc_lens"),
    "Writer": (".writer", "Writer"),
    "ColorDepth": (".writer", "ColorDepth"),
    "print_block": (".writer", "print_block"),
    "render_html": (".html", "render_html"),
}


def __dir__() -> list[str]:
    return list(__all__) + list(globals())


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is not None:
        module_path, attr = spec
        mod = _import_module(module_path, __name__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'painted.core' has no attribute {name!r}")
