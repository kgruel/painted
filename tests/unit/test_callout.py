"""Contract tests for the callout component.

A callout is a severity-tagged message: a colored glyph + subject, optionally
with a muted detail line, a muted "↳ hint" next-step line, and a box. The
severity drives both the glyph (ambient IconSet, so it ASCII-degrades) and the
color (ambient Palette role).
"""

from __future__ import annotations

from painted.icon_set import ASCII_ICONS, use_icons
from painted.palette import DEFAULT_PALETTE, use_palette
from painted.views import callout
from tests.helpers import block_to_text


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def test_severity_glyph_and_subject() -> None:
    text = block_to_text(callout("All good", severity="success"))
    assert text.strip().startswith("✓")
    assert "All good" in text


def test_each_severity_has_its_glyph() -> None:
    for sev, glyph in {"success": "✓", "info": "ℹ", "warning": "⚠", "error": "✗"}.items():
        text = block_to_text(callout("msg", severity=sev))
        assert glyph in text, f"{sev} should render {glyph}"


def test_unknown_severity_falls_back_to_info() -> None:
    assert "ℹ" in block_to_text(callout("hmm", severity="bogus"))


def test_hint_renders_on_a_second_line_with_arrow() -> None:
    lines = _lines(
        block_to_text(callout("Database not found", severity="error", hint="Run 'siftd ingest'"))
    )
    assert len(lines) == 2
    assert "✗" in lines[0] and "Database not found" in lines[0]
    assert "↳" in lines[1] and "Run 'siftd ingest'" in lines[1]


def test_detail_renders_as_a_continuation_line() -> None:
    lines = _lines(block_to_text(callout("Failed", severity="error", detail="permission denied")))
    assert len(lines) == 2
    assert "permission denied" in lines[1]


def test_ascii_degradation_swaps_glyph_and_arrow() -> None:
    with use_icons(ASCII_ICONS):
        text = block_to_text(callout("nope", severity="error", hint="do x"))
    lines = _lines(text)
    assert "✗" not in text and lines[0].startswith("x") and "nope" in lines[0]
    assert "↳" not in text and "->" in lines[1]


def test_box_adds_a_border_frame() -> None:
    plain = _lines(block_to_text(callout("hi", severity="info")))
    boxed = _lines(block_to_text(callout("hi", severity="info", box=True)))
    # A 1-line callout gains a top + bottom border row when boxed.
    assert len(boxed) == len(plain) + 2


def test_color_rides_the_glyph_under_ansi() -> None:
    with use_palette(DEFAULT_PALETTE):
        colored = block_to_text(callout("bad", severity="error"), use_ansi=True)
        plain = block_to_text(callout("bad", severity="error"), use_ansi=False)
    assert "\x1b[" in colored  # the role color is applied
    assert "\x1b[" not in plain
