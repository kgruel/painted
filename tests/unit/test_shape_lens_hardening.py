"""Slice 1 — hardened shape_lens: cycle detection, depth cap, declared schema.

These cover the substrate additions that let the diagnostics arc render arbitrary
values (locals, traceback payloads) without crashing: a self-referential container
must not RecursionError, a pathologically deep one must stop at the floor, and a
declared schema (dataclass / NamedTuple / Enum) renders on the spine rather than
falling through to `str()`.
"""

from __future__ import annotations

import dataclasses
import enum
import typing

from painted.views import shape_lens
from tests.helpers import block_to_text


# ---------------------------------------------------------------------------
# Cycle detection — the real RecursionError fix
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """A self-referential container emits a muted `↻ <cycle>` marker, not a crash."""

    def test_self_referential_list_does_not_recurse(self):
        # High zoom defeats the zoom-decrement bound; before the guard this raised
        # RecursionError. The regression: it must render and honor width instead.
        lst: list = []
        lst.append(lst)
        block = shape_lens(lst, 2000, 40)
        assert block.width == 40
        assert "↻ <cycle>" in block_to_text(block)

    def test_self_referential_dict_does_not_recurse(self):
        d: dict = {}
        d["self"] = d
        block = shape_lens(d, 2000, 40)
        assert block.width == 40

    def test_self_referential_dataclass_does_not_recurse(self):
        @dataclasses.dataclass
        class Node:
            child: object = None

        n = Node()
        n.child = n
        block = shape_lens(n, 2000, 40)
        assert block.width == 40
        assert "↻ <cycle>" in block_to_text(block)

    def test_mutually_referential_dicts_do_not_recurse(self):
        a: dict = {}
        b: dict = {}
        a["b"] = b
        b["a"] = a
        assert shape_lens(a, 2000, 40).width == 40


# ---------------------------------------------------------------------------
# Depth cap — the absolute floor
# ---------------------------------------------------------------------------


class TestDepthCap:
    """A deep but acyclic structure stops descending at the floor with a muted `…`."""

    def test_deep_nesting_caps_with_ellipsis(self):
        # Build a chain deeper than the floor (6) on the built-in list path (a
        # nested list never dispatches to a sub-lens). Distinct lists at each level
        # so the cycle guard never fires — only the depth cap can stop this.
        node: list = ["leaf"]
        for _ in range(12):
            node = [node]
        block = shape_lens(node, 2000, 40)
        assert block.width == 40
        assert "…" in block_to_text(block)


# ---------------------------------------------------------------------------
# Declared schema — dataclass / NamedTuple / Enum on the spine
# ---------------------------------------------------------------------------


class TestDataclassSchema:
    """A dataclass renders its fields through the dict machinery, honoring repr."""

    def test_fields_rendered_as_key_value(self):
        @dataclasses.dataclass
        class Point:
            x: int
            y: int

        text = block_to_text(shape_lens(Point(1, 2), 2, 40))
        assert "x:" in text
        assert "y:" in text
        assert "1" in text
        assert "2" in text

    def test_repr_false_field_is_suppressed(self):
        @dataclasses.dataclass
        class Cred:
            user: str
            secret: str = dataclasses.field(repr=False)

        text = block_to_text(shape_lens(Cred("alice", "hunter2"), 2, 40))
        assert "user:" in text
        assert "hunter2" not in text
        assert "secret" not in text

    def test_field_values_route_through_recursive_path(self):
        # A nested container field is rendered by the recursive path, not str()'d.
        @dataclasses.dataclass
        class Holder:
            items: list

        text = block_to_text(shape_lens(Holder([1, 2, 3]), 3, 40))
        assert "items:" in text

    def test_dataclass_type_is_not_treated_as_instance(self):
        # The class object itself is not an instance — falls through to str().
        @dataclasses.dataclass
        class Empty:
            pass

        block = shape_lens(Empty, 1, 40)
        # str() of a class object, not a rendered field table.
        assert "class" in block_to_text(block)


class TestNamedTupleSchema:
    """A NamedTuple renders its _asdict() through the dict machinery."""

    def test_named_fields_rendered(self):
        class Pt(typing.NamedTuple):
            x: int
            y: int

        text = block_to_text(shape_lens(Pt(1, 2), 2, 40))
        assert "x:" in text
        assert "y:" in text

    def test_numeric_namedtuple_honors_names_over_chart(self):
        # A plain numeric tuple charts; a NamedTuple's declared names win.
        class Size(typing.NamedTuple):
            w: int
            h: int

        text = block_to_text(shape_lens(Size(4, 8), 2, 40))
        assert "w:" in text
        assert "h:" in text


class TestEnumSchema:
    """An Enum renders as the scalar `TypeName.MEMBER` at every zoom."""

    def test_enum_member_label(self):
        class Color(enum.Enum):
            RED = 1
            GREEN = 2

        assert block_to_text(shape_lens(Color.RED, 2, 40)).strip() == "Color.RED"
        assert block_to_text(shape_lens(Color.RED, 0, 40)).strip() == "Color.RED"

    def test_int_enum_honors_name_not_value(self):
        class Level(enum.IntEnum):
            LOW = 1
            HIGH = 9

        # IntEnum is an int subclass; the declared-schema branch must win.
        assert block_to_text(shape_lens(Level.HIGH, 2, 40)).strip() == "Level.HIGH"
