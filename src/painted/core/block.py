"""Block: immutable rectangle of styled cells with known dimensions."""

from __future__ import annotations

import re
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


def _split_lines(text: str) -> list[str]:
    """Split text on declared line breaks — the str sibling of
    ``_split_runs_newlines``: ``\\n`` breaks, a ``\\r\\n`` pair is one break."""
    return text.replace("\r\n", "\n").split("\n")


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

        A newline (``\\n``, or a ``\\r\\n`` pair) in ``content`` is declared
        line structure, honored as a hard break: segments split first, the
        wrap mode applies *within* each segment, and the segment blocks stack
        vertically (decision practice/block-text-honors-newlines). Without
        this split the control chars would reach ``Cell`` and be scrubbed to
        spaces — the renderer silently rewriting declared meaning. The
        ``width <= 0`` degenerate case keeps its empty-block contract and
        collapses before the split.
        """
        ref = _resolve_ref_alias(ref, id, spelling="Block.text(id=)")
        if width is not None and width <= 0:
            return Block([[]], 0, ref=ref)

        if width is None:
            if "\n" in content:
                return _wrap_runs(
                    [(content, style, None)], None, wrap=Wrap.NONE, pad_style=style, ref=ref
                )
            cells = _cells_from_text(content, style)
            return Block._create((tuple(cells),), len(cells), ref=ref)

        if wrap == Wrap.NONE and content.isascii() and "\n" not in content:
            # The hot path: single-line ASCII clip/pad through the cached
            # tuple map, no list intermediates (the engine's degenerate case,
            # kept inline — Block.text is the hottest constructor in the tree).
            return Block._create((_ascii_row_tuple(content, width, style),), width, ref=ref)

        return _wrap_runs([(content, style, None)], width, wrap=wrap, pad_style=style, ref=ref)

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
        to match. A newline (or CRLF pair) inside an entry's text is declared
        line structure: the entry splits into one row per line, each carrying
        the entry's style (decision practice/block-text-honors-newlines).
        """
        ref = _resolve_ref_alias(ref, id, spelling="Block.column(id=)")
        if any("\n" in text for text, _style in rows):
            rows = [(segment, style) for text, style in rows for segment in _split_lines(text)]
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
# The wrap algorithms operate on a *styled-run stream* — one (text, Style,
# ref) run per uniformly styled stretch of source text, the same shape a
# `Span` declares. Single-style text (`str`) is the degenerate one-run case,
# so the `str` entry points build a one-run stream rather than adapting a
# parallel implementation. This is the one wrap engine: wrap algorithms
# operate on runs, and materialization batches per run through the cached
# cell maps (`_cells_from_text` is the per-run core), so the degenerate case
# pays the fast-path cost, not a per-char tax. The ref lane is what lets a
# `Span`'s denotation survive reflow: a wrapped link keeps its ref on every
# fragment, the same way its style rides its characters.

_StyledRuns = list[tuple[str, Style, str | None]]


def _run_width(text: str) -> int:
    """Display width of one run's text — the cell count its materialization
    produces (zero-width chars contribute nothing, wide chars two columns).

    Deliberately not `display_width`: that falls back to ``len(text)`` when
    ``wcswidth`` reports non-printables, which would diverge from the cell
    count `_cells_from_text` actually produces. This is the engine's measure;
    it must predict materialization exactly.
    """
    if text.isascii():
        return len(text)
    return sum(w for w in map(char_width, text) if w > 0)


def _runs_width(runs: _StyledRuns) -> int:
    """Display width of a styled-run stream."""
    return sum(_run_width(text) for text, _style, _ref in runs)


