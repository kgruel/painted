"""Table lens: a sequence of records, transcribed as aligned columns."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...core.block import Block
from ...core.cell import Style
from ...core.compose import Align, fit_to_width
from ...core.errors import ContractError
from ...core.span import Line
from ..components._table import AUTO, Column, TableState, table
from ._records import format_value, record_fields

if TYPE_CHECKING:
    from ...core.fidelity import Fidelity

__all__ = ["table_lens"]


def _is_numeric(value: Any) -> bool:
    """Numeric for alignment purposes — bool excluded, matching `_is_numeric_sequence`."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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

    **Accepted subjects** — a sequence whose items declare a field schema:
    ``dict``, dataclass instance, or ``NamedTuple``. Columns are the union of
    the declared field names in first-seen order; a row that omits one renders
    an empty cell, because that row did not declare it. A sequence of scalars
    is a single unnamed column. Anything else raises ``ContractError`` rather
    than being coerced into a shape it never declared — a bare ``dict`` included
    (``paint()``/``transcribe`` already render one as key/value, so there is
    nothing here for it to add).

    **Zoom is deliberately two-rung**: ``0`` is the count line (``3 rows x 4
    columns``), ``>= 1`` is the table with every declared column. There is no
    ladder that drops columns as zoom falls, because *column importance is not
    declared by the data* — ranking the fields of an anonymous record would be
    exactly the inference ``show()`` was corrected for. Width pressure is
    already handled honestly one rung down: ``table()`` clips and reports what
    it dropped through the ``+Nc`` badge (law 6).

    Alignment is derived, not guessed: a column whose every present value is
    numeric aligns right. The type *is* the declaration.

    Args:
        data: A sequence of records (or of scalars).
        zoom: 0 for the count line; >= 1 for the table.
        width: Exact width — the block is padded or clipped to it. None sizes
            naturally (the width law).
        columns: Explicit ``Column`` list, overriding derivation — the escape
            hatch for fixed widths, ``Fill``, or custom headers. Must match the
            derived column order; use ``table()`` directly for anything further.
        fidelity: Threaded to cell transcription for its ``chars`` budget.

    Returns:
        Block — natural height (one header row plus one row per record). No
        scroll window is opened, so no evidence row is reserved.
    """
    if isinstance(data, (str, bytes)) or not hasattr(data, "__iter__"):
        raise ContractError(
            f"table_lens needs a sequence of records; got {type(data).__name__}. "
            "Accepted: a sequence of dicts, dataclasses, or NamedTuples (or of "
            "scalars, as one column). A single mapping is already rendered as "
            "key/value by paint()."
        )
    if isinstance(data, dict):
        raise ContractError(
            "table_lens needs a sequence of records, not a single mapping; "
            "paint() already renders a dict as key/value rows. Pass a sequence "
            "of dicts (e.g. list(d.values()), or [d] for one row)."
        )

    items = list(data)

    # Column derivation: declared field names, union in first-seen order.
    names: list[str] = []
    records: list[dict[str, Any] | None] = []
    for item in items:
        record = record_fields(item)
        records.append(record)
        if record is None:
            continue
        for key in record:
            if key not in names:
                names.append(key)

    if items and not names:
        raise ContractError(
            "table_lens needs items that declare named fields (dict, dataclass, "
            f"or NamedTuple); got a sequence of {type(items[0]).__name__}. A "
            "sequence of scalars declares order, not columns — paint() already "
            "transcribes it as items."
        )

    if zoom <= 0 or not items:
        count = len(items)
        text = f"{count} row{'s' if count != 1 else ''}"
        if count:
            text += f" x {len(names)} column{'s' if len(names) != 1 else ''}"
        return Block.text(text, Style(), width=width)

    # A row that declares no schema sits in a mixed sequence; its cells are
    # empty rather than silently re-projected into someone else's columns.
    derived = []
    for name in names:
        present = [r[name] for r in records if r is not None and name in r]
        align = Align.END if present and all(_is_numeric(v) for v in present) else Align.START
        derived.append(Column(header=Line.plain(name), width=AUTO, align=align, ellipsis=True))
    rows = [
        [
            Line.plain(format_value(r[name])) if r is not None and name in r else Line.plain("")
            for name in names
        ]
        for r in records
    ]

    if columns is not None:
        if len(columns) != len(derived):
            raise ContractError(
                f"table_lens was given {len(columns)} columns but the data declares "
                f"{len(derived)} ({', '.join(names)}); the "
                "explicit list must match the derived order"
            )
        derived = columns

    state = TableState().with_count(len(rows))
    # visible_height == row count: the whole table is shown, so `table()` opens
    # no scroll window and reserves no evidence row. Natural height is the lens
    # contract; a host that cannot fit it owns that viewport (RENDER_MODEL law 6).
    block = table(state, derived, rows, visible_height=len(rows), width=width)
    if width is None:
        return block
    # `table()` treats a width as a *budget* — with no Fill column it sizes
    # naturally and leaves slack unfilled. A lens is width-EXACT (law 5, and
    # every sibling lens), so the offered width is honored here. Over-budget
    # content was already clipped (and badged) by `table()`; this pads the
    # under-budget case.
    return fit_to_width(block, width)
