"""Lens functions: stateless content-to-Block transformation at zoom levels."""

__all__ = [
    "NodeRenderer",
    "chart_lens",
    "flame_lens",
    "shape_lens",
    "tree_lens",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "NodeRenderer": (".tree", "NodeRenderer"),
    "chart_lens": (".chart", "chart_lens"),
    "flame_lens": (".flame", "flame_lens"),
    "shape_lens": (".shape", "shape_lens"),
    "tree_lens": (".tree", "tree_lens"),
}


def __dir__() -> list[str]:
    return list(__all__) + list(globals())


def __getattr__(name: str):
    spec = _LAZY_IMPORTS.get(name)
    if spec is None:
        raise AttributeError(f"module 'painted.views.lens' has no attribute {name!r}")

    module_path, attr = spec
    import importlib

    mod = importlib.import_module(module_path, __name__)
    value = getattr(mod, attr)
    globals()[name] = value
    return value
