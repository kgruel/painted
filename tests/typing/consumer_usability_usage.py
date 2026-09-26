"""Consumer additions keep their return types through the taught lazy facades.

Checked by ty, never executed. List normalization is a runtime defense; the
existing tuple annotations still describe stored state, not a widened constructor.
"""

from typing import assert_type

from painted.core.block import Block
from painted.core.span import Line, Span
from painted.views import table_lens
from painted.views.lens import table_lens as lens_table_lens
from painted.views.lens.table import table_lens as concrete_table_lens


def _typecheck() -> None:
    assert_type(Block.text("hi"), Block)
    assert_type(Line((Span("hi"),)), Line)
    assert_type(table_lens([{"a": 1}], 1), Block)
    assert_type(lens_table_lens([{"a": 1}], 1, width=20), Block)
    assert_type(concrete_table_lens([{"a": 1}], 1), Block)