def _cells_from_runs(
    runs: _StyledRuns, *, max_width: int | None = None
) -> tuple[list[Cell], list[str | None] | None]:
    """Materialize a styled-run stream into cells plus a parallel ref lane.

    Each run batches through `_cells_from_text`'s cached maps; a run's ref
    stamps every cell it produces (wide-char placeholders included). The ref
    lane is ``None`` (not a list of ``None``) when no run carries a ref — the
    common case allocates nothing. Truncation stops at the first character
    that does not fit (a wide char at the boundary ends the take; later runs
    do not spill past it).
    """
    cells: list[Cell] = []
    refs: list[str | None] | None = None
    remaining = max_width
    for text, style, ref in runs:
        if not text:
            continue
        run_cells = _cells_from_text(text, style, max_width=remaining)
        if ref is not None and refs is None:
            refs = cast("list[str | None]", [None] * len(cells))
        cells.extend(run_cells)
        if refs is not None:
            refs.extend([ref] * len(run_cells))
        if remaining is not None:
            remaining -= len(run_cells)
            if remaining <= 0 or len(run_cells) < _run_width(text):
                break
    return cells, refs


def _pad_refs(refs: list[str | None], width: int) -> list[str | None]:
    """Pad a ref lane to width — pad cells denote nothing."""
    if len(refs) < width:
        return refs + [None] * (width - len(refs))
    return refs


def _take_runs_prefix(runs: _StyledRuns, width: int) -> tuple[_StyledRuns, _StyledRuns, int]:
    """Split a run stream at a display-column boundary.

    Returns ``(prefix, rest, consumed)`` — ``consumed`` counts display columns
    removed from the stream (taken plus dropped), so a caller measuring the
    whole stream once can subtract instead of re-scanning ``rest``. Zero-width
    chars ride with the character before them; a char wider than the remaining
    budget ends the take before it. A lead char wider than ``width`` itself is
    unrepresentable at this width and dropped here, so the take always makes
    progress: an empty prefix means the stream is exhausted (``rest == []``).
    """
    prefix: _StyledRuns = []
    remaining = width
    consumed = 0
    for idx, run in enumerate(runs):
        text = run[0]
        if not text:
            continue
        w = _run_width(text)
        if w <= remaining:
            prefix.append(run)
            remaining -= w
            consumed += w
            if remaining == 0:
                return prefix, [r for r in runs[idx + 1 :] if r[0]], consumed
            continue
        # Boundary run: char-scan what fits, dropping fresh-row lead chars
        # too wide to fit at any row of this width.
        head_chars: list[str] = []
        pos = 0
        for ch in text:
            cw = char_width(ch)
            if cw == 0:
                # Zero-width (combining) chars ride with the preceding prefix.
                head_chars.append(ch)
                pos += 1
                continue
            if cw > width and remaining == width:
                # Fresh row (no columns taken, zero-width marks aside): this
                # char can never fit at this width — drop it here so it can't
                # force an empty take.
                consumed += cw
                pos += 1
                continue
            if cw > remaining:
                break
            head_chars.append(ch)
            remaining -= cw
            consumed += cw
            pos += 1
            if remaining == 0:
                break
        if head_chars:
            prefix.append(("".join(head_chars), run[1], run[2]))
        if pos >= len(text) and remaining > 0:
            continue
        rest: _StyledRuns = []
        tail = text[pos:]
        if tail:
            rest.append((tail, run[1], run[2]))
        rest.extend(r for r in runs[idx + 1 :] if r[0])
        return prefix, rest, consumed
    return prefix, [], consumed


def _ref_grid(lanes: list[list[str | None] | None], width: int) -> list[list[str | None]] | None:
    """Collapse per-row ref lanes into a full grid — ``None`` when no row has
    refs, so the common case allocates nothing."""
    if any(lane is not None for lane in lanes):
        return [lane if lane is not None else [None] * width for lane in lanes]
    return None


