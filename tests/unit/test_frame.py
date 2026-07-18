"""Unit tests for the host-rung evidence row + frame assembly (HOST_RUNG §6).

The specific branches of the F-conditional algorithm and the evidence row's
contract: F=0 (evidence waived), fit-pad, overflow, F=1-overflow, ASCII
degradation, the ref-carrying row, and row-count (not entry-count) wording.
The invariants that must hold for *any* input live in
``tests/property/test_frame_assembly.py``.
"""

from __future__ import annotations

import pytest

from painted.core.block import Block
from painted.core.cell import Style
from painted.core.errors import ContractError
from painted.core._text_width import char_width, display_width
from painted.icon_set import ASCII_ICONS, use_icons
from painted.views import assemble_frame, evidence_row
from tests.helpers import row_text
from tests.property.strategies import has_orphan_wide


def _content(n: int, width: int = 24) -> Block:
    """A natural-height content Block of ``n`` distinct rows.

    Width is comfortably wider than the evidence marker so overflow assertions
    read the full wording (the evidence row clips to content width — a row,
    never a rail — which is exercised directly in ``TestEvidenceRow``).
    """
    return Block.column([(f"row{i}", Style()) for i in range(n)], width=width)


# --- assemble_frame branches -------------------------------------------------


class TestAssembleFrame:
    def test_f0_is_empty_and_waives_evidence(self) -> None:
        """F=0: a zero-height frame, no evidence row (the §5 degenerate rule)."""
        frame = assemble_frame(_content(10), 0, 0)
        assert frame.height == 0
        assert frame.width == 24  # width preserved even at zero height

    def test_fits_is_shown_and_padded(self) -> None:
        """content shorter than F is shown top-anchored and bottom-padded to F."""
        frame = assemble_frame(_content(3), 6, 0)
        assert frame.height == 6
        assert [row_text(frame, y).rstrip() for y in range(3)] == ["row0", "row1", "row2"]
        # The tail is padding, not evidence.
        assert row_text(frame, 5).strip() == ""

    def test_fits_exactly_is_content_unchanged(self) -> None:
        content = _content(5)
        frame = assemble_frame(content, 5, 0)
        assert frame.height == 5
        assert [row_text(frame, y) for y in range(5)] == [row_text(content, y) for y in range(5)]

    def test_overflow_shows_f_minus_1_rows_plus_evidence(self) -> None:
        """F-1 content rows sliced at the offset, then one evidence row."""
        frame = assemble_frame(_content(10), 5, 0)
        assert frame.height == 5
        assert [row_text(frame, y).rstrip() for y in range(4)] == [
            "row0",
            "row1",
            "row2",
            "row3",
        ]
        # 10 rows, 4 shown from top → 6 hidden below.
        assert "6 more rows" in row_text(frame, 4)

    def test_overflow_at_offset_counts_both_directions(self) -> None:
        frame = assemble_frame(_content(10), 5, 3)
        evidence = row_text(frame, 4)
        # offset 3, 4 rows shown [3..6] → 3 above, 3 below → 6 total hidden.
        assert "6 more rows" in evidence
        assert ASCII_ICONS.ellipsis != evidence  # sanity: not the ASCII marker under default

    def test_f1_overflow_is_a_single_evidence_row(self) -> None:
        """At F=1 with overflow the one row is the evidence row (InPlace precedent)."""
        frame = assemble_frame(_content(10), 1, 0)
        assert frame.height == 1
        assert "more rows" in row_text(frame, 0)

    def test_negative_height_fails_loudly(self) -> None:
        with pytest.raises(ContractError):
            assemble_frame(_content(10), -1, 0)

    def test_offset_is_clamped_for_exact_height(self) -> None:
        """An out-of-range offset still yields exactly F rows (no stored state)."""
        frame = assemble_frame(_content(10), 4, 10_000)
        assert frame.height == 4
        # Clamped to the bottom: last content row visible, nothing below.
        assert "row9" in row_text(frame, 2)

    def test_zero_width_content_stays_zero_width(self) -> None:
        """Zero-width content overflowing a frame keeps width 0 through the
        evidence row — the evidence builder is exercised at width 0."""
        content = Block.empty(0, 10)  # 10 rows, zero columns
        frame = assemble_frame(content, 4, 0)
        assert frame.height == 4
        assert frame.width == 0


# --- evidence_row contract ---------------------------------------------------


class TestEvidenceRow:
    def test_exact_width_clip_and_pad(self) -> None:
        assert evidence_row(0, 5, 40).width == 40
        assert evidence_row(0, 5, 3).width == 3  # clipped, never wider

    def test_counts_rows_not_entries(self) -> None:
        """Default wording is row counts — the noun is 'rows'."""
        text = row_text(evidence_row(0, 763, 40), 0)
        assert "763 more rows" in text
        assert "entries" not in text

    def test_direction_below_only(self) -> None:
        text = row_text(evidence_row(0, 5, 40), 0)
        assert "▼" in text and "▲" not in text

    def test_direction_above_only(self) -> None:
        text = row_text(evidence_row(5, 0, 40), 0)
        assert "▲" in text and "▼" not in text

    def test_direction_both(self) -> None:
        text = row_text(evidence_row(2, 3, 40), 0)
        assert "▲" in text and "▼" in text
        assert "5 more rows" in text  # total hidden

    def test_ascii_degradation(self) -> None:
        with use_icons(ASCII_ICONS):
            text = row_text(evidence_row(0, 5, 40), 0)
        assert "..." in text and "v" in text
        assert "▼" not in text and "…" not in text

    def test_label_seam_substitutes_wording(self) -> None:
        """A caller-supplied label replaces the row-count noun phrase."""
        text = row_text(evidence_row(0, 5, 40, label="763 older ticks"), 0)
        assert "763 older ticks" in text
        assert "more rows" not in text

    def test_ref_carries_denotation(self) -> None:
        row = evidence_row(0, 5, 40, ref="scroll:below")
        assert row.cell_ref(0, 0) == "scroll:below"
        assert row.cell_ref(10, 0) == "scroll:below"

    def test_negative_counts_clamp(self) -> None:
        # A degenerate negative count is treated as zero, not a crash.
        text = row_text(evidence_row(-3, 5, 40), 0)
        assert "5 more rows" in text

    def test_zero_width_is_one_empty_row(self) -> None:
        """Width 0 is a valid (degenerate) evidence row: one row, zero columns."""
        row = evidence_row(0, 5, 0)
        assert row.width == 0
        assert row.height == 1

    def test_wide_glyph_clips_by_display_width(self) -> None:
        """The width contract is display columns, not len(): a wide-glyph label
        clipped mid-glyph yields exactly ``width`` columns and splits no 2-column
        glyph (no orphaned wide lead — the cell-buffer wide-char invariant)."""
        label = "日本語テスト"  # six 2-display-column CJK glyphs

        # Locate where the label begins (past the "… ▼ " prefix), measured in
        # display columns so it is robust to the prefix glyphs' widths.
        full_text = row_text(evidence_row(0, 5, 40, label=label), 0)
        label_col = display_width(full_text[: full_text.index(label[0])])

        # Clip 3 columns into the label's wide-glyph run: the first CJK glyph
        # (2 cols) lands in the visible region and the boundary bisects the
        # second, which must be dropped-and-padded, never orphaned.
        width = label_col + 3
        row = evidence_row(0, 5, width, label=label)
        assert row.width == width
        assert not has_orphan_wide(row.row(0))
        # Non-vacuity: a wide glyph really did reach the clipped region.
        assert any(char_width(c.char) == 2 for c in row.row(0))
