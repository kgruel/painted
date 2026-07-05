"""Contract tests for the callout component.

A callout is a severity-tagged message: a colored glyph + subject, optionally
with a muted detail line, a muted "↳ hint" next-step line, and a box. The
severity drives both the glyph (ambient IconSet, so it ASCII-degrades) and the
color (ambient Palette role).

Beyond the rendering contract, three hardening invariants are pinned here (the
defects that would otherwise freeze on publish): ``severity`` is a closed
``Severity`` enum (no silent string fall-through); ``width`` is exact even with
``box=True`` (the border counts toward the budget); and an embedded newline in
``subject``/``detail``/``hint`` is collapsed so it cannot corrupt the rectangle.
"""

from __future__ import annotations

import pytest

from painted.core.errors import ContractError
from painted.icon_set import ASCII_ICONS, use_icons
from painted.palette import DEFAULT_PALETTE, use_palette
from painted.views import Severity, callout
from tests.helpers import block_to_text


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


# --- Rendering contract -------------------------------------------------------


def test_severity_glyph_and_subject() -> None:
    text = block_to_text(callout("All good", severity=Severity.SUCCESS))
    assert text.strip().startswith("✓")
    assert "All good" in text


def test_each_severity_has_its_glyph() -> None:
    for sev, glyph in {
        Severity.SUCCESS: "✓",
        Severity.INFO: "ℹ",
        Severity.WARNING: "⚠",
        Severity.ERROR: "✗",
    }.items():
        text = block_to_text(callout("msg", severity=sev))
        assert glyph in text, f"{sev} should render {glyph}"


def test_info_is_the_default_severity() -> None:
    assert "ℹ" in block_to_text(callout("note"))


def test_hint_renders_on_a_second_line_with_arrow() -> None:
    lines = _lines(
        block_to_text(
            callout("Database not found", severity=Severity.ERROR, hint="Run 'siftd ingest'")
        )
    )
    assert len(lines) == 2
    assert "✗" in lines[0] and "Database not found" in lines[0]
    assert "↳" in lines[1] and "Run 'siftd ingest'" in lines[1]


def test_detail_renders_as_a_continuation_line() -> None:
    lines = _lines(
        block_to_text(callout("Failed", severity=Severity.ERROR, detail="permission denied"))
    )
    assert len(lines) == 2
    assert "permission denied" in lines[1]


def test_ascii_degradation_swaps_glyph_and_arrow() -> None:
    with use_icons(ASCII_ICONS):
        text = block_to_text(callout("nope", severity=Severity.ERROR, hint="do x"))
    lines = _lines(text)
    assert "✗" not in text and lines[0].startswith("x") and "nope" in lines[0]
    assert "↳" not in text and "->" in lines[1]


def test_box_adds_a_border_frame() -> None:
    plain = _lines(block_to_text(callout("hi", severity=Severity.INFO)))
    boxed = _lines(block_to_text(callout("hi", severity=Severity.INFO, box=True)))
    # A 1-line callout gains a top + bottom border row when boxed.
    assert len(boxed) == len(plain) + 2


def test_color_rides_the_glyph_under_ansi() -> None:
    with use_palette(DEFAULT_PALETTE):
        colored = block_to_text(callout("bad", severity=Severity.ERROR), use_ansi=True)
        plain = block_to_text(callout("bad", severity=Severity.ERROR), use_ansi=False)
    assert "\x1b[" in colored  # the role color is applied
    assert "\x1b[" not in plain


# --- Hardening: severity is a closed enum (no silent typo fall-through) --------


def test_severity_is_a_closed_four_level_enum() -> None:
    assert {s.name for s in Severity} == {"SUCCESS", "INFO", "WARNING", "ERROR"}


def test_invalid_severity_is_rejected_with_a_clear_error() -> None:
    # The pre-hardening defect was a stringly-typed param with a silent fall-back
    # to "info" on a typo. A non-Severity value must now raise a clear, typed
    # error (ContractError — not a silent default, and not a bare KeyError
    # leaking the internal lookup). The most natural mistake is the old string
    # spelling, whose .value equals a Severity member's.
    with pytest.raises(ContractError, match="severity"):
        callout("oops", severity="error")  # type: ignore[arg-type]


# --- Hardening: width is exact, box included ----------------------------------


def test_width_without_box_is_exactly_width() -> None:
    for w in (8, 12, 40):
        assert callout("subject", severity=Severity.INFO, width=w).width == w


def test_width_clips_a_long_subject() -> None:
    block = callout("a very long subject that overflows", severity=Severity.INFO, width=12)
    assert block.width == 12


def test_box_with_width_is_exactly_width() -> None:
    # The headline defect: box=True previously returned width + 4 (border + pad),
    # violating the exact-width contract. The border must count toward the budget.
    for w in (10, 20, 40):
        block = callout("message", severity=Severity.WARNING, box=True, width=w)
        assert block.width == w, f"boxed width={w} produced {block.width}"


def test_box_with_width_smaller_than_chrome_still_honors_width() -> None:
    # Degenerate budgets (smaller than the 4-col box chrome) still clamp exactly.
    for w in (0, 1, 3, 4):
        block = callout("x", severity=Severity.ERROR, box=True, width=w)
        assert block.width == w


def test_natural_box_adds_chrome_to_content() -> None:
    plain = callout("hello there", severity=Severity.INFO)
    boxed = callout("hello there", severity=Severity.INFO, box=True)
    # Natural (width omitted): the box adds its 4 cols of chrome around content.
    assert boxed.width == plain.width + 4


# --- Hardening: embedded newlines are collapsed, never corrupt the rectangle ---


def test_newline_in_subject_stays_one_row() -> None:
    block = callout("line one\nline two", severity=Severity.INFO)
    assert block.height == 1
    assert "line one line two" in block_to_text(block)


def test_newlines_collapse_in_detail_and_hint() -> None:
    block = callout(
        "subject",
        severity=Severity.WARNING,
        detail="detail a\ndetail b",
        hint="hint a\nhint b",
    )
    assert block.height == 3  # one row each: subject, detail, hint
    rows = block_to_text(block).splitlines()
    assert "detail a detail b" in rows[1]
    assert "hint a hint b" in rows[2]


def test_tab_and_ansi_in_subject_are_neutralized() -> None:
    # D2 fully closed at the substrate: a tab or a raw ESC never survives into the
    # rendered output (a tab breaks the width contract at the terminal; a raw ESC
    # would issue control sequences). Cell neutralizes the control *byte* to a
    # space — the ESC is gone so the screen-clear can't fire; the harmless literal
    # "[2J" text remains (callout is not an ANSI parser, it just kills controls).
    text = block_to_text(callout("a\tb\x1b[2Jc", severity=Severity.INFO))
    assert "\t" not in text
    assert "\x1b" not in text
    assert "a b [2Jc" in text
