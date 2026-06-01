"""Behavioral regression guards from the invariant audit.

See docs/plans/2026-05-29-invariant-audit-remediation.md. These cover the
width-awareness and record_line newline invariants that no clean static check
can express (a `len(`/`[:width]` grep is all false positives). Finding numbers
refer to that plan.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from painted import Block, Style, Zoom
from painted.core.borders import BorderChars
from painted.core.span import Line
from painted.views import chart_lens, table
from painted.views import Column, TableState
from painted.views.record import record_line

from tests.helpers import block_to_text


# --- Finding #1: table separator measured in display columns, not codepoints --
def test_table_width_uses_display_width_for_wide_separator() -> None:
    # Fullwidth vertical bar — one codepoint, two display columns.
    wide = BorderChars("+", "+", "+", "+", "-", "｜", "+")
    cols = [Column(Line.plain("A"), 3), Column(Line.plain("B"), 3)]
    rows = [[Line.plain("a1"), Line.plain("b1")]]

    block = table(TableState(), cols, rows, visible_height=1, borders=wide)

    # Width must account for the separator's 2 display columns, not len()==1:
    #   3 + 3 + display_width(sep) * (n - 1) = 6 + 2 = 8
    assert block.width == 8
    # Second column content survives (no desync from an undersized buffer).
    assert "b1" in block_to_text(block)


# --- Finding #2: chart bars must not drop the value column for wide labels ----
def test_chart_lens_preserves_value_for_combining_label() -> None:
    # A label with interior combining marks: display width 1 but len 21, so
    # len(row_text) > its display width. The "wide" sibling forces label_col >= 3
    # so the combining label survives chart's own truncation intact (otherwise
    # the marks get stripped and the mismatch never reaches the buggy slice).
    # A codepoint slice [:width] would then drop the trailing value text.
    combining = "a" + "́" * 20
    data = {combining: 10, "wide": 90}

    text = block_to_text(chart_lens(data, zoom=3, width=40))

    assert "10%" in text  # combining-label row kept its value
    assert "90%" in text  # control row unaffected


# --- Findings #5/#6: record_line emits no embedded-newline rows (default lens) -
@pytest.mark.parametrize("zoom", [Zoom.MINIMAL, Zoom.SUMMARY, Zoom.DETAILED, Zoom.FULL])
def test_record_line_no_embedded_newline_rows(zoom: Zoom) -> None:
    payload = {
        "message": "line one\nline two\nline three",
        "output": "first\nsecond",
    }
    block = record_line(datetime(2026, 5, 29, 12, 0), "log", payload, zoom, width=60)

    for y in range(block.height):
        for cell in block.row(y):
            assert cell.char != "\n", (
                f"row {y} at zoom {zoom} contains a literal newline cell "
                "(breaks the gutter rail / single-line contract)"
            )


def _block_has_newline(block: Block) -> bool:
    return any(cell.char == "\n" for y in range(block.height) for cell in block.row(y))


def test_record_line_full_still_splits_multiline_into_rows() -> None:
    # FULL fans multiline values into real rows — the fix must not regress that.
    payload = {"message": "alpha\nbeta\ngamma"}
    block = record_line(datetime(2026, 5, 29, 12, 0), "log", payload, Zoom.FULL, width=60)

    assert not _block_has_newline(block)
    text = block_to_text(block)
    assert "alpha" in text and "beta" in text and "gamma" in text
