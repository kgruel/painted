"""InPlaceRenderer: ephemeral liveness in the scrollback.

Animate Block output in-place without entering alt screen.

CONTRACT (see docs/LIVE_DELIVERY_DESIGN.md): this renderer is for
short-lived liveness — spinners, progress, status — where the final state
belonging to terminal history is the point. Its relative cursor addressing
is structurally fragile under viewport disturbance: scrolling during a
render lands writes on the wrong visual rows (tearing, reprinted frames).
Sustained animation belongs on the alt screen (Surface), which is immune.

OVERSIZED FRAMES (declared behavior — LIVE_DELIVERY_DESIGN §10, ratified
0.10): a live frame taller than the viewport cannot be repainted (its top
rows are already released to scrollback), so on a TTY ``render()`` **clips
with evidence** — the top rows survive and a dim ``… +N rows`` marker takes
the last line. ``finalize()``'s deposit writes full height (nothing repaints
after it; history keeps everything), and a non-TTY stream has no viewport,
so it is never clipped.

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

from .core.errors import LifecycleError
from .core.writer import Writer, render_block_ansi, render_row_ansi

if TYPE_CHECKING:
    from .core.block import Block

# DEC private mode 2026: synchronized output. The terminal buffers
# everything between begin/end and composites it as one update.
_SYNC_BEGIN = "\x1b[?2026h"
_SYNC_END = "\x1b[?2026l"


def _viewport_rows(stream: TextIO) -> int | None:
    """The stream's viewport height, or ``None`` when it has none.

    Only a TTY has a viewport to tear against; a pipe/StringIO frame is
    never clipped. Geometry is ambient (``shutil.get_terminal_size``), the
    same source the framework's ``detect_context`` reads — reading it here
    is delivery-layer territory, not fidelity resolution (law 4 constrains
    the latter).
    """
    try:
        if not stream.isatty():
            return None
    except (AttributeError, ValueError):
        return None
    import shutil

    return shutil.get_terminal_size().lines


def _ref_row(block: Block, y: int):
    """The ref row for a block row: per-cell grid, uniform block ref, or None.

    Local to keep the arch invariant (a public module must not import a private
    sibling symbol) — the same 3-branch idiom compose.py inlines throughout.
    """
    if block._refs is not None:
        return block._refs[y]
    if block.ref is not None:
        return (block.ref,) * block.width
    return None


class InPlaceRenderer:
    """Animate Block output in-place without alt screen.

    Pattern: hide cursor; per frame, one synchronized atomic write that
    moves up and overwrites; show cursor.
    """

    def __init__(self, stream: TextIO = sys.stdout):
        self._stream = stream
        self._writer = Writer(stream)
        self._height = 0  # lines written by last frame
        self._prev: Block | None = None  # last rendered frame, for row diffing
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

        First call (or height change): full write, overwriting in place.
        Same-height redraws DIFF against the previous frame: unchanged rows
        are hopped over with cursor-down, only changed rows are rewritten —
        the write shrinks to the churn, not the frame. Either way the frame
        goes out as one write wrapped in synchronized-update markers, so a
        line-buffered TTY can't expose a partially drawn state.

        A frame taller than the viewport is clipped with evidence (module
        contract): the top rows survive and a dim ``… +N rows`` marker takes
        the last line — the alternative is silent tearing on the next redraw.
        """
        if not self._active:
            raise LifecycleError("InPlaceRenderer.render() called outside of a context manager")
        self._render_frame(self._fit_viewport(block))

    def _fit_viewport(self, block: Block) -> Block:
        """Clip a frame taller than the viewport, marking the cut."""
        rows = _viewport_rows(self._stream)
        if rows is None or block.height <= rows:
            return block
        from .core.block import Block as _Block
        from .core.cell import Style
        from .core.compose import join_vertical, vslice
        from .icon_set import current_icons

        kept = max(0, rows - 1)
        marker = f"{current_icons().ellipsis} +{block.height - kept} rows"
        evidence = _Block.text(marker, Style(dim=True))
        return join_vertical(vslice(block, 0, kept), evidence, gap=0)

    def _render_frame(self, block: Block) -> None:
        """Write a frame as-is — the shared body behind render/finalize."""
        parts: list[str] = [_SYNC_BEGIN]
        if self._prev is not None and self._prev.height == block.height:
            parts.append(f"\x1b[{self._height}A")
            skip = 0  # unchanged rows pending a cursor hop
            for row_idx in range(block.height):
                # Row equality includes the ref row: a ref-only change (same
                # glyphs + style, different denotation) must still redraw, or a
                # stale hyperlink lingers on screen (design §5).
                if block.row(row_idx) == self._prev.row(row_idx) and _ref_row(
                    block, row_idx
                ) == _ref_row(self._prev, row_idx):
                    skip += 1
                    continue
                if skip:
                    parts.append(f"\x1b[{skip}B")
                    skip = 0
                parts.append(render_row_ansi(block, row_idx, self._writer, clear_eol=True))
                parts.append("\n")
            if skip:
                parts.append(f"\x1b[{skip}B")
        else:
            if self._height > 0:
                parts.append(f"\x1b[{self._height}A")
            parts.append(render_block_ansi(block, self._writer, clear_eol=True))
            leftover = self._height - block.height
            if leftover > 0:
                # The new frame is shorter: blank the rows it no longer
                # covers, then park the cursor at the end of the new content.
                parts.append("\x1b[2K\n" * leftover + f"\x1b[{leftover}A")
        parts.append(_SYNC_END)
        self._stream.write("".join(parts))
        self._stream.flush()
        self._height = block.height
        self._prev = block

    def clear(self) -> None:
        """Clear the last rendered content."""
        if not self._active:
            raise LifecycleError("InPlaceRenderer.clear() called outside of a context manager")
        if self._height > 0:
            h = self._height
            self._stream.write(f"\x1b[{h}A" + ("\x1b[2K\n" * h) + f"\x1b[{h}A")
            self._stream.flush()
            self._height = 0
            self._prev = None  # the screen is blank — nothing to diff against

    def finalize(self, block: Block | None = None) -> None:
        """Finalize output: clear, optionally print final block, show cursor.

        Call this to "lock in" a final state. The cursor is shown and
        positioned after the output. The deposit writes FULL height — it
        belongs to terminal history and nothing repaints after it, so the
        oversized-frame clip does not apply (LIVE_DELIVERY_DESIGN §10).
        """
        if block is not None:
            if not self._active:
                raise LifecycleError(
                    "InPlaceRenderer.finalize() called outside of a context manager"
                )
            self._render_frame(block)

        if self._active:
            self._writer.show_cursor()
            self._active = False
