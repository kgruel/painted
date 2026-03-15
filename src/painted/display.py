"""show() — auto-formatting display for any Python value.

Four paths:
- No args: blank line (like print())
- Block: print directly via print_block
- JSON format (piped or explicit): json.dumps with default=str
- Otherwise: render through lens (default shape_lens) then print_block
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from contextlib import nullcontext
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from .core.block import Block

_MISSING = object()


def _format_value(fmt: Any) -> str:
    if hasattr(fmt, "value"):
        return str(fmt.value)
    return str(fmt)


def _detect_show_context(force_plain: bool) -> tuple[bool, int]:
    stdout = sys.stdout
    is_tty = hasattr(stdout, "isatty") and stdout.isatty()
    use_ansi = (not force_plain) and is_tty
    width = shutil.get_terminal_size().columns
    return use_ansi, width


def show(
    data: Any = _MISSING,
    *,
    zoom: int | None = None,
    lens: "Callable[[Any, int, int], Block] | None" = None,
    format: Any = "auto",
    file: TextIO = sys.stdout,
) -> None:
    """Display data with auto-detected formatting."""
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

    # Block passthrough — already rendered, no icon resolution needed
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
    from .icon_set import ASCII_ICONS, use_icons
    from .views.lens.shape import shape_lens

    icons_scope = use_icons(ASCII_ICONS) if not use_ansi else nullcontext()
    render_fn = lens or shape_lens
    with icons_scope:
        block = render_fn(data, zoom, width)
    print_block(block, file, use_ansi=use_ansi)
