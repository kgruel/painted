"""Declared-schema vocabulary, shared by the lenses that read records.

Two lenses ask the same question of a subject — *what fields does this value
declare?* — and must answer it identically: ``shape.py`` (transcription, the
``paint()`` base case) walks one record's fields, and ``table.py`` projects a
sequence of them into columns. Were they to disagree, the same data would name
different fields depending on which lens you reached for.

The module is private; its names are not, so public siblings may import them
(``painted/views/_frame.py`` sets the precedent). The rule enforcing that is
``test_public_modules_do_not_import_private_symbols_from_siblings``.
"""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any


def is_namedtuple(x: Any) -> bool:
    """A tuple carrying the NamedTuple protocol (declared field schema)."""
    return isinstance(x, tuple) and hasattr(x, "_fields") and hasattr(x, "_asdict")


def format_value(value: Any) -> str:
    """Format a scalar for display — the shared leaf spelling.

    What ``paint()`` shows for a value is what a table cell shows for it.
    """
    if value is None:
        return "None"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    return str(value)


def record_fields(item: Any) -> dict[Any, Any] | None:
    """Project one item to its declared field mapping, or None if it declares none.

    The three declared-schema shapes ``transcribe`` honors (PAINT_DESIGN §3): a
    mapping declares key->value; a dataclass and a NamedTuple each declare named
    fields. Nothing is inferred — an object declaring no field schema is not
    coaxed into one.
    """
    if isinstance(item, dict):
        return dict(item)
    if is_namedtuple(item):
        return dict(item._asdict())
    if is_dataclass(item) and not isinstance(item, type):
        # repr=False is declared suppression, as in transcribe().
        return {f.name: getattr(item, f.name) for f in fields(item) if f.repr}
    return None
