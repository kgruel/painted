"""show() — auto-formatting display for any Python value.

Four paths:
- No args: blank line (like print())
- Block: print directly via print_block
- JSON format (piped or explicit): json.dumps with default=str
- Otherwise: render through lens (default shape_lens) then print_block
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from .core.block import Block

_MISSING = object()


def _format_value(fmt: Any) -> str:
    if isinstance(fmt, str):
        return fmt
    value = getattr(fmt, "value", None)
    if isinstance(value, str):
        return value
    return str(fmt)


def _detect_show_context(force_plain: bool) -> tuple[bool, int]:
    if force_plain:
        use_ansi = False
    else:
        stdout = sys.stdout
        is_tty = stdout.isatty()
        use_ansi = is_tty

    import shutil

    width = shutil.get_terminal_size().columns
    return use_ansi, width


def show(
    data: Any = _MISSING,
    *,
    zoom: int | None = None,
    lens: "Callable[[Any, int, int], Block] | None" = None,
    format: Any = "auto",
    file: TextIO | None = None,
) -> None:
    """Display data with auto-detected formatting."""
    if file is None:
        file = sys.stdout
    if zoom is None:
        zoom = 2  # Zoom.DETAILED

    # No args — blank line
    if data is _MISSING:
        file.write("\n")
        file.flush()
        return

    fmt = _format_value(format)
    is_json = fmt == "json"
    force_plain = fmt == "plain"

    # Block passthrough — avoid importing Block for common builtin payloads
    if not isinstance(data, (dict, list, set, tuple, str, int, float, bool)) and data is not None:
        from .core.block import Block

        if isinstance(data, Block):
            from .core.writer import print_block

            use_ansi, _width = _detect_show_context(force_plain)
            print_block(data, file, use_ansi=use_ansi)
            return

    # JSON path — serialize directly, bypasses render pipeline
    if is_json:
        file.write(json.dumps(data, default=str))
        file.write("\n")
        file.flush()
        return

    use_ansi, width = _detect_show_context(force_plain)

    # Scalars — no structure to inspect, just print
    if lens is None and (data is None or isinstance(data, (str, int, float, bool))):
        file.write(str(data))
        file.write("\n")
        file.flush()
        return

    # Rendered path — scope ASCII icons for plain output, restored on exit
    from .core.writer import print_block
    from .views.lens.shape import shape_lens

    render_fn = lens or shape_lens
    if not use_ansi:
        from .icon_set import ASCII_ICONS, use_icons

        with use_icons(ASCII_ICONS):
            block = render_fn(data, zoom, width)
    else:
        block = render_fn(data, zoom, width)
    print_block(block, file, use_ansi=use_ansi)
