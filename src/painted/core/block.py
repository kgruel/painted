"""Block: immutable rectangle of styled cells with known dimensions."""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from enum import Enum
from typing import cast

from ._row_ops import blank_cell, iter_row_spans
from ._text_width import char_width, display_width
from .buffer import Buffer, BufferView
from .cell import Cell, Style
from .errors import ContractError


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


def _freeze_ref_rows(
    rows: Sequence[Sequence[str | None]],
) -> tuple[tuple[str | None, ...], ...]:
    frozen: list[tuple[str | None, ...]] = []
    for row in rows:
        frozen.append(cast(tuple[str | None, ...], row) if isinstance(row, tuple) else tuple(row))
    return tuple(frozen)


# Sentinel for the deprecated ``id=``/``ids=`` alias kwargs: distinguishes "not
# passed" from an explicit ``None`` so the alias only warns when actually used.
_ALIAS_UNSET: object = object()


def _resolve_ref_alias(ref: str | None, id: object, *, spelling: str) -> str | None:
    """Fold the deprecated ``id=`` kwarg into ``ref``, warning at the caller."""
    if id is _ALIAS_UNSET:
        return ref
    if ref is not None:
        raise ContractError(f"pass ref=, not both ref= and the deprecated id= ({spelling})")
    warnings.warn(
        f"{spelling} is deprecated; use ref= (removed at 1.0)",
        DeprecationWarning,
        stacklevel=3,
    )
    return cast("str | None", id)


