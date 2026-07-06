"""Buffer: 2D grid of Cells with diff and region support."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import cast

from wcwidth import wcwidth

from ._row_ops import blank_cell
from .cell import EMPTY_CELL, Cell, Style


@dataclass(frozen=True, slots=True)
class CellWrite:
    """A single cell change: position + new cell value (+ optional denotation ref)."""

    x: int
    y: int
    cell: Cell
    ref: str | None = None


class Buffer:
    """2D grid of Cells, row-major flat list for cache efficiency."""

    __slots__ = ("width", "height", "_cells", "_refs")

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self._cells: list[Cell] = [EMPTY_CELL] * (width * height)
        self._refs: list[str | None] | None = None

    def __setstate__(self, state: tuple[object, dict[str, object]]) -> None:
        # Pickles written by painted <= 0.6 carry the pre-rename slot name
        # (_ids); remap so they restore into the renamed slot. Removed at 1.0
        # with the rest of the id= alias surface.
        _, slots = state
        if "_ids" in slots:
            slots["_refs"] = slots.pop("_ids")
        for name, value in slots.items():
            object.__setattr__(self, name, value)

    def _ensure_refs(self) -> list[str | None]:
        if self._refs is None:
            self._refs = cast(list[str | None], [None] * (self.width * self.height))
        return self._refs

    def _index(self, x: int, y: int) -> int | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return y * self.width + x
        return None

    def get(self, x: int, y: int) -> Cell:
        idx = self._index(x, y)
        if idx is None:
            return EMPTY_CELL
        return self._cells[idx]

    def put(self, x: int, y: int, char: str, style: Style) -> None:
        """Set a single cell. Out-of-bounds writes are silently ignored."""
        idx = self._index(x, y)
        if idx is None:
            return
        self._cells[idx] = Cell(char, style)
        if self._refs is not None:
            self._refs[idx] = None

    def put_ref(self, x: int, y: int, char: str, style: Style, ref: str) -> None:
        """Set a single cell and record a semantic ref for hit-testing."""
        idx = self._index(x, y)
        if idx is None:
            return
        self._cells[idx] = Cell(char, style)
        self._ensure_refs()[idx] = ref

    def put_id(self, x: int, y: int, char: str, style: Style, id: str) -> None:
        """Deprecated alias for :meth:`put_ref` (removed at 1.0)."""
        warnings.warn(
            "Buffer.put_id is deprecated; use Buffer.put_ref",
            DeprecationWarning,
            stacklevel=2,
        )
        self.put_ref(x, y, char, style, id)

    def put_text(self, x: int, y: int, text: str, style: Style) -> None:
        """Write a string horizontally, respecting wide characters."""
        col = x
        blank = blank_cell(style)
        for ch in text:
            w = wcwidth(ch)
            if w < 0:
                # Non-printable — skip
                continue
            if w == 0:
                # Zero-width (combining) — skip
                continue
            if w == 1:
                idx = self._index(col, y)
                if idx is not None:
                    self._cells[idx] = Cell(ch, style)
                    if self._refs is not None:
                        self._refs[idx] = None
                col += w
                continue

            # Only write a wide glyph when it fully fits; otherwise blank the
            # visible overlap so the row stays column-valid.
            if 0 <= col and col + w <= self.width and 0 <= y < self.height:
                idx = self._index(col, y)
                if idx is not None:
                    self._cells[idx] = Cell(ch, style)
                    if self._refs is not None:
                        self._refs[idx] = None
                for dx in range(1, w):
                    next_idx = self._index(col + dx, y)
                    if next_idx is not None:
                        self._cells[next_idx] = blank
                        if self._refs is not None:
                            self._refs[next_idx] = None
            else:
                for dx in range(w):
                    idx = self._index(col + dx, y)
                    if idx is not None:
                        self._cells[idx] = blank
                        if self._refs is not None:
                            self._refs[idx] = None
            col += w

    def fill(self, x: int, y: int, w: int, h: int, char: str, style: Style) -> None:
        """Fill a rectangular region with a character+style."""
        cell = Cell(char, style)
        for row in range(y, y + h):
            for col in range(x, x + w):
                idx = self._index(col, row)
                if idx is not None:
                    self._cells[idx] = cell
                    if self._refs is not None:
                        self._refs[idx] = None

    def region(self, x: int, y: int, w: int, h: int) -> BufferView:
        """Return a view that translates coordinates to a sub-region."""
        return BufferView(self, x, y, w, h)

    def hit(self, x: int, y: int) -> str | None:
        """Return the semantic ref at (x, y), if any."""
        idx = self._index(x, y)
        if idx is None or self._refs is None:
            return None
        return self._refs[idx]

    def diff(self, other: Buffer) -> list[CellWrite]:
        """Compare with another buffer, return list of cells that differ.

        ``self`` is the new buffer; every emitted write carries ``self``'s ref
        for its cell. Ref slots are compared whenever *either* buffer has a ref
        grid allocated, so a same-glyph/same-style cell whose only change is its
        ref still emits a write — the stale-hyperlink blind spot (design §5).
        When neither side has a ref grid — the common case — the fast
        list-equality short-circuit stays.
        """
        width = self.width
        cells = self._cells
        self_refs = self._refs

        if width != other.width or self.height != other.height:
            # Dimension mismatch: treat every cell as changed. This avoids IndexError
            # and ensures coordinates are computed against `self`'s stride. Refs come
            # from the new buffer (self).
            return [
                CellWrite(
                    i % width,
                    i // width,
                    cell,
                    self_refs[i] if self_refs is not None else None,
                )
                for i, cell in enumerate(cells)
            ]

        other_cells = other._cells
        other_refs = other._refs
        has_refs = self_refs is not None or other_refs is not None
        if not has_refs and cells == other_cells:
            return []

        writes: list[CellWrite] = []
        append = writes.append
        for i, cell in enumerate(cells):
            other_cell = other_cells[i]
            cell_same = cell is other_cell or cell == other_cell
            if has_refs:
                self_ref = self_refs[i] if self_refs is not None else None
                other_ref = other_refs[i] if other_refs is not None else None
                if cell_same and self_ref == other_ref:
                    continue
                append(CellWrite(i % width, i // width, cell, self_ref))
            elif not cell_same:
                append(CellWrite(i % width, i // width, cell))
        return writes

    def line_hashes(self, *, include_style: bool = True) -> list[int]:
        """Return a hash for each line.

        This is used for fast line-level comparison (e.g. scroll detection).
        Hashes are only meaningful within the current process and should not be
        persisted.

        The full hash (``include_style=True``) also mixes in the ref grid —
        it feeds repaint selection, and a line whose only change is a ref must
        not hash equal or the scroll-optimized flush leaves a stale hyperlink.
        The content hash (``include_style=False``) stays cells-only: it feeds
        scroll *detection*, and moved content is the same scroll regardless of
        its refs. A row of all-``None`` refs hashes identically to no grid.
        """
        w, h = self.width, self.height
        refs = self._refs if include_style else None
        out: list[int] = [0] * h
        idx = 0
        for y in range(h):
            v = 0x345678
            for _ in range(w):
                c = self._cells[idx]
                if include_style:
                    hv = hash(c)
                    if refs is not None:
                        r = refs[idx]
                        if r is not None:
                            hv ^= hash(r)
                else:
                    hv = hash(c.char)
                idx += 1
                v = (v * 1000003) ^ hv
            out[y] = v
        return out

    def scroll_region_in_place(
        self,
        top: int,
        bottom: int,
        n: int,
        *,
        fill: Cell = EMPTY_CELL,
    ) -> None:
        """Scroll a vertical region in-place by n lines.

        top/bottom are 0-based inclusive. Positive n scrolls up (content moves up),
        negative n scrolls down. Newly uncovered lines are filled with `fill`.
        """
        if n == 0:
            return

        top = max(0, top)
        bottom = min(self.height - 1, bottom)
        if top > bottom:
            return

        height = bottom - top + 1
        if abs(n) >= height:
            # Entire region becomes blank.
            for y in range(top, bottom + 1):
                start = y * self.width
                self._cells[start : start + self.width] = [fill] * self.width
                if self._refs is not None:
                    self._refs[start : start + self.width] = [None] * self.width
            return

        w = self.width

        if n > 0:
            # Scroll up: copy rows downwards in index space.
            for y in range(top, bottom - n + 1):
                dst = y * w
                src = (y + n) * w
                self._cells[dst : dst + w] = self._cells[src : src + w]
                if self._refs is not None:
                    self._refs[dst : dst + w] = self._refs[src : src + w]
            for y in range(bottom - n + 1, bottom + 1):
                start = y * w
                self._cells[start : start + w] = [fill] * w
                if self._refs is not None:
                    self._refs[start : start + w] = [None] * w
        else:
            m = -n
            # Scroll down: copy rows upwards in index space (descending y).
            for y in range(bottom, top + m - 1, -1):
                dst = y * w
                src = (y - m) * w
                self._cells[dst : dst + w] = self._cells[src : src + w]
                if self._refs is not None:
                    self._refs[dst : dst + w] = self._refs[src : src + w]
            for y in range(top, top + m):
                start = y * w
                self._cells[start : start + w] = [fill] * w
                if self._refs is not None:
                    self._refs[start : start + w] = [None] * w

    def clone(self) -> Buffer:
        """Deep copy for diff comparison."""
        buf = object.__new__(Buffer)
        buf.width = self.width
        buf.height = self.height
        buf._cells = self._cells.copy()  # Cells are frozen, shallow copy is fine
        buf._refs = self._refs.copy() if self._refs is not None else None
        return buf


class BufferView:
    """A clipped view into a Buffer with coordinate translation."""

    __slots__ = ("_buffer", "_ox", "_oy", "_w", "_h")

    def __init__(self, buffer: Buffer, ox: int, oy: int, w: int, h: int):
        self._buffer = buffer
        self._ox = ox
        self._oy = oy
        self._w = w
        self._h = h

    @property
    def width(self) -> int:
        return self._w

    @property
    def height(self) -> int:
        return self._h

    def _clip(self, x: int, y: int) -> tuple[int, int] | None:
        """Translate and clip. Returns absolute coords or None if out of bounds."""
        if 0 <= x < self._w and 0 <= y < self._h:
            return (self._ox + x, self._oy + y)
        return None

    def put(self, x: int, y: int, char: str, style: Style) -> None:
        pos = self._clip(x, y)
        if pos:
            self._buffer.put(pos[0], pos[1], char, style)

    def put_ref(self, x: int, y: int, char: str, style: Style, ref: str) -> None:
        pos = self._clip(x, y)
        if pos:
            self._buffer.put_ref(pos[0], pos[1], char, style, ref)

    def put_id(self, x: int, y: int, char: str, style: Style, id: str) -> None:
        """Deprecated alias for :meth:`put_ref` (removed at 1.0)."""
        warnings.warn(
            "BufferView.put_id is deprecated; use BufferView.put_ref",
            DeprecationWarning,
            stacklevel=2,
        )
        self.put_ref(x, y, char, style, id)

    def put_text(self, x: int, y: int, text: str, style: Style) -> None:
        """Write text, clipping characters that fall outside the view."""
        col = x
        blank = blank_cell(style)
        for ch in text:
            w = wcwidth(ch)
            if w <= 0:
                continue

            if w == 1:
                if 0 <= col < self._w and 0 <= y < self._h:
                    self._buffer.put(self._ox + col, self._oy + y, ch, style)
                col += w
                continue

            if 0 <= col and col + w <= self._w and 0 <= y < self._h:
                self._buffer.put(self._ox + col, self._oy + y, ch, style)
                for dx in range(1, w):
                    self._buffer.put(self._ox + col + dx, self._oy + y, " ", style)
            else:
                for dx in range(w):
                    px = col + dx
                    if 0 <= px < self._w and 0 <= y < self._h:
                        self._buffer.put(self._ox + px, self._oy + y, blank.char, blank.style)
            col += w

    def fill(self, x: int, y: int, w: int, h: int, char: str, style: Style) -> None:
        """Fill a region, clipping to view bounds."""
        for row in range(y, y + h):
            for col in range(x, x + w):
                pos = self._clip(col, row)
                if pos:
                    self._buffer.put(pos[0], pos[1], char, style)

    def hit(self, x: int, y: int) -> str | None:
        """Return the semantic ref at a local coordinate (or None)."""
        pos = self._clip(x, y)
        if not pos:
            return None
        return self._buffer.hit(pos[0], pos[1])
