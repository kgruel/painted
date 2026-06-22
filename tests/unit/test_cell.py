"""Contract tests for Cell — the atomic display unit.

Two invariants are pinned: a Cell holds exactly one character, and C0/C1 control
characters are neutralized to a space at construction so they can never reach the
writer and corrupt the rendered grid (a raw TAB breaks the width contract at the
terminal; a raw ESC issues cursor/erase sequences out from under the renderer).

Critically — this is a *rendering* library — characters that are NOT C0/C1
controls must pass through untouched: zero-width joiners (emoji glue), private-use
icon glyphs (Nerd Fonts), box-drawing, and combining marks. The naive
``unicodedata.category(ch)[0] == 'C'`` filter would strip the first two; the
ordinal C0/C1 test does not.
"""

from __future__ import annotations

import pytest

from painted.core.cell import Cell, Style


def test_char_must_be_a_single_character() -> None:
    with pytest.raises(ValueError, match="single character"):
        Cell("ab", Style())


def test_c0_control_chars_become_space() -> None:
    for ch in ("\n", "\r", "\t", "\x00", "\x07", "\x08", "\x0b", "\x0c", "\x1b", "\x1f", "\x7f"):
        assert Cell(ch, Style()).char == " ", f"{ch!r} should neutralize to a space"


def test_c1_control_chars_become_space() -> None:
    for o in range(0x80, 0xA0):
        assert Cell(chr(o), Style()).char == " ", f"U+{o:04X} should neutralize to a space"


def test_printable_chars_pass_through() -> None:
    for ch in ("a", " ", "é", "中", "─", "│", "┌", "█", "▁", "→"):
        assert Cell(ch, Style()).char == ch


def test_format_and_private_use_chars_pass_through() -> None:
    # The landmine: these are categories Cf / Co / Mn, NOT C0/C1 controls, and
    # are load-bearing in a renderer. A `category[0] == 'C'` filter would wrongly
    # strip the ZWJ (breaking emoji sequences) and the private-use glyph (icon
    # fonts). The ordinal C0/C1 test leaves them alone.
    for ch in (
        "‍",  # ZERO WIDTH JOINER — emoji sequence glue (Cf)
        "‌",  # ZERO WIDTH NON-JOINER (Cf)
        "",  # private-use area — e.g. a Nerd Font icon glyph (Co)
        "́",  # COMBINING ACUTE ACCENT (Mn)
    ):
        assert Cell(ch, Style()).char == ch, f"{ch!r} must pass through untouched"


def test_style_is_preserved_when_char_is_neutralized() -> None:
    style = Style(fg="red", bold=True)
    cell = Cell("\x1b", style)
    assert cell.char == " "
    assert cell.style == style