class Block:
    """Immutable rectangle of styled cells with known dimensions."""

    __slots__ = ("width", "height", "ref", "_rows", "_refs", "_frozen")

    def __init__(
        self,
        rows: Sequence[Sequence[Cell]],
        width: int,
        *,
        ref: str | None = None,
        refs: Sequence[Sequence[str | None]] | None = None,
        id: object = _ALIAS_UNSET,
        ids: object = _ALIAS_UNSET,
    ):
        if id is not _ALIAS_UNSET or ids is not _ALIAS_UNSET:
            if (id is not _ALIAS_UNSET and ref is not None) or (
                ids is not _ALIAS_UNSET and refs is not None
            ):
                raise ContractError(
                    "pass ref=/refs=, not both the new and the deprecated id=/ids= spellings"
                )
            warnings.warn(
                "Block(id=, ids=) is deprecated; use ref=, refs= (removed at 1.0)",
                DeprecationWarning,
                stacklevel=2,
            )
            if id is not _ALIAS_UNSET:
                ref = cast("str | None", id)
            if ids is not _ALIAS_UNSET:
                refs = cast("Sequence[Sequence[str | None]] | None", ids)

        frozen_rows = _freeze_cell_rows(rows)
        frozen_refs = _freeze_ref_rows(refs) if refs is not None else None
        for row_idx, row in enumerate(frozen_rows):
            if len(row) != width:
                raise ContractError(f"Block row {row_idx} width {len(row)} != block width {width}")
        if frozen_refs is not None:
            if len(frozen_refs) != len(frozen_rows):
                raise ContractError(
                    f"Block refs height {len(frozen_refs)} != block height {len(frozen_rows)}"
                )
            for row_idx, row in enumerate(frozen_refs):
                if len(row) != width:
                    raise ContractError(
                        f"Block refs row {row_idx} width {len(row)} != block width {width}"
                    )
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", len(frozen_rows))
        object.__setattr__(self, "ref", ref)
        object.__setattr__(self, "_rows", frozen_rows)
        object.__setattr__(self, "_refs", frozen_refs)
        object.__setattr__(self, "_frozen", True)

    @staticmethod
    def _create(
        rows: tuple[tuple[Cell, ...] | Sequence[Cell], ...],
        width: int,
        ref: str | None = None,
        refs: tuple[tuple[str | None, ...], ...] | None = None,
    ) -> Block:
        """Internal fast constructor — rows must be frozen tuples of correct width."""
        b = object.__new__(Block)
        object.__setattr__(b, "width", width)
        object.__setattr__(b, "height", len(rows))
        object.__setattr__(b, "ref", ref)
        object.__setattr__(b, "_rows", rows)
        object.__setattr__(b, "_refs", refs)
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
        ref: str | None = None,
        id: object = _ALIAS_UNSET,
    ) -> Block:
        """Create a block from text content with optional wrapping.

        A newline in ``content`` is declared line structure, honored as a hard
        break: segments split first, the wrap mode applies *within* each
        segment, and the segment blocks stack vertically (decision
        practice/block-text-honors-newlines). Without this split a ``\\n``
        would reach ``Cell`` and be scrubbed to a space — the renderer
        silently rewriting declared meaning.
        """
        ref = _resolve_ref_alias(ref, id, spelling="Block.text(id=)")
        if width is not None and width <= 0:
            return Block([[]], 0, ref=ref)

        if "\n" in content:
            seg_blocks = [
                Block.text(segment, style, width=width, wrap=wrap)
                for segment in content.split("\n")
            ]
            if width is None:
                w = max(b.width for b in seg_blocks)
                rows = [_pad_row(list(row), w, style) for b in seg_blocks for row in b._rows]
                return Block(rows, w, ref=ref)
            rows_t = tuple(row for b in seg_blocks for row in b._rows)
            return Block._create(rows_t, width, ref=ref)

        if width is None:
            cells = _cells_from_text(content, style)
            return Block._create((tuple(cells),), len(cells), ref=ref)

        if wrap == Wrap.NONE:
            # Truncate at width, single line
            if content.isascii():
                return Block._create((_ascii_row_tuple(content, width, style),), width, ref=ref)
            cells = _cells_from_text(content, style, max_width=width)
            cells = _pad_row(cells, width, style)
            return Block._create((tuple(cells),), width, ref=ref)

        if wrap == Wrap.ELLIPSIS:
            # Truncate with the ambient marker if needed. The marker is read from
            # current_icons() (not a hardcoded "…") so it degrades to ASCII under
            # use_icons(ASCII_ICONS) and a strict-ASCII stream never raises on the
            # "…" codepoint. The marker may be wider than one column ("..."), so
            # reserve its display width — never assume a 1-column ellipsis.
            from ..icon_set import current_icons

            if display_width(content) <= width:
                if content.isascii():
                    return Block._create((_ascii_row_tuple(content, width, style),), width, ref=ref)
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
            return Block._create((tuple(cells),), width, ref=ref)

        if wrap == Wrap.CHAR:
            # Break at any character boundary
            rows = _char_wrap(content, width, style)
            return Block(rows, width, ref=ref)

        if wrap == Wrap.WORD:
            # Break at word boundaries
            lines = _word_wrap(content, width)
            rows = [
                _pad_row(_cells_from_text(line, style, max_width=width), width, style)
                for line in lines
            ]
            return Block(rows, width, ref=ref)

        raise ContractError(f"Unknown wrap mode: {wrap}")

    @staticmethod
    def column(
        rows: Sequence[tuple[str, Style]],
        *,
        width: int | None = None,
        ref: str | None = None,
        id: object = _ALIAS_UNSET,
    ) -> Block:
        """Create a block from per-row (text, style) pairs.

        Each entry becomes one row. Width is inferred from the first row's
        display width if not given explicitly; all rows are padded/truncated
        to match.
        """
        ref = _resolve_ref_alias(ref, id, spelling="Block.column(id=)")
        if not rows:
            return Block([], 0, ref=ref)

        if width is None:
            width = max(display_width(text) for text, _style in rows)

        cell_rows: list[list[Cell]] = []
        for text, style in rows:
            cells = _cells_from_text(text, style, max_width=width)
            cells = _pad_row(cells, width, style)
            cell_rows.append(cells)

        return Block(cell_rows, width, ref=ref)

    @staticmethod
    def empty(
        width: int | None,
        height: int,
        style: Style = Style(),
        *,
        ref: str | None = None,
        id: object = _ALIAS_UNSET,
    ) -> Block:
        """Create a block filled with space cells.

        ``width=None`` sizes naturally (the width contract: absent is natural) —
        empty content has no width, so the rows are zero-width. The idiom for
        vertical spacing in width-None lens paths: ``Block.empty(None, 1)``.
        """
        ref = _resolve_ref_alias(ref, id, spelling="Block.empty(id=)")
        if width is None:
            width = 0
        space = Cell(" ", style)
        rows = [[space] * width for _ in range(height)]
        return Block(rows, width, ref=ref)

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
                dst_refs = buffer._refs
                buffer_width = buffer.width
                rows = self._rows

                if self._refs is None:
                    if self.ref is None:
                        clear_refs = [None] * span if dst_refs is not None else None
                        start = top * buffer_width + left
                        for by in range(top, bottom):
                            src_row = rows[by - y]
                            dst_cells[start : start + span] = src_row[src_x:src_end]
                            if dst_refs is not None and clear_refs is not None:
                                dst_refs[start : start + span] = clear_refs
                            start += buffer_width
                        return

                    refs = buffer._ensure_refs()
                    row_refs = [self.ref] * span
                    start = top * buffer_width + left
                    for by in range(top, bottom):
                        src_row = rows[by - y]
                        dst_cells[start : start + span] = src_row[src_x:src_end]
                        refs[start : start + span] = row_refs
                        start += buffer_width
                    return

                refs = buffer._ensure_refs()
                src_refs = self._refs
                assert src_refs is not None
                start = top * buffer_width + left
                for by in range(top, bottom):
                    src_idx = by - y
                    src_row = rows[src_idx]
                    dst_cells[start : start + span] = src_row[src_x:src_end]
                    refs[start : start + span] = src_refs[src_idx][src_x : src_x + span]
                    start += buffer_width
                return

        target = buffer
        uniform_ref = self.ref if self._refs is None else None

        for row_idx in range(self.height):
            by = y + row_idx
            if by < 0 or by >= target.height:
                continue

            src_row = self._rows[row_idx]
            src_refs = self._refs[row_idx] if self._refs is not None else None

            for span in iter_row_spans(src_row, src_refs):
                bx = x + span.start

                if span.width == 1:
                    if 0 <= bx < target.width:
                        cell = span.cells[0]
                        cref = span.refs[0] if span.refs is not None else uniform_ref
                        if cref is None:
                            target.put(bx, by, cell.char, cell.style)
                        else:
                            target.put_ref(bx, by, cell.char, cell.style, cref)
                    continue

                if 0 <= bx and bx + span.width <= target.width:
                    for offset, cell in enumerate(span.cells):
                        cref = span.refs[offset] if span.refs is not None else uniform_ref
                        px = bx + offset
                        if cref is None:
                            target.put(px, by, cell.char, cell.style)
                        else:
                            target.put_ref(px, by, cell.char, cell.style, cref)
                    continue

                for offset, cell in enumerate(span.cells):
                    px = bx + offset
                    if 0 <= px < target.width:
                        blank = blank_cell(cell.style)
                        cref = span.refs[offset] if span.refs is not None else uniform_ref
                        if cref is None:
                            target.put(px, by, blank.char, blank.style)
                        else:
                            target.put_ref(px, by, blank.char, blank.style, cref)

    def row(self, y: int) -> tuple[Cell, ...]:
        """Access a row by index."""
        return self._rows[y]

    @property
    def id(self) -> str | None:
        """Deprecated alias for :attr:`ref` (removed at 1.0)."""
        warnings.warn(
            "Block.id is deprecated; use Block.ref",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.ref

    def cell_ref(self, x: int, y: int) -> str | None:
        """Return the semantic ref at a local coordinate (or None)."""
        if self._refs is not None:
            return self._refs[y][x]
        return self.ref

    def cell_id(self, x: int, y: int) -> str | None:
        """Deprecated alias for :meth:`cell_ref` (removed at 1.0)."""
        warnings.warn(
            "Block.cell_id is deprecated; use Block.cell_ref",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.cell_ref(x, y)

    def __setstate__(self, state: tuple[object, dict[str, object]]) -> None:
        # Pickles written by painted <= 0.6 carry the pre-rename slot names
        # (id, _ids); remap so they restore into the renamed slots. The default
        # slot restore would also trip the read-only ``id`` property, so slots
        # are assigned directly. Removed at 1.0 with the rest of the id= alias
        # surface.
        _, slots = state
        for old, new in (("id", "ref"), ("_ids", "_refs")):
            if old in slots:
                slots[new] = slots.pop(old)
        for name, value in slots.items():
            object.__setattr__(self, name, value)


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
# The wrap algorithms operate on a *styled-char stream* — one (char, Style,
# ref) entry per source character. Single-style text (`str`) is the degenerate
# case where every entry shares one style and no ref, so the `str` entry
# points below are thin adapters over these cores. This is the one wrap
# engine; there is no parallel str/styled logic to keep in sync. The ref lane
# is what lets a `Span`'s denotation survive reflow: a wrapped link keeps its
# ref on every fragment, the same way its style rides its characters.

_StyledChars = list[tuple[str, Style, str | None]]


def _styled_from_text(text: str, style: Style) -> _StyledChars:
    """Expand a single-style string into a styled-char stream."""
    return [(ch, style, None) for ch in text]


def _cells_from_styled(
    chars: _StyledChars, *, max_width: int | None = None
) -> tuple[list[Cell], list[str | None] | None]:
    """Materialize a styled-char stream into cells plus a parallel ref lane.

    Each character carries its own style and ref; a space placeholder follows
    a wide char and inherits both. Mirrors `_cells_from_text` but per-char
    rather than per-string. The ref lane is ``None`` (not a list of ``None``)
    when no character carries a ref — the common case allocates nothing.
    """
    cells: list[Cell] = []
    refs: list[str | None] | None = None
    used = 0
    for ch, st, ref in chars:
        w = char_width(ch)
        if w == 0:
            continue
        if max_width is not None and used + w > max_width:
            break
        if ref is not None and refs is None:
            refs = cast("list[str | None]", [None] * len(cells))
        cells.append(Cell(ch, st))
        if refs is not None:
            refs.append(ref)
        if w == 2:
            cells.append(Cell(" ", st))
            if refs is not None:
                refs.append(ref)
        used += w
        if max_width is not None and used >= max_width:
            break
    return cells, refs


def _pad_refs(refs: list[str | None], width: int) -> list[str | None]:
    """Pad a ref lane to width — pad cells denote nothing."""
    if len(refs) < width:
        return refs + [None] * (width - len(refs))
    return refs


def _styled_width(chars: _StyledChars) -> int:
    """Display width of a styled-char stream."""
    return sum(w for w in (char_width(entry[0]) for entry in chars) if w > 0)


def _take_styled_prefix(seg: _StyledChars, width: int) -> tuple[_StyledChars, int]:
    """Take a styled prefix within width columns; returns (prefix, consumed)."""
    used = 0
    out: _StyledChars = []
    consumed = 0
    for i, entry in enumerate(seg):
        w = char_width(entry[0])
        if w == 0:
            out.append(entry)
            consumed = i + 1
            continue
        if w > width:
            break
        if used + w > width:
            break
        out.append(entry)
        used += w
        consumed = i + 1
        if used == width:
            break
    return out, consumed


def _char_wrap_styled(
    chars: _StyledChars, width: int, pad_style: Style
) -> tuple[list[list[Cell]], list[list[str | None]] | None]:
    """Wrap a styled-char stream at any character boundary by display width.

    Returns the cell rows plus a parallel grid of ref rows — ``None`` when no
    character carries a ref, so the common case allocates nothing.
    """
    if not chars:
        return [_pad_row([], width, pad_style)], None

    has_refs = any(entry[2] is not None for entry in chars)
    rows: list[list[Cell]] = []
    ref_rows: list[list[str | None]] = []
    current: list[Cell] = []
    current_refs: list[str | None] = []
    used = 0

    for ch, st, ref in chars:
        w = char_width(ch)
        if w == 0:
            continue
        if w > width:
            # Can't represent this character at this width.
            continue

        if used + w > width and current:
            rows.append(_pad_row(current, width, pad_style))
            if has_refs:
                ref_rows.append(_pad_refs(current_refs, width))
            current = []
            current_refs = []
            used = 0

        if used + w > width:
            continue

        current.append(Cell(ch, st))
        current_refs.append(ref)
        if w == 2:
            current.append(Cell(" ", st))
            current_refs.append(ref)
        used += w

        if used == width:
            rows.append(current)
            if has_refs:
                ref_rows.append(current_refs)
            current = []
            current_refs = []
            used = 0

    if current or not rows:
        rows.append(_pad_row(current, width, pad_style))
        if has_refs:
            ref_rows.append(_pad_refs(current_refs, width))

    return rows, ref_rows if has_refs else None


def _word_wrap_styled(chars: _StyledChars, width: int) -> list[_StyledChars]:
    """Break a styled-char stream at word boundaries to fit within width.

    Source spaces (and their styles) are preserved between words on the same
    line; the break space at a wrap point is dropped (lines are right-trimmed).
    For uniform-style input where pad style equals the content style, this
    yields cells identical to the legacy string wrap.
    """
    if width <= 0 or not chars:
        return [[]]

    # Group into alternating space / non-space segments, style + ref preserved.
    segments: list[tuple[bool, _StyledChars]] = []
    cur: _StyledChars = []
    cur_sp: bool | None = None
    for entry in chars:
        sp = entry[0] == " "
        if cur and sp != cur_sp:
            segments.append((cast(bool, cur_sp), cur))
            cur = []
        cur.append(entry)
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

    # Emit the trailing line, but only if it carries content or is the sole row.
    # A final word that is entirely unrepresentable (e.g. a width-2 char in a
    # width-1 budget) drains ``line`` to empty after the wrap above; appending it
    # unconditionally would add a phantom blank row, inflating height and
    # diverging from the legacy ``lines if lines else ['']`` contract. Mirrors
    # the guard in ``_char_wrap_styled``.
    if line or not lines:
        lines.append(line)
    return lines


# --- str adapters over the styled engine ------------------------------------


def _char_wrap(text: str, width: int, style: Style) -> list[list[Cell]]:
    """Wrap a single-style string at any character boundary."""
    rows, _ = _char_wrap_styled(_styled_from_text(text, style), width, style)
    return rows


def _word_wrap(text: str, width: int) -> list[str]:
    """Break a single-style string at word boundaries (legacy str view)."""
    if width <= 0 or not text:
        return [""]
    lines = _word_wrap_styled(_styled_from_text(text, Style()), width)
    return ["".join(entry[0] for entry in ln) for ln in lines] or [""]


def _take_word_prefix(word: str, width: int) -> tuple[str, int]:
    """Take a word prefix within width columns; returns (prefix, consumed)."""
    out, consumed = _take_styled_prefix(_styled_from_text(word, Style()), width)
    return "".join(entry[0] for entry in out), consumed


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
        rows, ref_rows = _char_wrap_styled(chars, width, pad_style)
        return Block(rows, width, refs=ref_rows)

    if wrap == Wrap.WORD:
        lines = _word_wrap_styled(chars, width)
        rows = []
        line_refs: list[list[str | None] | None] = []
        for line in lines:
            cells, refs = _cells_from_styled(line, max_width=width)
            rows.append(_pad_row(cells, width, pad_style))
            line_refs.append(_pad_refs(refs, width) if refs is not None else None)
        if any(r is not None for r in line_refs):
            ref_rows = [r if r is not None else [None] * width for r in line_refs]
            return Block(rows, width, refs=ref_rows)
        return Block(rows, width)

    if wrap == Wrap.NONE:
        cells, refs = _cells_from_styled(chars, max_width=width)
        cells = _pad_row(cells, width, pad_style)
        if refs is not None:
            return Block([cells], width, refs=[_pad_refs(refs, width)])
        return Block([cells], width)

    if wrap == Wrap.ELLIPSIS:
        if _styled_width(chars) <= width:
            cells, refs = _cells_from_styled(chars, max_width=width)
        else:
            from ..icon_set import current_icons

            ellipsis = current_icons().ellipsis
            ell_w = display_width(ellipsis)
            ell_chars = _styled_from_text(ellipsis, pad_style)
            if ell_w >= width:
                cells, refs = _cells_from_styled(ell_chars, max_width=width)
            else:
                cells, refs = _cells_from_styled(chars, max_width=width - ell_w)
                ell_cells, _ = _cells_from_styled(ell_chars)
                if refs is not None:
                    # The marker denotes nothing — it is loss evidence, not content.
                    refs.extend([None] * len(ell_cells))
                cells.extend(ell_cells)
        cells = _pad_row(cells, width, pad_style)
        if refs is not None:
            return Block([cells], width, refs=[_pad_refs(refs, width)])
        return Block([cells], width)

    raise ContractError(f"Unknown wrap mode: {wrap}")
