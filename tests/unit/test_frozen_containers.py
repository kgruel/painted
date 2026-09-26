"""Ratchet: a sequence field on the stable surface holds a tuple after construction.

A frozen dataclass that annotates ``tuple[X, ...]`` gets no enforcement from
Python. Pass a list and the attribute *stays* a list — and the value then works
almost everywhere: ``Line([Span("hi")])`` measures, blocks and wraps correctly,
then raises ``TypeError: can only concatenate list (not "tuple") to list`` four
frames away inside ``table()``'s cell padding, where the list first meets a
tuple concatenation. The declaration violation surfaces nowhere near its cause.

The rule this pins is older than the bug. ``IconSet.spinner`` and
``Vocabulary.values`` already coerced, each with its own comment explaining why
— but the rule lived only in whoever remembered to apply it, so siblings
drifted: ``IconSet.sparkline`` did *not* coerce while ``IconSet.spinner``,
three fields up in the same class, did. That is the shape of an invariant that
survives on review vigilance alone.

Two annotations are honest here and the ratchet accepts both, because the
invariant is about what the field *stores*, not how it is spelled:
``tuple[X, ...]`` states the post-construction truth (``Line.spans``), while
``Sequence[X]`` states what the constructor accepts (``IconSet.spinner``).
Either way the stored value must be a tuple — a frozen value that kept the
caller's list could be mutated through a retained reference, and every one of
these is read at render time, so that mutation would be observable.

So the ratchet is **discovery-driven**, not a list of classes someone thought
of: it reflects over every public frozen dataclass on the semver-stable surface
(``painted.core`` + ``painted.views``), finds every caller-settable field
declared as a ``tuple``, and requires each one to have a probe below proving it
normalizes. A new tuple field ships with a probe or the suite goes red — the
enumeration is what makes forgetting impossible, and it is the reason this test
executes (tier 2) rather than AST-parsing (tier 0).

``EXEMPT`` is shrink-only: entries may be removed, never added, without a ruling
recorded here. It is empty, and that is the point.
"""

from __future__ import annotations

import collections.abc
import dataclasses
import importlib
import typing

import pytest

import painted.core
import painted.views
from painted.core import Style
from painted.core.doc import Def

# Stable-surface namespaces this ratchet covers.
_NAMESPACES = ("painted.core", "painted.views")

# The generic origins that mean "a sequence this frozen value stores".
_SEQUENCE_ORIGINS = (tuple, collections.abc.Sequence)

# Fields ruled exempt from normalization. SHRINK-ONLY: removing an entry is a
# fix; adding one needs a recorded ruling for why that field may hold a list.
EXEMPT: frozenset[tuple[str, str]] = frozenset()

# One probe per tuple-declared field: build the value with a **list** in that
# field and hand back the instance. The assertion is uniform (the attribute is a
# tuple afterwards); only construction differs, because required arguments do.
PROBES: dict[tuple[str, str], object] = {
    ("Line", "spans"): lambda: painted.core.Line(spans=[]),
    ("Doc", "body"): lambda: painted.core.Doc(title=None, body=[]),
    ("Section", "body"): lambda: painted.core.Section(heading="h", body=[]),
    ("Defs", "items"): lambda: painted.core.Defs(items=[Def(term="t", summary="s")]),
    ("Items", "entries"): lambda: painted.core.Items(entries=["a"]),
    ("Palette", "series"): lambda: painted.views.Palette(series=[Style()]),
    ("IconSet", "spinner"): lambda: painted.views.IconSet(spinner=["a"]),
    ("IconSet", "sparkline"): lambda: painted.views.IconSet(sparkline=["a"]),
    ("SpinnerFrames", "frames"): lambda: painted.views.SpinnerFrames(frames=["a"]),
    ("Vocabulary", "values"): lambda: painted.views.Vocabulary(
        name="v", values=["a"], roles={"a": "accent"}
    ),
    ("DataNode", "path"): lambda: painted.views.DataNode(
        key="k", value=1, depth=0, path=["p"], expandable=False, expanded=False
    ),
}


