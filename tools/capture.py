"""Shared helpers to capture demo output for tests and docs.

Supports two demo shapes (see tests/golden/CLAUDE.md):
- run_cli demos expose `_fetch()` and `_render(ctx, data)` → returns a Block
- direct-output demos expose standalone functions that write to stdout → returns text
"""

from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
from types import ModuleType

from painted import Block, CliContext, Fidelity, Zoom
from painted.cli import OutputMode

CaptureResult = Block | str


def import_module_by_path(path: str | Path, *, module_name: str | None = None) -> ModuleType:
    """Import a Python module from a file path without mutating sys.path."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    if p.suffix != ".py":
        raise ValueError(f"Expected a .py file, got: {p}")

    name = module_name or f"_demo_{p.stem}"
    spec = importlib.util.spec_from_file_location(name, p)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create module spec for {p}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # required for dataclass module lookup
    spec.loader.exec_module(mod)
    return mod


@contextmanager
def _patch_show_to_sys_stdout():
    """Make painted.show() respect redirect_stdout by using sys.stdout dynamically.

    show() has file=sys.stdout as an early-bound default, so redirect_stdout
    won't capture it unless we temporarily wrap the call site.
    print_block() already resolves sys.stdout at call time — no patch needed.
    """
    import painted as _painted

    orig_show = _painted.show

    def _show(*args, **kwargs):
        if "file" not in kwargs:
            kwargs["file"] = sys.stdout
        return orig_show(*args, **kwargs)

    _painted.show = _show  # type: ignore[assignment]
    try:
        yield
    finally:
        _painted.show = orig_show  # type: ignore[assignment]


def capture_demo(
    demo_path: str | Path,
    function_or_zoom: str | Zoom,
    *,
    width: int,
    height: int = 24,
    data_attr: str | None = None,
) -> CaptureResult:
    """Capture a demo output from file path.

    Args:
        demo_path: Path to a demo .py file.
        function_or_zoom:
            - Zoom → run_cli demo shape (_fetch/_render) returning a Block
            - str → direct-output demo shape: function name to call, returning captured stdout as text
        width: Render width (only used for run_cli demos).
        height: Render height (only used for run_cli demos).
        data_attr: Optional module attribute name to use as render data (instead of calling _fetch()).
    """
    if isinstance(function_or_zoom, Zoom):
        mod = import_module_by_path(demo_path)
        zoom = function_or_zoom
        fetch = getattr(mod, "_fetch", None)
        render = getattr(mod, "_render", None)
        if not callable(render):
            raise AttributeError(f"{demo_path} is missing callable _render(ctx, data)")

        if data_attr is not None:
            if not hasattr(mod, data_attr):
                raise AttributeError(f"{demo_path} missing data attribute {data_attr!r}")
            data = getattr(mod, data_attr)
        else:
            if not callable(fetch):
                raise AttributeError(f"{demo_path} is missing callable _fetch()")
            data = fetch()

        # Resolve tag implications exactly as the CLI compiler would — a demo
        # declaring _TAGS gets the same visible set here as via run_cli, so
        # capture output can't diverge from what the flags produce.
        from painted.cli import implied_visible

        fidelity = Fidelity(
            depth=int(zoom),
            visible=implied_visible(getattr(mod, "_TAGS", None), int(zoom)),
        )
        ctx = CliContext(
            fidelity=fidelity,
            mode=OutputMode.STATIC,
            use_ansi=False,
            is_tty=False,
            width=width,
            height=height,
        )
        out = render(ctx, data)
        if not isinstance(out, Block):
            raise TypeError(f"{demo_path}._render returned {type(out).__name__}, expected Block")
        return out

    fn_name = function_or_zoom
    buf = StringIO()
    with _patch_show_to_sys_stdout(), redirect_stdout(buf):
        mod = import_module_by_path(demo_path, module_name=f"_demo_{Path(demo_path).stem}_output")
        if fn_name == "<module>":
            if data_attr is not None:
                val = getattr(mod, data_attr, None)
                if isinstance(val, Block):
                    return val
            return buf.getvalue()
        fn = getattr(mod, fn_name, None)
        if not callable(fn):
            raise AttributeError(f"{demo_path} is missing callable {fn_name}()")
        fn()
    return buf.getvalue()
