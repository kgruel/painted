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
    from .cli.types import Format, Zoom

_MISSING = object()


def show(
    data: Any = _MISSING,
    *,
    zoom: "Zoom | None" = None,
    lens: "Callable[[Any, int, int], Block] | None" = None,
    format: "Format | None" = None,
    file: TextIO = sys.stdout,
) -> None:
    """Display data with auto-detected formatting.

    Four paths:
    - No args: blank line (like print())
    - Block: print directly via print_block
    - JSON format (piped or explicit): json.dumps with default=str
    - Otherwise: render through lens (default shape_lens) then print_block

    Args:
        data: Any Python value, or a pre-built Block. Omit for blank line.
        zoom: Detail level (default SUMMARY).
        lens: Render function override (default: shape_lens).
        format: Force output format (default: auto-detect from TTY).
        file: Output stream (default: sys.stdout).
    """
    from .cli.types import Format, OutputMode, Zoom

    if zoom is None:
        zoom = Zoom.DETAILED
    if format is None:
        format = Format.AUTO

    # No args — blank line
    if data is _MISSING:
        file.write("\n")
        file.flush()
        return

    # Resolve format to bools — JSON short-circuits, plain suppresses ANSI
    is_json = format == Format.JSON
    force_plain = format == Format.PLAIN

    # Block passthrough — already rendered, no icon resolution needed
    from .core.block import Block

    if isinstance(data, Block):
        from .cli.context import detect_context
        from .core.writer import print_block

        if is_json:
            # Can't JSON-serialize a Block, fall through to ANSI/plain
            pass
        ctx = detect_context(zoom, OutputMode.AUTO, force_plain=force_plain)
        print_block(data, file, use_ansi=ctx.use_ansi)
        return

    # JSON path — serialize directly, bypasses render pipeline
    if is_json:
        file.write(json.dumps(data, default=str))
        file.write("\n")
        file.flush()
        return

    # Detect output context
    from .cli.context import detect_context

    ctx = detect_context(zoom, OutputMode.AUTO, force_plain=force_plain)

    # Scalars — no structure to inspect, just print
    if lens is None and (data is None or isinstance(data, (str, int, float, bool))):
        file.write(str(data))
        file.write("\n")
        file.flush()
        return

    # Rendered path — scope ASCII icons for plain output, restored on exit
    from contextlib import nullcontext

    from .core.writer import print_block
    from .icon_set import ASCII_ICONS, use_icons
    from .views.lens import shape_lens

    icons_scope = use_icons(ASCII_ICONS) if not ctx.use_ansi else nullcontext()
    render_fn = lens or shape_lens
    with icons_scope:
        block = render_fn(data, ctx.zoom, ctx.width)
    print_block(block, file, use_ansi=ctx.use_ansi)
