"""Unit tier — the id-to-ref deprecation aliases (REFS_DESIGN §3, D2).

One test pair per row of the design doc's alias table: the old spelling still
*works* (forwards to the new behavior) and *warns* (``DeprecationWarning``,
``stacklevel`` aimed at the caller — checked here by asserting the recorded
warning's ``filename`` is this test file, not the library frame that raised
it). ``Focus.id`` is a different concept in a different subsystem and is
deliberately absent from this table.
"""

from __future__ import annotations

import warnings
from contextlib import contextmanager

import pytest

from painted.core.block import Block
from painted.core.buffer import Buffer, BufferView
from painted.core.cell import Style
from painted.core.compose import border
from painted.core.doc import Code

S = Style()


def _warns_at_caller(records: list[warnings.WarningMessage]) -> None:
    """Assert the recorded warning points at *this* file — the caller, not the
    library frame that issued it (the stacklevel discipline the design doc
    requires for every alias)."""
    assert any(r.filename == __file__ for r in records)


@contextmanager
def _no_deprecation_warning():
    """Assert the block raises no ``DeprecationWarning`` — the new spelling is
    silent, only the deprecated alias speaks."""
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        yield
    assert not any(issubclass(r.category, DeprecationWarning) for r in records)


# --- Block.text/column/empty(…, id=) -> ref= ----------------------------------


class TestBlockConstructorAliases:
    def test_text_id_forwards_to_ref(self) -> None:
        with pytest.warns(DeprecationWarning, match="Block.text\\(id=\\)") as rec:
            b = Block.text("hi", S, id="greet")
        assert b.ref == "greet"
        _warns_at_caller(rec.list)

    def test_column_id_forwards_to_ref(self) -> None:
        with pytest.warns(DeprecationWarning, match="Block.column\\(id=\\)") as rec:
            b = Block.column([("hi", S)], id="col")
        assert b.ref == "col"
        _warns_at_caller(rec.list)

    def test_empty_id_forwards_to_ref(self) -> None:
        with pytest.warns(DeprecationWarning, match="Block.empty\\(id=\\)") as rec:
            b = Block.empty(3, 2, id="bg")
        assert b.ref == "bg"
        _warns_at_caller(rec.list)


# --- Block(…, id=, ids=) -> ref=, refs= ----------------------------------------


class TestBlockInitAliases:
    def test_id_kwarg_forwards_to_ref(self) -> None:
        with pytest.warns(DeprecationWarning, match="Block\\(id=, ids=\\)") as rec:
            b = Block([[]], 0, id="box")
        assert b.ref == "box"
        _warns_at_caller(rec.list)

    def test_ids_kwarg_forwards_to_refs(self) -> None:
        from painted.core.cell import Cell

        row = [Cell("a", S), Cell("b", S)]
        with pytest.warns(DeprecationWarning, match="Block\\(id=, ids=\\)") as rec:
            b = Block([row], 2, ids=[["x", "y"]])
        assert b._refs == (("x", "y"),)
        _warns_at_caller(rec.list)

    def test_no_warning_when_neither_alias_passed(self) -> None:
        with _no_deprecation_warning():
            Block([[]], 0, ref="box")


# --- Block.id attribute -> Block.ref -------------------------------------------


class TestBlockIdAttributeAlias:
    def test_id_attribute_forwards_to_ref(self) -> None:
        b = Block.text("hi", S, ref="label")
        with pytest.warns(DeprecationWarning, match="Block.id is deprecated") as rec:
            value = b.id
        assert value == "label"
        _warns_at_caller(rec.list)


# --- Block.cell_id(x, y) -> Block.cell_ref(x, y) -------------------------------


class TestBlockCellIdAlias:
    def test_cell_id_forwards_to_cell_ref(self) -> None:
        b = Block.text("ab", S, ref="x")
        with pytest.warns(DeprecationWarning, match="Block.cell_id is deprecated") as rec:
            value = b.cell_id(0, 0)
        assert value == "x"
        _warns_at_caller(rec.list)


# --- border(…, id=) -> ref= -----------------------------------------------------


class TestBorderIdAlias:
    def test_border_id_forwards_to_ref(self) -> None:
        b = Block.text("X", S)
        with pytest.warns(DeprecationWarning, match="border\\(id=\\)") as rec:
            framed = border(b, id="frame")
        assert framed._refs is not None
        assert framed._refs[0][0] == "frame"  # top-left border cell
        _warns_at_caller(rec.list)


# --- Buffer.put_id(…, id) -> Buffer.put_ref(…, ref) ----------------------------


class TestBufferPutIdAlias:
    def test_put_id_forwards_to_put_ref(self) -> None:
        buf = Buffer(3, 1)
        with pytest.warns(DeprecationWarning, match="Buffer.put_id is deprecated") as rec:
            buf.put_id(0, 0, "x", S, "tag")
        assert buf.hit(0, 0) == "tag"
        _warns_at_caller(rec.list)


# --- BufferView.put_id -> BufferView.put_ref -----------------------------------


class TestBufferViewPutIdAlias:
    def test_view_put_id_forwards_to_put_ref(self) -> None:
        buf = Buffer(5, 5)
        view = buf.region(1, 1, 3, 3)
        assert isinstance(view, BufferView)
        with pytest.warns(DeprecationWarning, match="BufferView.put_id is deprecated") as rec:
            view.put_id(0, 0, "x", S, "tag")
        assert buf.hit(1, 1) == "tag"
        _warns_at_caller(rec.list)


# --- D2: Code(ref=) -> Code(src=) -----------------------------------------------


class TestCodeRefAlias:
    def test_code_ref_forwards_to_src(self) -> None:
        with pytest.warns(DeprecationWarning, match="Code\\(ref=\\)") as rec:
            code = Code(ref="py:painted.cell:Style#definition")
        assert code.src == "py:painted.cell:Style#definition"
        _warns_at_caller(rec.list)

    def test_code_src_directly_does_not_warn(self) -> None:
        with _no_deprecation_warning():
            Code(src="py:painted.cell:Style#definition")
