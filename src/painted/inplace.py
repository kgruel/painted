"""InPlaceRenderer: non-Surface terminal animation.

Animate Block output in-place without entering alt screen.

Each frame is emitted as ONE atomic write: cursor up, every line
overwritten in place (erase-to-EOL trims old residue), leftover lines
blanked only if the frame shrank — the screen always holds the old frame
or the new one, never a cleared region waiting for its redraw. The write
is wrapped in DEC 2026 synchronized-update markers so terminals that
support them (ghostty, kitty, iTerm2, WezTerm, ...) composite the frame
atomically; terminals that don't simply ignore the markers.

For CLI spinners, progress bars, and live-updating status.

Usage:
    from painted.inplace import InPlaceRenderer
    from painted import Block, Style

    with InPlaceRenderer() as renderer:
        for i in range(100):
            block = Block.text(f"Progress: {i}%", Style())
            renderer.render(block)
            time.sleep(0.05)
        renderer.finalize(Block.text("Done!", Style(fg="green")))
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO

from .core.writer import Writer, render_block_ansi

if TYPE_CHECKING:
    from .core.block import Block

# DEC private mode 2026: synchronized output. The terminal buffers
# everything between begin/end and composites it as one update.
_SYNC_BEGIN = "\x1b[?2026h"
_SYNC_END = "\x1b[?2026l"


class InPlaceRenderer:
    """Animate Block output in-place without alt screen.

    Pattern: hide cursor; per frame, one synchronized atomic write that
    moves up and overwrites; show cursor.
    """

    def __init__(self, stream: TextIO = sys.stdout):
        self._stream = stream
        self._writer = Writer(stream)
        self._height = 0  # lines written by last frame
        self._active = False

    def __enter__(self) -> InPlaceRenderer:
        """Enter context: hide cursor."""
        self._writer.hide_cursor()
        self._active = True
        return self

    def __exit__(self, *args) -> None:
        """Exit context: show cursor."""
        if self._active:
            self._writer.show_cursor()
            self._active = False

    def render(self, block: Block) -> None:
        """Render block, replacing previous output.

        First call: just write lines.
        Subsequent calls: move up and overwrite in place — no blank phase.
        The whole frame goes out as a single write so a line-buffered TTY
        can't expose a partially drawn state between flushes.
        """
        if not self._active:
            raise RuntimeError("InPlaceRenderer.render() called outside of a context manager")
        parts: list[str] = [_SYNC_BEGIN]
        if self._height > 0:
            parts.append(f"\x1b[{self._height}A")
        parts.append(render_block_ansi(block, self._writer, clear_eol=True))
        leftover = self._height - block.height
        if leftover > 0:
            # The new frame is shorter: blank the rows it no longer covers,
            # then park the cursor back at the end of the new content.
            parts.append("\x1b[2K\n" * leftover + f"\x1b[{leftover}A")
        parts.append(_SYNC_END)
        self._stream.write("".join(parts))
        self._stream.flush()
        self._height = block.height

    def clear(self) -> None:
        """Clear the last rendered content."""
        if not self._active:
            raise RuntimeError("InPlaceRenderer.clear() called outside of a context manager")
        if self._height > 0:
            h = self._height
            self._stream.write(f"\x1b[{h}A" + ("\x1b[2K\n" * h) + f"\x1b[{h}A")
            self._stream.flush()
            self._height = 0

    def finalize(self, block: Block | None = None) -> None:
        """Finalize output: clear, optionally print final block, show cursor.

        Call this to "lock in" a final state. The cursor is shown and
        positioned after the output.
        """
        if block is not None:
            self.render(block)

        if self._active:
            self._writer.show_cursor()
            self._active = False