def _char_wrap_runs(
    runs: _StyledRuns, width: int, pad_style: Style
) -> tuple[list[list[Cell]], list[list[str | None]] | None]:
    """Wrap a styled-run stream at any character boundary by display width.

    Returns the cell rows plus a parallel grid of ref rows (see `_ref_grid`).
    A char wider than ``width`` itself is unrepresentable and dropped.
    """
    rows: list[list[Cell]] = []
    lanes: list[list[str | None] | None] = []
    rest = [r for r in runs if r[0]]
    while rest:
        prefix, rest, _consumed = _take_runs_prefix(rest, width)
        if not prefix:
            break  # stream drained by unrepresentable chars — no phantom row
        cells, refs = _cells_from_runs(prefix)
        if not cells:
            # A combining-marks-only prefix materializes to nothing (zero-width
            # chars occupy no cell) — emitting it would be a phantom blank row.
            continue
        rows.append(_pad_row(cells, width, pad_style))
        lanes.append(_pad_refs(refs, width) if refs is not None else None)
    if not rows:
        rows.append(_pad_row([], width, pad_style))
        lanes.append(None)
    return rows, _ref_grid(lanes, width)


_SPACE_RE = re.compile(r"( +)")


def _word_wrap_runs(runs: _StyledRuns, width: int) -> list[_StyledRuns]:
    """Break a styled-run stream at word boundaries to fit within width.

    Source spaces (and their styles) are preserved between words on the same
    line; the break space at a wrap point is dropped (lines are right-trimmed).
    """
    if width <= 0:
        return [[]]

    # Group into alternating space / non-space segments, style + ref preserved
    # across run boundaries (a word split across two spans is one segment).
    segments: list[tuple[bool, _StyledRuns]] = []
    for text, style, ref in runs:
        for token in _SPACE_RE.split(text):
            if not token:
                continue
            sp = token[0] == " "
            if segments and segments[-1][0] == sp:
                segments[-1][1].append((token, style, ref))
            else:
                segments.append((sp, [(token, style, ref)]))

    lines: list[_StyledRuns] = []
    line: _StyledRuns = []
    line_w = 0
    pending: _StyledRuns = []  # space segment awaiting a following word

    for is_sp, seg in segments:
        if is_sp:
            pending = seg
            continue

        word_w = _runs_width(seg)
        if line:
            sp_w = _runs_width(pending)
            if line_w + sp_w + word_w <= width:
                # `line` is always a freshly owned list here — safe to extend.
                line.extend(pending)
                line.extend(seg)
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
            rest_w = word_w
            while rest and rest_w > width:
                prefix, rest, consumed = _take_runs_prefix(rest, width)
                rest_w -= consumed
                if not prefix:
                    break  # stream drained by unrepresentable chars
                lines.append(prefix)
            line = list(rest)
            line_w = rest_w

    # Emit the trailing line, but only if it carries content or is the sole row.
    # A final word that is entirely unrepresentable (e.g. a width-2 char in a
    # width-1 budget) drains ``line`` to empty after the wrap above; appending it
    # unconditionally would add a phantom blank row, inflating height and
    # diverging from the legacy ``lines if lines else ['']`` contract. Mirrors
    # the guard in ``_char_wrap_runs``.
    if line or not lines:
        lines.append(line)
    return lines


def _split_runs_newlines(runs: _StyledRuns) -> list[_StyledRuns]:
    """Split a styled-run stream on newlines — declared line structure.

    A ``\\n`` is a hard break; a ``\\r`` immediately before it (even at the
    end of the previous run) is part of the same break (CRLF), not content.
    Mirrors ``_split_lines`` one rung up in style richness (decision
    practice/block-text-honors-newlines).
    """
    segments: list[_StyledRuns] = [[]]
    for text, style, ref in runs:
        if "\n" not in text:
            if text:
                segments[-1].append((text, style, ref))
            continue
        for i, part in enumerate(text.split("\n")):
            if i:
                seg = segments[-1]
                if seg and seg[-1][0].endswith("\r"):
                    last_text, last_style, last_ref = seg[-1]
                    if len(last_text) > 1:
                        seg[-1] = (last_text[:-1], last_style, last_ref)
                    else:
                        seg.pop()
                segments.append([])
            if part:
                segments[-1].append((part, style, ref))
    return segments


