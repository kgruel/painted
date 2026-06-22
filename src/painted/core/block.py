"""Block: immutable rectangle of styled cells with known dimensions."""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from typing import cast

from ._row_ops import blank_cell, iter_row_spans
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


def _ascii_row_tuple(chars: str, width: int, style: Style) -> tuple[Cell, ...]:
    """Build a padded ASCII row as a frozen tuple, bypassing list intermediates."""
    m = _style_cell_maps.get(style)
    if m is None:
        m = {}
        _style_cell_maps[style] = m
    src = chars[:width]
    try:
        row = tuple(map(m.__getitem__, src))
    except KeyError:
        for ch in src:
            if ch not in m:
                m[ch] = Cell(ch, style)
        row = tuple(map(m.__getitem__, src))
    n = len(row)
    if n < width:
        space = m.get(" ")
        if space is None:
            space = Cell(" ", style)
            m[" "] = space
        row = row + (space,) * (width - n)
    return row


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

    @staticmethod
    def _create(
        rows: tuple[tuple[Cell, ...] | Sequence[Cell], ...],
        width: int,
        id: str | None = None,
        ids: tuple[tuple[str | None, ...], ...] | None = None,
    ) -> Block:
        """Internal fast constructor — rows must be frozen tuples of correct width."""
        b = object.__new__(Block)
        object.__setattr__(b, "width", width)
        object.__setattr__(b, "height", len(rows))
        object.__setattr__(b, "id", id)
        object.__setattr__(b, "_rows", rows)
        object.__setattr__(b, "_ids", ids)
        object.__setattr__(b, "_frozen", True)
        return b

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
            return Block._create((tuple(cells),), len(cells), id=id)

        if wrap == Wrap.NONE:
            # Truncate at width, single line
            if content.isascii():
                return Block._create((_ascii_row_tuple(content, width, style),), width, id=id)
            cells = _cells_from_text(content, style, max_width=width)
            cells = _pad_row(cells, width, style)
            return Block._create((tuple(cells),), width, id=id)

        if wrap == Wrap.ELLIPSIS:
            # Truncate with the ambient marker if needed. The marker is read from
            # current_icons() (not a hardcoded "…") so it degrades to ASCII under
            # use_icons(ASCII_ICONS) and a strict-ASCII stream never raises on the
            # "…" codepoint. The marker may be wider than one column ("..."), so
            # reserve its display width — never assume a 1-column ellipsis.
            from ..icon_set import current_icons

            if display_width(content) <= width:
                if content.isascii():
                    return Block._create((_ascii_row_tuple(content, width, style),), width, id=id)
                cells = _cells_from_text(content, style, max_width=width)
            else:
                ellipsis = current_icons().ellipsis
                ell_w = display_width(ellipsis)
                if ell_w >= width:
                    # No room for content beside the marker — show the marker
                    # alone, itself clipped to the budget.
                    cells = _cells_from_text(ellipsis, style, max_width=width)
                else:
                    cells = _cells_from_text(content, style, max_width=width - ell_w)
                    cells.extend(_cells_from_text(ellipsis, style))
            cells = _pad_row(cells, width, style)
            return Block._create((tuple(cells),), width, id=id)

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
            width = max(display_width(text) for text, _style in rows)

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

            if 0 <= x and x + self.width <= buffer.width:
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

        target = buffer
        uniform_id = self.id if self._ids is None else None

        for row_idx in range(self.height):
            by = y + row_idx
            if by < 0 or by >= target.height:
                continue

            src_row = self._rows[row_idx]
            src_ids = self._ids[row_idx] if self._ids is not None else None

            for span in iter_row_spans(src_row, src_ids):
                bx = x + span.start

                if span.width == 1:
                    if 0 <= bx < target.width:
                        cell = span.cells[0]
                        cid = span.ids[0] if span.ids is not None else uniform_id
                        if cid is None:
                            target.put(bx, by, cell.char, cell.style)
                        else:
                            target.put_id(bx, by, cell.char, cell.style, cid)
                    continue

                if 0 <= bx and bx + span.width <= target.width:
                    for offset, cell in enumerate(span.cells):
                        cid = span.ids[offset] if span.ids is not None else uniform_id
                        px = bx + offset
                        if cid is None:
                            target.put(px, by, cell.char, cell.style)
                        else:
                            target.put_id(px, by, cell.char, cell.style, cid)
                    continue

                for offset, cell in enumerate(span.cells):
                    px = bx + offset
                    if 0 <= px < target.width:
                        blank = blank_cell(cell.style)
                        cid = span.ids[offset] if span.ids is not None else uniform_id
                        if cid is None:
                            target.put(px, by, blank.char, blank.style)
                        else:
                            target.put_id(px, by, blank.char, blank.style, cid)

    def row(self, y: int) -> tuple[Cell, ...]:
        """Access a row by index."""
        return self._rows[y]

    def cell_id(self, x: int, y: int) -> str | None:
        """Return the semantic id at a local coordinate (or None)."""
        if self._ids is not None:
            return self._ids[y][x]
        return self.id


