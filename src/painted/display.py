"""paint() — render any Python value onto a surface.

`paint(subject)` is the single entry point (0.8+). With no lens it transcribes
what carries its own meaning (text, a Block, a dict/list/tuple, a declared
schema); a lens is taken only to *interpret* — arrangement that reinterprets the
subject as something other than itself. See docs/PAINT_DESIGN.md.

Paths:
- No args: blank line (the sole print() parity concession)
- Block: delivered directly via print_block
- Scalar: str()
- Otherwise: transcribe the declared shape (the no-lens default `transcribe`),
  or render through an explicit lens

Deferred in 0.8 (see PAINT_DESIGN §3): an ``Exception`` renders as ``str(exc)``,
not ``render_traceback`` (that path is the framework-worn ``install()`` /
``PaintedHandler``); container dispatch keys on the concrete ``dict``/``list``/
``tuple``, so an abstract ``Mapping``/``Sequence`` renders via ``str``.

`show()` is a deprecated alias (removed at 1.0): it retains the pre-0.8 render
body and its sys.stdout-based detection, warns, and no longer honours `format`.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from .core.block import Block

# paint()'s closed kwarg surface is a public ABI; show carries a documented 1.0
# removal horizon. Both are semver-stable and guarded by test_public_api.py.
__all__ = ["paint", "show"]

_MISSING = object()


def _detect_context(stream: TextIO) -> tuple[bool, int]:
    """Resolve ``(use_ansi, width)`` — ANSI from the stream, width from ambient.

    Only ``use_ansi`` reads ``stream``: ANSI is a property of the destination
    (PAINT_DESIGN §8) — a real TTY renders ANSI, anything else (pipe, file,
    StringIO) renders plain. paint() passes the caller's ``file``; show() passes
    ``sys.stdout`` (bug-compatible — see show()). ``width`` does NOT consult the
    stream — it is ambient (``shutil.get_terminal_size`` → ``COLUMNS`` or, failing
    that, ``sys.__stdout__``), independent of where the paint is delivered.
    """
    use_ansi = hasattr(stream, "isatty") and stream.isatty()
    import shutil

    width = shutil.get_terminal_size().columns
    return use_ansi, width


def _render_and_deliver(
    subject: Any,
    zoom: int,
    lens: "Callable[[Any, int, int], Block] | None",
    file: TextIO,
    *,
    use_ansi: bool,
    width: int,
    render_default: "Callable[[Any, int, int], Block]",
) -> None:
    """Block passthrough, scalar short-circuit, else render through a lens.

    Shared by paint() and show(); they differ only in *which stream* detection
    reads and in ``render_default`` — Slice 2 swaps paint()'s to the
    transcription renderer while show() keeps ``shape_lens``.
    """
    # Block passthrough — avoid importing Block for common builtin payloads
    if (
        not isinstance(subject, (dict, list, set, frozenset, tuple, str, int, float, bool))
        and subject is not None
    ):
        from .core.block import Block

        if isinstance(subject, Block):
            from .core.writer import print_block

            print_block(subject, file, use_ansi=use_ansi)
            return

    # Scalars — no structure to inspect, just print (only on the no-lens path).
    # Enum is excluded: a StrEnum/IntEnum subclasses str/int but is a declared
    # schema (renders as Type.MEMBER), so it must reach the renderer, not str().
    if lens is None and (
        subject is None
        or (isinstance(subject, (str, int, float, bool)) and not isinstance(subject, Enum))
    ):
        file.write(str(subject))
        file.write("\n")
        file.flush()
        return

    # Rendered path — scope ASCII icons for plain output, restored on exit
    from .core.writer import print_block

    render_fn = lens or render_default
    if not use_ansi:
        from .icon_set import ASCII_ICONS, use_icons

        with use_icons(ASCII_ICONS):
            block = render_fn(subject, zoom, width)
    else:
        block = render_fn(subject, zoom, width)
    print_block(block, file, use_ansi=use_ansi)


def paint(
    subject: Any = _MISSING,
    *,
    zoom: int | None = None,
    lens: "Callable[[Any, int, int], Block] | None" = None,
    file: TextIO | None = None,
) -> None:
    """Render a subject onto a surface — the single entry point.

    With no lens, paint() transcribes what carries its own meaning; a lens
    interprets. ANSI vs plain is detected from ``file`` (default stdout); there
    is no ``format`` — JSON is a harness concern (``run_cli --json``). The kwarg
    surface is closed to the four meaning channels plus the destination; see
    docs/PAINT_DESIGN.md.

    Precedence: a ``Block`` subject is already painted, so it is delivered as-is
    and an explicit ``lens=`` is **ignored** for it (a lens interprets a raw
    value into a Block; a Block has nothing left to interpret). For every
    non-Block subject the lens wins over the transcription default — including
    scalars, so ``paint("hi", lens=spy)`` calls the lens.
    """
    out: TextIO = sys.stdout if file is None else file
    zoom = 2 if zoom is None else zoom  # Zoom.DETAILED

    # No args — blank line (the sole print() parity concession; §11 Slice 1 (a))
    if subject is _MISSING:
        out.write("\n")
        out.flush()
        return

    use_ansi, width = _detect_context(out)
    from .views.lens.shape import transcribe

    # paint()'s no-lens default TRANSCRIBES (never infers arrangement, at any
    # depth); a lens is taken only to interpret. show() keeps shape_lens.
    _render_and_deliver(
        subject, zoom, lens, out, use_ansi=use_ansi, width=width, render_default=transcribe
    )


def show(
    data: Any = _MISSING,
    *,
    zoom: int | None = None,
    lens: "Callable[[Any, int, int], Block] | None" = None,
    format: Any = "auto",
    file: TextIO | None = None,
) -> None:
    """Deprecated alias for paint() — removed in painted 1.0.

    Retains the pre-0.8 render body (the ``shape_lens``-inferring default) and
    its ``sys.stdout``-based detection, so existing output is unchanged **except**
    for two accepted drifts (PAINT_DESIGN §9): a top-level ``IntEnum``/``StrEnum``
    now renders ``Type.MEMBER`` (was ``str(value)`` via the scalar short-circuit),
    and a ``tuple`` now renders as an item list (was ``str()``). It warns and
    **no longer honours** ``format`` (warn-and-narrow): JSON/plain are a harness
    concern (``run_cli``). Use paint().
    """
    import warnings

    warnings.warn(
        "painted.show() is deprecated and will be removed in 1.0; use paint(). "
        "format= is no longer honoured — use run_cli for JSON/plain output.",
        DeprecationWarning,
        stacklevel=2,
    )
    out: TextIO = sys.stdout if file is None else file
    zoom = 2 if zoom is None else zoom  # Zoom.DETAILED

    # No args — blank line
    if data is _MISSING:
        out.write("\n")
        out.flush()
        return

    # Bug-compatible: detection reads sys.stdout, not `file` (the pre-0.8
    # behaviour). paint() fixes this; show() preserves it through the window.
    use_ansi, width = _detect_context(sys.stdout)
    from .views.lens.shape import shape_lens

    _render_and_deliver(
        data, zoom, lens, out, use_ansi=use_ansi, width=width, render_default=shape_lens
    )