def _row_block(
    cells: list[Cell],
    refs: list[str | None] | None,
    width: int,
    pad_style: Style,
    ref: str | None,
) -> Block:
    """Pad one materialized row to width and freeze it as a single-row Block."""
    cells = _pad_row(cells, width, pad_style)
    if refs is not None:
        return Block._create((tuple(cells),), width, ref=ref, refs=(tuple(_pad_refs(refs, width)),))
    return Block._create((tuple(cells),), width, ref=ref)


def _wrap_runs(
    runs: _StyledRuns,
    width: int | None,
    *,
    wrap: Wrap = Wrap.WORD,
    pad_style: Style = Style(),
    ref: str | None = None,
) -> Block:
    """Wrap a styled-run stream into a Block — the seam behind `Line.wrap`,
    `Line.to_block`, and `Block.text`'s width-honoring modes.

    `pad_style` styles the trailing pad cells (and the ellipsis marker); it is
    the reflowing generalization of `Line.to_block` (which is `Wrap.NONE` per
    segment). A newline in any run is a hard break: segments split first, the
    wrap mode applies within each segment, and the segment rows stack
    (decision practice/block-text-honors-newlines). `ref` is the block-level
    denotation (`Block.text(ref=)`); per-run refs ride the ref lane.

    ``width=None`` sizes naturally (the width contract: absent is natural) —
    the widest declared line sets the width, nothing reflows or clips, and
    all-blank lines keep their zero-width rows (structure survives natural
    zero width). An explicitly nonpositive ``width`` keeps the empty-block
    contract and collapses before the split.
    """
    if width is not None and width <= 0:
        return Block([[]], 0, ref=ref)

    if any("\n" in run[0] for run in runs):
        from .compose import join_vertical

        segments = _split_runs_newlines(runs)
        if width is None:
            width = max(_runs_width(segment) for segment in segments)
            if width <= 0:
                return Block([[] for _ in segments], 0, ref=ref)
        stacked = join_vertical(
            *(_wrap_runs(segment, width, wrap=wrap, pad_style=pad_style) for segment in segments)
        )
        if ref is None:
            return stacked
        return Block._create(stacked._rows, stacked.width, ref=ref, refs=stacked._refs)

    if width is None:
        # Natural sizing of one declared line: materialize in full — no
        # budget, so the wrap mode is moot.
        cells, refs = _cells_from_runs(runs)
        return _row_block(cells, refs, len(cells), pad_style, ref)

    if wrap == Wrap.CHAR:
        char_rows, ref_rows = _char_wrap_runs(runs, width, pad_style)
        return Block(char_rows, width, ref=ref, refs=ref_rows)

    if wrap == Wrap.WORD:
        lines = _word_wrap_runs(runs, width)
        word_rows = []
        lanes: list[list[str | None] | None] = []
        for line in lines:
            # Each wrapped line fits the width by construction — no budget.
            cells, refs = _cells_from_runs(line)
            word_rows.append(_pad_row(cells, width, pad_style))
            lanes.append(_pad_refs(refs, width) if refs is not None else None)
        return Block(word_rows, width, ref=ref, refs=_ref_grid(lanes, width))

    if wrap == Wrap.NONE:
        cells, refs = _cells_from_runs(runs, max_width=width)
        return _row_block(cells, refs, width, pad_style, ref)

    if wrap == Wrap.ELLIPSIS:
        if _runs_width(runs) <= width:
            cells, refs = _cells_from_runs(runs, max_width=width)
        else:
            from ..icon_set import current_icons

            ellipsis = current_icons().ellipsis
            ell_w = display_width(ellipsis)
            ell_runs: _StyledRuns = [(ellipsis, pad_style, None)]
            if ell_w >= width:
                cells, refs = _cells_from_runs(ell_runs, max_width=width)
            else:
                cells, refs = _cells_from_runs(runs, max_width=width - ell_w)
                ell_cells, _ = _cells_from_runs(ell_runs)
                if refs is not None:
                    # The marker denotes nothing — it is loss evidence, not content.
                    refs.extend([None] * len(ell_cells))
                cells.extend(ell_cells)
        return _row_block(cells, refs, width, pad_style, ref)

    raise ContractError(f"Unknown wrap mode: {wrap}")