def _sequence_fields() -> list[tuple[str, str]]:
    """Every caller-settable sequence-declared field on the stable surface.

    Both honest spellings count — ``tuple[X, ...]`` and ``Sequence[X]``.
    ``init=False`` fields are skipped: they are computed in ``__post_init__``
    (``Vocabulary._app_roles``), never handed in by a caller, so no caller can
    put a list there. ``str``/``bytes`` annotations have no generic origin and
    so never match, which is what keeps plain text fields out.
    """
    found: list[tuple[str, str]] = []
    for modname in _NAMESPACES:
        mod = importlib.import_module(modname)
        for name in mod.__all__:
            obj = getattr(mod, name, None)
            if not (isinstance(obj, type) and dataclasses.is_dataclass(obj)):
                continue
            params = getattr(obj, "__dataclass_params__", None)
            if not (params and params.frozen):
                continue
            hints = typing.get_type_hints(obj)
            for f in dataclasses.fields(obj):
                if not f.init:
                    continue
                if typing.get_origin(hints.get(f.name)) in _SEQUENCE_ORIGINS:
                    found.append((name, f.name))
    return found


def test_every_tuple_field_has_a_probe_or_an_exemption():
    """The enumeration half: nothing on the stable surface escapes unnoticed."""
    discovered = set(_sequence_fields())
    covered = set(PROBES) | EXEMPT
    missing = discovered - covered
    assert not missing, (
        "sequence fields on the stable surface with no normalization probe: "
        f"{sorted(missing)}. Add a probe to PROBES (and a __post_init__ calling "
        "painted.core._normalize.freeze_fields) so the annotation stays true."
    )
    stale = covered - discovered - EXEMPT
    assert not stale, f"PROBES entries for fields that no longer exist: {sorted(stale)}"


@pytest.mark.parametrize("key", sorted(PROBES), ids=lambda k: f"{k[0]}.{k[1]}")
def test_tuple_field_normalizes_a_list(key: tuple[str, str]):
    """The behavior half: constructed from a list, the field reads back a tuple."""
    cls_name, field_name = key
    instance = PROBES[key]()  # type: ignore[operator]
    value = getattr(instance, field_name)
    assert type(value) is tuple, (
        f"{cls_name}.{field_name} is a declared sequence field but held "
        f"{type(value).__name__} after construction from a list"
    )


@pytest.mark.parametrize("key", sorted(PROBES), ids=lambda k: f"{k[0]}.{k[1]}")
def test_sequence_fields_detach_caller_lists_on_replace(key: tuple[str, str]):
    """Construction and dataclasses.replace must both sever the mutable alias."""
    _, field_name = key
    original = PROBES[key]()  # type: ignore[operator]
    expected = getattr(original, field_name)
    source = list(expected)
    updated = dataclasses.replace(original, **{field_name: source})
    source.append(object())
    assert getattr(updated, field_name) == expected
    assert type(getattr(updated, field_name)) is tuple
    assert getattr(original, field_name) == expected


def test_line_from_list_survives_table_padding():
    """The downstream consumer's exact failure, through the public component."""
    from painted.core import Line, Span
    from painted.views import Column, TableState, table

    spans = [Span("x")]
    line = Line(spans)
    spans.append(Span("not part of the line"))
    block = table(
        TableState().with_count(1),
        [Column(header=Line.plain("wide"))],
        [[line]],
        visible_height=1,
    )
    assert "".join(cell.char for cell in block.row(2)) == "x   "


def test_exempt_set_is_empty_and_shrink_only():
    """Guards the docstring's claim. If this ever fails, a ruling is owed."""
    assert EXEMPT == frozenset(), (
        "EXEMPT gained an entry. It is shrink-only: record the ruling for why "
        "this field may hold a list in the module docstring."
    )
