"""Span and Line: styled text primitives for the render layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from wcwidth import wcswidth

from ._text_width import char_width
from .buffer import BufferView
from .cell import Cell, Style

if TYPE_CHECKING:
    from .block import Block, Wrap


@dataclass(frozen=True, slots=True)
class Span:
    """A run of text with a single style — and optionally a single denotation.

    ``ref`` is the per-cell denotation channel (see ``docs/REFS_DESIGN.md``)
    stamped at the text-primitive rung: every cell this span's characters
    produce carries it, through ``to_block``, ``wrap`` (across line breaks),
    and ``paint`` alike — the same way the span's style rides its characters.
    """

    text: str
    style: Style = Style()
    ref: str | None = None

    @property
    def width(self) -> int:
        """Display width, accounting for wide characters."""
        w = wcswidth(self.text)
        if w < 0:
            # Fallback for strings containing non-printable chars
            return len(self.text)
        return w


@dataclass(frozen=True, slots=True)
class Line:
    """A sequence of spans forming a single line of styled text."""

    spans: tuple[Span, ...] = ()
    style: Style = Style()

    @classmethod
    def plain(cls, text: str, style: Style = Style()) -> Line:
        """Create a Line from a single unstyled (or uniformly styled) string."""
        return cls((Span(text, style),))

    @property
    def width(self) -> int:
        """Total display width across all spans."""
        return sum(s.width for s in self.spans)

    def paint(self, view: BufferView, x: int, y: int) -> None:
        """Render spans into a BufferView, merging base style onto each span.

        A span's ``ref`` is stamped on every cell it writes (and cleared where
        a ref-less span overwrites)."""
        col = x
        for span in self.spans:
            merged = self.style.merge(span.style)
            view.put_text(col, y, span.text, merged, ref=span.ref)
            col += span.width

    def truncate(self, max_width: int) -> Line:
        """Return a new Line truncated to max_width display columns."""
        remaining = max_width
        kept: list[Span] = []
        for span in self.spans:
            sw = span.width
            if sw <= remaining:
                kept.append(span)
                remaining -= sw
            else:
                # Cut this span character by character
                chars: list[str] = []
                used = 0
                for ch in span.text:
                    cw = wcswidth(ch)
                    if cw < 0:
                        cw = 1
                    if used + cw > remaining:
                        break
                    chars.append(ch)
                    used += cw
                if chars:
                    kept.append(Span("".join(chars), span.style, span.ref))
                break
        return Line(spans=tuple(kept), style=self.style)

    def wrap(self, width: int, *, wrap: Wrap | None = None) -> Block:
        """Reflow this multi-style Line to `width`, returning a multi-row Block.

        The multi-line generalization of `to_block` (which is single-line
        `Wrap.NONE`): each span's style is merged onto the Line style and rides
        with its characters across line breaks. `wrap` mirrors `Block.text`'s
        modes exactly — the same operation `Block.text(..., wrap=...)` gives a
        single-style `str`, one rung up in style richness. Defaults to
        `Wrap.WORD`. Pad cells and the ELLIPSIS marker inherit the Line's base
        style.
        """
        from .block import Wrap, _wrap_styled

        if wrap is None:
            wrap = Wrap.WORD

        chars = [
            (ch, self.style.merge(span.style), span.ref) for span in self.spans for ch in span.text
        ]
        return _wrap_styled(chars, width, wrap=wrap, pad_style=self.style)

    def to_block(self, width: int | None) -> Block:
        """Convert this Line to a Block of the given width.

        Builds cells directly from spans, merging Line style onto each span.
        Pads with empty cells if Line is shorter than width.
        Truncates if Line is longer than width.
        ``width=None`` sizes naturally (the width contract: absent is natural) —
        the Block takes the Line's own display width.
        """
        from .block import Block

        if width is None:
            width = self.width
        if width <= 0:
            return Block([[]], 0)

        cells: list[Cell] = []
        refs: list[str | None] | None = None
        used = 0
        done = False
        for span in self.spans:
            merged = self.style.merge(span.style)
            if span.ref is not None and refs is None:
                refs = cast("list[str | None]", [None] * len(cells))
            for ch in span.text:
                w = char_width(ch)
                if w == 0:
                    # Zero-width (combining) characters aren't representable as separate cells.
                    continue
                if used + w > width:
                    done = True
                    break
                cells.append(Cell(ch, merged))
                if refs is not None:
                    refs.append(span.ref)
                if w == 2:
                    # Placeholder cell for wide characters.
                    if used + 2 > width:
                        cells.pop()
                        if refs is not None:
                            refs.pop()
                        done = True
                        break
                    cells.append(Cell(" ", merged))
                    if refs is not None:
                        refs.append(span.ref)
                used += w
                if used >= width:
                    done = True
                    break
            if done:
                break

        # Pad to width
        if used < width:
            pad = Cell(" ", self.style)
            cells.extend([pad] * (width - used))

        if refs is not None:
            refs.extend([None] * (width - len(refs)))
            return Block([cells], width, refs=[refs])
        return Block([cells], width)