_space_cells: dict[Style, Cell] = {}


def _pad_row(cells: list[Cell], width: int, style: Style) -> list[Cell]:
    """Pad a row to the target width with space cells."""
    if len(cells) < width:
        space = _space_cells.get(style)
        if space is None:
            space = Cell(" ", style)
            _space_cells[style] = space
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
        src = text if max_width is None else text[:max_width]
        try:
            return list(map(m.__getitem__, src))
        except KeyError:
            for ch in src:
                if ch not in m:
                    m[ch] = Cell(ch, style)
            return list(map(m.__getitem__, src))

    # Inline cell caching for the non-ASCII path to avoid per-char function calls
    m = _style_cell_maps.get(style)
    if m is None:
        m = {}
        _style_cell_maps[style] = m

    cells: list[Cell] = []
    used = 0
    append = cells.append
    m_get = m.get

    for ch in text:
        if ch.isascii():
            if max_width is not None and used + 1 > max_width:
                break
            cell = m_get(ch)
            if cell is None:
                cell = Cell(ch, style)
                m[ch] = cell
            append(cell)
            used += 1
        else:
            w = char_width(ch)
            if w == 0:
                continue
            if max_width is not None and used + w > max_width:
                break
            cell = m_get(ch)
            if cell is None:
                cell = Cell(ch, style)
                m[ch] = cell
            append(cell)
            if w == 2:
                space = m_get(" ")
                if space is None:
                    space = Cell(" ", style)
                    m[" "] = space
                append(space)
            used += w

        if max_width is not None and used >= max_width:
            break

    return cells


# --- Styled wrap engine -----------------------------------------------------
#
# The wrap algorithms operate on a *styled-char stream* — one (char, Style)
# entry per source character. Single-style text (`str`) is the degenerate case
# where every entry shares one style, so the `str` entry points below are thin
# adapters over these cores. This is the one wrap engine; there is no parallel
# str/styled logic to keep in sync.

_StyledChars = list[tuple[str, Style]]


def _styled_from_text(text: str, style: Style) -> _StyledChars:
    """Expand a single-style string into a styled-char stream."""
    return [(ch, style) for ch in text]


def _cells_from_styled(chars: _StyledChars, *, max_width: int | None = None) -> list[Cell]:
    """Materialize a styled-char stream into cells, expanding wide chars.

    Each character carries its own style; a space placeholder follows a wide
    char and inherits that char's style. Mirrors `_cells_from_text` but
    per-char rather than per-string.
    """
    cells: list[Cell] = []
    used = 0
    for ch, st in chars:
        w = char_width(ch)
        if w == 0:
            continue
        if max_width is not None and used + w > max_width:
            break
        cells.append(Cell(ch, st))
        if w == 2:
            cells.append(Cell(" ", st))
        used += w
        if max_width is not None and used >= max_width:
            break
    return cells


def _styled_width(chars: _StyledChars) -> int:
    """Display width of a styled-char stream."""
    return sum(w for w in (char_width(ch) for ch, _ in chars) if w > 0)


def _take_styled_prefix(seg: _StyledChars, width: int) -> tuple[_StyledChars, int]:
    """Take a styled prefix within width columns; returns (prefix, consumed)."""
    used = 0
    out: _StyledChars = []
    consumed = 0
    for i, (ch, st) in enumerate(seg):
        w = char_width(ch)
        if w == 0:
            out.append((ch, st))
            consumed = i + 1
            continue
        if w > width:
            break
        if used + w > width:
            break
        out.append((ch, st))
        used += w
        consumed = i + 1
        if used == width:
            break
    return out, consumed


def _char_wrap_styled(chars: _StyledChars, width: int, pad_style: Style) -> list[list[Cell]]:
    """Wrap a styled-char stream at any character boundary by display width."""
    if not chars:
        return [_pad_row([], width, pad_style)]

    rows: list[list[Cell]] = []
    current: list[Cell] = []
    used = 0

    for ch, st in chars:
        w = char_width(ch)
        if w == 0:
            continue
        if w > width:
            # Can't represent this character at this width.
            continue

        if used + w > width and current:
            rows.append(_pad_row(current, width, pad_style))
            current = []
            used = 0

        if used + w > width:
            continue

        current.append(Cell(ch, st))
        if w == 2:
            current.append(Cell(" ", st))
        used += w

        if used == width:
            rows.append(current)
            current = []
            used = 0

    if current or not rows:
        rows.append(_pad_row(current, width, pad_style))

    return rows


