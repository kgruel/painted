"""Table lens: a sequence of records, transcribed as aligned columns."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from enum import Enum
from typing import TYPE_CHECKING, Any

from ...core.block import Block
from ...core.cell import Style, scrub_control
from ...core.compose import Align, fit_to_width
from ...core.errors import ContractError
from ...core.span import Line
from ..components._table import AUTO, Column, TableState, table
from ._records import format_value, record_fields

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity

__all__ = ["table_lens"]


def _is_numeric(value: Any) -> bool:
    """Numbers declare numeric alignment; bool and Enum declare other meanings."""
    return isinstance(value, (int, float)) and not isinstance(value, (bool, Enum))


def _single_line(text: str, location: str) -> str:
    """Refuse declared breaks first, then neutralize other controls like Cell."""
    if "\n" in text or "\r" in text:
        raise ContractError(
            f"table_lens {location} must be single-line (no LF or CR); "
            "supply single-line text or use a multiline layout instead."
        )
    return scrub_control(text)


def table_lens(
    data: Any,
    zoom: int,
    width: int | None = None,
    *,
    columns: list[Column] | None = None,
    fidelity: Fidelity | None = None,
) -> Block:
    """Render a sequence of records as an aligned table.

    The lens rung of ``table()``. ``table()`` is a *stateful* component — it
    takes a ``TableState``, a ``visible_height``, and scrolls — so rendering a
    static table through it costs four steps of setup that have nothing to do
    with the data. This is the same view as a ``data -> Block`` function, which
    is the unit that ports: script (``paint(rows, lens=table_lens)``), tool
    (``run_cli``) and TUI (``Surface``) run the identical call (PAINT_DESIGN §2).
    It is a projection onto ``table()``, not a second table renderer — every
    column-width, ellipsis and overflow behavior is that component's.

    **Accepted subjects** — an ordered ``collections.abc.Sequence`` of dicts,
    dataclass instances or NamedTuples (not arbitrary Mapping rows). Bare
    records are refused before collection handling: wrap one in ``[record]``.
    Text/binary containers, sets, generators and other iterables are refused,
    never silently materialized. Unsupported rows raise ``ContractError``
    identifying their zero-based index and type, at every zoom.

    Columns are the union of declared fields in first-seen order, preserving
    dict key identity. A missing field renders an empty cell; dataclass fields
    with ``repr=False`` stay suppressed. Nonempty records with no visible
    fields show ``N rows x 0 columns`` at every zoom; empty input shows ``0 rows``.
    Formatted cells and derived/explicit headers must be single-line (no LF or
    CR), validated even at count zoom or when clipped. Other C0/C1 controls,
    including DEL, become one space each, as in Cell/transcription; explicit
    headers retain styles, refs and settings at the ``table()`` input boundary
    without mutating caller values. This does not alter ``table()``'s header
    base-style override or lack of output refs. Enum leaves preserve
    transcription's named spelling and unnamed fallback. Cells do not recurse.

    **Zoom is deliberately two-rung**: ``0`` is the count line (``3 rows x 4
    columns``), ``>= 1`` is the table with every declared column. There is no
    ladder that drops columns as zoom falls, because *column importance is not
    declared by the data* — ranking the fields of an anonymous record would be
    exactly the inference ``show()`` was corrected for. Width pressure is
    already handled honestly one rung down: ``table()`` clips and reports what
    it dropped through the ``+Nc`` badge (law 6).

    Alignment is derived, not guessed: a column whose every present value is
    an int/float (excluding bool and all Enum values) aligns right; otherwise it
    aligns left. Explicit columns retain their alignment. The type *is* the declaration.

    Args:
        data: An ordered Sequence of supported records.
        zoom: 0 for the count line; >= 1 for the table.
        width: Exact width — the block is padded or clipped to it. None sizes
            naturally (the width law). Nonpositive widths collapse before validation.
        columns: Explicit ``Column`` list, overriding derivation — the escape
            hatch for fixed widths, ``Fill``, or custom headers. Cardinality must
            match the derived columns at every zoom, even on empty input. Mismatch
            diagnostics quote field-name text, escaping controls. The override is
            positional; header text need not equal field names.
            Use ``table()`` directly for scrolling or selection.
        fidelity: Accepted for lens-call compatibility; budgets and tags are
            not currently consumed. ``zoom`` controls the two disclosure rungs.

    Returns:
        Block — natural height (header, separator, then one row per record), or
        a one-line count summary. No selection or scroll window is invented.
    """
    if width is not None and width <= 0:
        return Block.empty(0, 1)

    # Record identity takes precedence over incidental iterability (NamedTuple
    # is itself a Sequence, and a dataclass may implement __iter__).
    if record_fields(data) is not None:
        raise ContractError(
            f"table_lens needs a Sequence of records, not a bare {type(data).__name__}; "
            "pass [record] for one row, or use paint() to transcribe the record."
        )
    if isinstance(data, (str, bytes, bytearray, memoryview)) or not isinstance(data, Sequence):
        raise ContractError(
            f"table_lens needs an ordered Sequence of records; got {type(data).__name__}. "
            "Pass a Sequence of dicts, dataclass instances, or NamedTuples "
            "(not text/binary containers, sets, generators or arbitrary iterables)."
        )

    # Column derivation: declared field names, union in first-seen order.
    names: list[Any] = []
    records: list[dict[Any, Any]] = []
    for index, item in enumerate(data):
        record = record_fields(item)
        if record is None:
            raise ContractError(
                f"table_lens row {index} has unsupported type {type(item).__name__}; "
                "each row must be a dict, dataclass instance, or NamedTuple."
            )
        records.append(record)
        for key in record:
            if key not in names:
                names.append(key)

    if columns is not None and len(columns) != len(names):
        fields = f" ({', '.join(repr(str(name)) for name in names)})" if names else ""
        raise ContractError(
            f"table_lens was given {len(columns)} columns but the data declares "
            f"{len(names)}{fields}; the "
            "explicit list must match the derived order"
        )

    # Validate once, before count/empty returns or width clipping. Keep original
    # keys for lookup; only the derived header is display text.
    headers = [
        _single_line(str(name), f"derived header at column {index}")
        for index, name in enumerate(names)
    ]
    if columns is not None:
        for index, column in enumerate(columns):
            _single_line(
                "".join(span.text for span in column.header.spans),
                f"explicit header at column {index}",
            )
        # Clone only the text-bearing path; retain all column/line/span settings
        # and caller-owned values. Validation above includes split-span CRLF.
        columns = [
            replace(
                column,
                header=replace(
                    column.header,
                    spans=tuple(
                        replace(span, text=scrub_control(span.text)) for span in column.header.spans
                    ),
                ),
            )
            for column in columns
        ]
    rows = [
        [
            Line.plain(_single_line(format_value(record[name]), f"row {index}, field {name!r}"))
            if name in record
            else Line.plain("")
            for name in names
        ]
        for index, record in enumerate(records)
    ]

    if zoom <= 0 or not names:
        count = len(records)
        text = f"{count} row{'s' if count != 1 else ''}"
        if count:
            text += f" x {len(names)} column{'s' if len(names) != 1 else ''}"
        return Block.text(text, Style(), width=width)

    if columns is None:
        derived = []
        for name, header in zip(names, headers):
            present = [r[name] for r in records if name in r]
            align = Align.END if all(_is_numeric(v) for v in present) else Align.START
            derived.append(
                Column(header=Line.plain(header), width=AUTO, align=align, ellipsis=True)
            )
    else:
        derived = columns

    state = TableState().with_count(len(rows))
    # visible_height == row count: the whole table is shown, so `table()` opens
    # no scroll window and reserves no evidence row. Natural height is the lens
    # contract; a host that cannot fit it owns that viewport (RENDER_MODEL law 6).
    block = table(
        state, derived, rows, visible_height=len(rows), width=width, selected_style=Style()
    )
    if width is None:
        return block
    # `table()` treats a width as a *budget* — with no Fill column it sizes
    # naturally and leaves slack unfilled. A lens is width-EXACT (law 5, and
    # every sibling lens), so the offered width is honored here. Over-budget
    # content was already clipped (and badged) by `table()`; this pads the
    # under-budget case.
    return fit_to_width(block, width)
