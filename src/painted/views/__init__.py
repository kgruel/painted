"""Views: view-layer primitives (data/state -> Block).

Public namespace for Painted view-layer APIs.
"""

__all__ = [
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
    # Theme
    "Theme",
    "DEFAULT_THEME",
    "NORD_THEME",
    "MONO_THEME",
    "PAINTED_THEME",
    "use_theme",
    "reset_theme",
    # Stateless views
    "NodeRenderer",
    "shape_lens",
    "tree_lens",
    "chart_lens",
    "flame_lens",
    "sparkline",
    "sparkline_with_range",
    "cost_meter",
    "SpinnerState",
    "SpinnerFrames",
    "spinner",
    "DOTS",
    "LINE",
    "BRAILLE",
    "ProgressState",
    "progress_bar",
    "render_big",
    "BigTextFormat",
    "BIG_GLYPHS",
    # Stateful views
    "ListState",
    "list_view",
    "TableState",
    "Column",
    "AUTO",
    "Fill",
    "table",
    "TextInputState",
    "text_input",
    "DataExplorerState",
    "DataNode",
    "data_explorer",
    "flatten",
    # Profile bridge
    "ProfileResult",
    "profile",
    "parse_collapsed",
    # Record rendering
    "PayloadLens",
    "GutterFn",
    "AttentionFn",
    "record_line",
    "record_timeline",
    "record_map",
    "record_line_composed",
    "apply_gutter",
    "apply_attention",
    "gutter_lifecycle",
    "gutter_freshness",
    "gutter_pass_fail",
    "attention_staleness",
    "attention_novelty",
    "attention_blocked",
    "attention_relevance",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    # Aesthetic
    "Palette": ("..palette", "Palette"),
    "DEFAULT_PALETTE": ("..palette", "DEFAULT_PALETTE"),
    "NORD_PALETTE": ("..palette", "NORD_PALETTE"),
    "MONO_PALETTE": ("..palette", "MONO_PALETTE"),
    "PAINTED_PALETTE": ("..palette", "PAINTED_PALETTE"),
    "current_palette": ("..palette", "current_palette"),
    "use_palette": ("..palette", "use_palette"),
    "reset_palette": ("..palette", "reset_palette"),
    "IconSet": ("..icon_set", "IconSet"),
    "ASCII_ICONS": ("..icon_set", "ASCII_ICONS"),
    "current_icons": ("..icon_set", "current_icons"),
    "use_icons": ("..icon_set", "use_icons"),
    "reset_icons": ("..icon_set", "reset_icons"),
    # Borders
    "BorderChars": ("..core.borders", "BorderChars"),
    "ROUNDED": ("..core.borders", "ROUNDED"),
    "HEAVY": ("..core.borders", "HEAVY"),
    "DOUBLE": ("..core.borders", "DOUBLE"),
    "LIGHT": ("..core.borders", "LIGHT"),
    "ASCII": ("..core.borders", "ASCII"),
    "current_borders": ("..core.borders", "current_borders"),
    "use_borders": ("..core.borders", "use_borders"),
    "reset_borders": ("..core.borders", "reset_borders"),
    # Theme
    "Theme": ("..theme", "Theme"),
    "DEFAULT_THEME": ("..theme", "DEFAULT_THEME"),
    "NORD_THEME": ("..theme", "NORD_THEME"),
    "MONO_THEME": ("..theme", "MONO_THEME"),
    "PAINTED_THEME": ("..theme", "PAINTED_THEME"),
    "use_theme": ("..theme", "use_theme"),
    "reset_theme": ("..theme", "reset_theme"),
    # Stateless views
    "NodeRenderer": (".lens", "NodeRenderer"),
    "shape_lens": (".lens", "shape_lens"),
    "tree_lens": (".lens", "tree_lens"),
    "chart_lens": (".lens", "chart_lens"),
    "flame_lens": (".lens", "flame_lens"),
    "sparkline": (".components._sparkline", "sparkline"),
    "sparkline_with_range": (".components._sparkline", "sparkline_with_range"),
    "cost_meter": (".components._meter", "cost_meter"),
    "SpinnerState": (".components._spinner", "SpinnerState"),
    "SpinnerFrames": (".components._spinner", "SpinnerFrames"),
    "spinner": (".components._spinner", "spinner"),
    "DOTS": (".components._spinner", "DOTS"),
    "LINE": (".components._spinner", "LINE"),
    "BRAILLE": (".components._spinner", "BRAILLE"),
    "ProgressState": (".components.progress", "ProgressState"),
    "progress_bar": (".components.progress", "progress_bar"),
    "render_big": (".big_text", "render_big"),
    "BigTextFormat": (".big_text", "BigTextFormat"),
    "BIG_GLYPHS": (".big_text", "BIG_GLYPHS"),
    # Stateful views
    "ListState": (".components._list_view", "ListState"),
    "list_view": (".components._list_view", "list_view"),
    "TableState": (".components._table", "TableState"),
    "Column": (".components._table", "Column"),
    "AUTO": (".components._table", "AUTO"),
    "Fill": (".components._table", "Fill"),
    "table": (".components._table", "table"),
    "TextInputState": (".components._text_input", "TextInputState"),
    "text_input": (".components._text_input", "text_input"),
    "DataExplorerState": (".components._data_explorer", "DataExplorerState"),
    "DataNode": (".components._data_explorer", "DataNode"),
    "data_explorer": (".components._data_explorer", "data_explorer"),
    "flatten": (".components._data_explorer", "flatten"),
    # Profile bridge
    "ProfileResult": ("._profile", "ProfileResult"),
    "profile": ("._profile", "profile"),
    "parse_collapsed": ("._profile", "parse_collapsed"),
    # Record rendering
    "PayloadLens": (".record", "PayloadLens"),
    "GutterFn": (".record", "GutterFn"),
    "AttentionFn": (".record", "AttentionFn"),
    "record_line": (".record", "record_line"),
    "record_timeline": (".record", "record_timeline"),
    "record_map": (".record", "record_map"),
    "record_line_composed": (".record", "record_line_composed"),
    "apply_gutter": (".record", "apply_gutter"),
    "apply_attention": (".record", "apply_attention"),
    "gutter_lifecycle": (".record", "gutter_lifecycle"),
    "gutter_freshness": (".record", "gutter_freshness"),
    "gutter_pass_fail": (".record", "gutter_pass_fail"),
    "attention_staleness": (".record", "attention_staleness"),
    "attention_novelty": (".record", "attention_novelty"),
    "attention_blocked": (".record", "attention_blocked"),
    "attention_relevance": (".record", "attention_relevance"),
}


def __dir__() -> list[str]:
    return list(__all__) + list(globals())


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module 'painted.views' has no attribute {name!r}")

    module_path, attr = spec
    import importlib

    mod = importlib.import_module(module_path, __name__)
    value = getattr(mod, attr)
    globals()[name] = value
    return value