def _word_wrap_styled(chars: _StyledChars, width: int) -> list[_StyledChars]:
    """Break a styled-char stream at word boundaries to fit within width.

    Source spaces (and their styles) are preserved between words on the same
    line; the break space at a wrap point is dropped (lines are right-trimmed).
    For uniform-style input where pad style equals the content style, this
    yields cells identical to the legacy string wrap.
    """
    if width <= 0 or not chars:
        return [[]]

    # Group into alternating space / non-space segments, style preserved.
    segments: list[tuple[bool, _StyledChars]] = []
    cur: _StyledChars = []
    cur_sp: bool | None = None
    for ch, st in chars:
        sp = ch == " "
        if cur and sp != cur_sp:
            segments.append((cast(bool, cur_sp), cur))
            cur = []
        cur.append((ch, st))
        cur_sp = sp
    if cur:
        segments.append((cast(bool, cur_sp), cur))

    lines: list[_StyledChars] = []
    line: _StyledChars = []
    line_w = 0
    pending: _StyledChars = []  # space segment awaiting a following word

    for is_sp, seg in segments:
        if is_sp:
            pending = seg
            continue

        word_w = _styled_width(seg)
        if line:
            sp_w = _styled_width(pending)
            if line_w + sp_w + word_w <= width:
                line = line + pending + seg
                line_w += sp_w + word_w
                pending = []
                continue
            # Word does not fit; wrap and drop the break space.
            lines.append(line)
            line = []
            line_w = 0
        pending = []

        # Place the word on a fresh line.
        if word_w <= width:
            line = list(seg)
            line_w = word_w
        else:
            rest = seg
            while rest and _styled_width(rest) > width:
                prefix, consumed = _take_styled_prefix(rest, width)
                if consumed == 0:
                    # Unrepresentable lead char (e.g. width=1, wide char).
                    rest = rest[1:]
                    continue
                lines.append(prefix)
                rest = rest[consumed:]
            line = list(rest)
            line_w = _styled_width(rest)

    lines.append(line)
    return lines


# --- str adapters over the styled engine ------------------------------------


def _char_wrap(text: str, width: int, style: Style) -> list[list[Cell]]:
    """Wrap a single-style string at any character boundary."""
    return _char_wrap_styled(_styled_from_text(text, style), width, style)


def _word_wrap(text: str, width: int) -> list[str]:
    """Break a single-style string at word boundaries (legacy str view)."""
    if width <= 0 or not text:
        return [""]
    lines = _word_wrap_styled(_styled_from_text(text, Style()), width)
    return ["".join(ch for ch, _ in ln) for ln in lines] or [""]


def _take_word_prefix(word: str, width: int) -> tuple[str, int]:
    """Take a word prefix within width columns; returns (prefix, consumed)."""
    out, consumed = _take_styled_prefix(_styled_from_text(word, Style()), width)
    return "".join(ch for ch, _ in out), consumed


def _wrap_styled(
    chars: _StyledChars,
    width: int,
    *,
    wrap: Wrap = Wrap.WORD,
    pad_style: Style = Style(),
) -> Block:
    """Wrap a styled-char stream into a Block — the seam behind `Line.wrap`.

    `pad_style` styles the trailing pad cells (and the ellipsis marker); it is
    the multi-line generalization of `Line.to_block`, which is itself
    single-line `Wrap.NONE`. The four `Wrap` modes mirror `Block.text` exactly.
    """
    if width <= 0:
        return Block([[]], 0)

    if wrap == Wrap.CHAR:
        rows = _char_wrap_styled(chars, width, pad_style)
        return Block(rows, width)

    if wrap == Wrap.WORD:
        lines = _word_wrap_styled(chars, width)
        rows = [
            _pad_row(_cells_from_styled(line, max_width=width), width, pad_style) for line in lines
        ]
        return Block(rows, width)

    if wrap == Wrap.NONE:
        cells = _pad_row(_cells_from_styled(chars, max_width=width), width, pad_style)
        return Block([cells], width)

    if wrap == Wrap.ELLIPSIS:
        if _styled_width(chars) <= width:
            cells = _cells_from_styled(chars, max_width=width)
        else:
            from ..icon_set import current_icons

            ellipsis = current_icons().ellipsis
            ell_w = display_width(ellipsis)
            ell_chars = _styled_from_text(ellipsis, pad_style)
            if ell_w >= width:
                cells = _cells_from_styled(ell_chars, max_width=width)
            else:
                cells = _cells_from_styled(chars, max_width=width - ell_w)
                cells.extend(_cells_from_styled(ell_chars))
        cells = _pad_row(cells, width, pad_style)
        return Block([cells], width)

    raise ValueError(f"Unknown wrap mode: {wrap}")
