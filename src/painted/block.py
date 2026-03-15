"""Block: immutable rectangle of styled cells with known dimensions."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import cast

from ._text_width import char_width, display_width
from .buffer import Buffer, BufferView
from .cell import Cell, Style


# Internal cell cache: maps Style → dict of char → Cell for ASCII characters.
_style_cell_maps: dict[Style, dict[str, Cell]] = {}


def _get_cell_map(style: Style) -> dict[str, Cell]:
    """Return a char→Cell map for the given style, creating lazily."""
    m = _style_cell_maps.get(style)
    if m is not None:
        return m
    m = {}
    _style_cell_maps[style] = m
    return m


def _ascii_cells(text: str, style: Style) -> list[Cell]:
    """Convert ASCII text to cached Cell list using fast map() lookup."""
    m = _style_cell_maps.get(style)
    if m is None:
        m = {}
        _style_cell_maps[style] = m
    for ch in text:
        if ch not in m:
            m[ch] = Cell(ch, style)
    return list(map(m.__getitem__, text))


def _cached_cell(char: str, style: Style) -> Cell:
    """Return a cached Cell for single ASCII characters."""
    m = _style_cell_maps.get(style)
    if m is not None:
        cell = m.get(char)
        if cell is not None:
            return cell
        cell = Cell(char, style)
        m[char] = cell
        return cell
    m = {}
    _style_cell_maps[style] = m
    cell = Cell(char, style)
    m[char] = cell
    return cell


class Wrap(Enum):
    NONE = "none"  # single line, truncate at width
    CHAR = "char"  # break at any character
    WORD = "word"  # break at word boundaries
    ELLIPSIS = "ellipsis"  # truncate with "…"


def _freeze_cell_rows(rows: Sequence[Sequence[Cell]]) -> tuple[tuple[Cell, ...], ...]:
    n = len(rows)
    if n == 1:
        r = rows[0]
        return (cast(tuple[Cell, ...], r) if isinstance(r, tuple) else tuple(r),)
    frozen: list[tuple[Cell, ...]] = []
    for row in rows:
        frozen.append(cast(tuple[Cell, ...], row) if isinstance(row, tuple) else tuple(row))
    return tuple(frozen)


def _freeze_id_rows(
    rows: Sequence[Sequence[str | None]],
) -> tuple[tuple[str | None, ...], ...]:
    frozen: list[tuple[str | None, ...]] = []
    for row in rows:
        frozen.append(cast(tuple[str | None, ...], row) if isinstance(row, tuple) else tuple(row))
    return tuple(frozen)


class Block:
    """Immutable rectangle of styled cells with known dimensions."""

    __slots__ = ("width", "height", "id", "_rows", "_ids", "_frozen")

    def __init__(
        self,
        rows: Sequence[Sequence[Cell]],
        width: int,
        *,
        id: str | None = None,
        ids: Sequence[Sequence[str | None]] | None = None,
    ):
        frozen_rows = _freeze_cell_rows(rows)
        frozen_ids = _freeze_id_rows(ids) if ids is not None else None
        for row_idx, row in enumerate(frozen_rows):
            if len(row) != width:
                raise ValueError(f"Block row {row_idx} width {len(row)} != block width {width}")
        if frozen_ids is not None:
            if len(frozen_ids) != len(frozen_rows):
                raise ValueError(
                    f"Block ids height {len(frozen_ids)} != block height {len(frozen_rows)}"
                )
            for row_idx, row in enumerate(frozen_ids):
                if len(row) != width:
                    raise ValueError(
                        f"Block ids row {row_idx} width {len(row)} != block width {width}"
                    )
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", len(frozen_rows))
        object.__setattr__(self, "id", id)
        object.__setattr__(self, "_rows", frozen_rows)
        object.__setattr__(self, "_ids", frozen_ids)
        object.__setattr__(self, "_frozen", True)

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError(f"{type(self).__name__} is immutable")
        object.__setattr__(self, name, value)

    @staticmethod
    def text(
        content: str,
        style: Style,
        *,
        width: int | None = None,
        wrap: Wrap = Wrap.NONE,
        id: str | None = None,
    ) -> Block:
        """Create a block from text content with optional wrapping."""
        if width is not None and width <= 0:
            return Block([[]], 0, id=id)

        if width is None:
            cells = _cells_from_text(content, style)
            return Block([cells], len(cells), id=id)

        if wrap == Wrap.NONE:
            # Truncate at width, single line
            if content.isascii():
                cells = _ascii_cells(content[:width], style)
                cells = _pad_row(cells, width, style)
                return Block([cells], width, id=id)
            cells = _cells_from_text(content, style, max_width=width)
            cells = _pad_row(cells, width, style)
            return Block([cells], width, id=id)

        if wrap == Wrap.ELLIPSIS:
            # Truncate with ellipsis if needed
            if content.isascii():
                if content[width:]:
                    if width == 1:
                        cells = [Cell("…", style)]
                    else:
                        cells = _ascii_cells(content[: width - 1], style)
                        cells.append(Cell("…", style))
                else:
                    cells = _ascii_cells(content, style)
                cells = _pad_row(cells, width, style)
                return Block([cells], width, id=id)
            if display_width(content) > width:
                if width == 1:
                    cells = [Cell("…", style)]
                else:
                    cells = _cells_from_text(content, style, max_width=width - 1)
                    cells.append(Cell("…", style))
            else:
                cells = _cells_from_text(content, style, max_width=width)
            cells = _pad_row(cells, width, style)
            return Block([cells], width, id=id)

        if wrap == Wrap.CHAR:
            # Break at any character boundary
            rows = _char_wrap(content, width, style)
            return Block(rows, width, id=id)

        if wrap == Wrap.WORD:
            # Break at word boundaries
            lines = _word_wrap(content, width)
            rows = [
                _pad_row(_cells_from_text(line, style, max_width=width), width, style)
                for line in lines
            ]
            return Block(rows, width, id=id)

        raise ValueError(f"Unknown wrap mode: {wrap}")

    @staticmethod
    def column(
        rows: Sequence[tuple[str, Style]],
        *,
        width: int | None = None,
        id: str | None = None,
    ) -> Block:
        """Create a block from per-row (text, style) pairs.

        Each entry becomes one row. Width is inferred from the first row's
        display width if not given explicitly; all rows are padded/truncated
        to match.
        """
        if not rows:
            return Block([], 0, id=id)

        if width is None:
            width = display_width(rows[0][0])

        cell_rows: list[list[Cell]] = []
        for text, style in rows:
            cells = _cells_from_text(text, style, max_width=width)
            cells = _pad_row(cells, width, style)
            cell_rows.append(cells)

        return Block(cell_rows, width, id=id)

    @staticmethod
    def empty(width: int, height: int, style: Style = Style(), *, id: str | None = None) -> Block:
        """Create a block filled with space cells."""
        space = Cell(" ", style)
        rows = [[space] * width for _ in range(height)]
        return Block(rows, width, id=id)

    def paint(self, buffer: Buffer | BufferView, x: int = 0, y: int = 0) -> None:
        """Transfer cells into a buffer region. Clips to buffer bounds."""
        if isinstance(buffer, Buffer):
            left = max(x, 0)
            top = max(y, 0)
            right = min(x + self.width, buffer.width)
            bottom = min(y + self.height, buffer.height)
            if left >= right or top >= bottom:
                return

            src_x = left - x
            src_end = src_x + (right - left)
            span = src_end - src_x
            dst_cells = buffer._cells
            dst_ids = buffer._ids
            buffer_width = buffer.width
            rows = self._rows

            if self._ids is None:
                if self.id is None:
                    clear_ids = [None] * span if dst_ids is not None else None
                    start = top * buffer_width + left
                    for by in range(top, bottom):
                        src_row = rows[by - y]
                        dst_cells[start : start + span] = src_row[src_x:src_end]
                        if dst_ids is not None and clear_ids is not None:
                            dst_ids[start : start + span] = clear_ids
                        start += buffer_width
                    return

                ids = buffer._ensure_ids()
                row_ids = [self.id] * span
                start = top * buffer_width + left
                for by in range(top, bottom):
                    src_row = rows[by - y]
                    dst_cells[start : start + span] = src_row[src_x:src_end]
                    ids[start : start + span] = row_ids
                    start += buffer_width
                return

            ids = buffer._ensure_ids()
            src_ids = self._ids
            assert src_ids is not None
            start = top * buffer_width + left
            for by in range(top, bottom):
                src_idx = by - y
                src_row = rows[src_idx]
                dst_cells[start : start + span] = src_row[src_x:src_end]
                ids[start : start + span] = src_ids[src_idx][src_x : src_x + span]
                start += buffer_width
            return

        if self._ids is None:
            if self.id is None:
                for row_idx in range(self.height):
                    for col_idx in range(self.width):
                        bx = x + col_idx
                        by = y + row_idx
                        cell = self._rows[row_idx][col_idx]
                        buffer.put(bx, by, cell.char, cell.style)
                return

            for row_idx in range(self.height):
                for col_idx in range(self.width):
                    bx = x + col_idx
                    by = y + row_idx
                    cell = self._rows[row_idx][col_idx]
                    buffer.put_id(bx, by, cell.char, cell.style, self.id)
            return

        for row_idx in range(self.height):
            for col_idx in range(self.width):
                bx = x + col_idx
                by = y + row_idx
                cell = self._rows[row_idx][col_idx]
                cid = self._ids[row_idx][col_idx]
                if cid is None:
                    buffer.put(bx, by, cell.char, cell.style)
                else:
                    buffer.put_id(bx, by, cell.char, cell.style, cid)

    def row(self, y: int) -> tuple[Cell, ...]:
        """Access a row by index."""
        return self._rows[y]

    def cell_id(self, x: int, y: int) -> str | None:
        """Return the semantic id at a local coordinate (or None)."""
        if self._ids is not None:
            return self._ids[y][x]
        return self.id


def _pad_row(cells: list[Cell], width: int, style: Style) -> list[Cell]:
    """Pad a row to the target width with space cells."""
    if len(cells) < width:
        space = _cached_cell(" ", style)
        cells = cells + [space] * (width - len(cells))
    return cells


def _cells_from_text(text: str, style: Style, *, max_width: int | None = None) -> list[Cell]:
    """Convert text to cells, expanding wide chars into 2 columns.

    Uses a space placeholder for the trailing cell of a wide character.
    """
    if text.isascii():
        m = _style_cell_maps.get(style)
        if m is None:
            m = {}
            _style_cell_maps[style] = m
        # Ensure all chars in text are cached
        for ch in text if max_width is None else text[:max_width]:
            if ch not in m:
                m[ch] = Cell(ch, style)
        if max_width is None:
            return list(map(m.__getitem__, text))
        return list(map(m.__getitem__, text[:max_width]))

    cells: list[Cell] = []
    used = 0

    for ch in text:
        w = char_width(ch)
        if w == 0:
            # Zero-width (combining) chars aren't representable as separate cells.
            continue

        if max_width is not None and used + w > max_width:
            break

        cells.append(Cell(ch, style))
        if w == 2:
            if max_width is not None and used + 2 > max_width:
                # Can't fit the full wide char; drop it.
                cells.pop()
                break
            cells.append(Cell(" ", style))

        used += w

        if max_width is not None and used >= max_width:
            break

    return cells


def _char_wrap(text: str, width: int, style: Style) -> list[list[Cell]]:
    """Wrap text at any character boundary by display width."""
    if not text:
        return [_pad_row([], width, style)]

    rows: list[list[Cell]] = []
    current: list[Cell] = []
    used = 0

    for ch in text:
        w = char_width(ch)
        if w == 0:
            continue
        if w > width:
            # Can't represent this character at this width.
            continue

        if used + w > width and current:
            rows.append(_pad_row(current, width, style))
            current = []
            used = 0

        if used + w > width:
            continue

        current.append(Cell(ch, style))
        if w == 2:
            current.append(Cell(" ", style))
        used += w

        if used == width:
            rows.append(current)
            current = []
            used = 0

    if current or not rows:
        rows.append(_pad_row(current, width, style))

    return rows


def _word_wrap(text: str, width: int) -> list[str]:
    """Break text at word boundaries to fit within width."""
    if width <= 0:
        return [""]
    if not text:
        return [""]

    words = text.split(" ")
    lines: list[str] = []
    current_line = ""

    for word in words:
        if not current_line:
            # First word on line — take it even if too long
            if display_width(word) <= width:
                current_line = word
            else:
                # Word itself exceeds width, break it
                while word and display_width(word) > width:
                    prefix, consumed = _take_word_prefix(word, width)
                    if consumed == 0:
                        # Unrepresentable (e.g., width=1 and next char is wide)
                        word = word[1:]
                        continue
                    lines.append(prefix)
                    word = word[consumed:]
                current_line = word
        elif display_width(current_line) + 1 + display_width(word) <= width:
            current_line += " " + word
        else:
            lines.append(current_line)
            if display_width(word) <= width:
                current_line = word
            else:
                while word and display_width(word) > width:
                    prefix, consumed = _take_word_prefix(word, width)
                    if consumed == 0:
                        word = word[1:]
                        continue
                    lines.append(prefix)
                    word = word[consumed:]
                current_line = word

    if current_line:
        lines.append(current_line)

    return lines if lines else [""]


def _take_word_prefix(word: str, width: int) -> tuple[str, int]:
    """Take a word prefix within width columns; returns (prefix, consumed)."""
    used = 0
    chars: list[str] = []
    consumed = 0

    for i, ch in enumerate(word):
        w = char_width(ch)
        if w == 0:
            chars.append(ch)
            consumed = i + 1
            continue
        if w > width:
            # Can't fit this char at all.
            break
        if used + w > width:
            break
        chars.append(ch)
        used += w
        consumed = i + 1
        if used == width:
            break

    return ("".join(chars), consumed)
