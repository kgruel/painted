"""Property: no C0/C1 control character ever reaches a rendered cell.

``Cell.__post_init__`` neutralizes control chars to spaces, so every text
primitive — ``Block.text`` and the char/word/ellipsis wrap paths beneath it — is
guaranteed control-char-free no matter what it is handed. This fuzzes that
invariant against text deliberately mixing control chars with printable ASCII,
wide chars, and the format/private-use chars that must NOT be neutralized.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted import Block, Style, Wrap

# Control chars (the subject) + printable + the must-be-preserved cases.
_FUZZ_ALPHABET = "ab \n\t\r\x00\x07\x08\x0b\x0c\x1b\x1f\x7f\x85\x9f中😀‍─"


def _is_c0_c1(ch: str) -> bool:
    o = ord(ch)
    return o < 0x20 or 0x7F <= o <= 0x9F


@given(
    st.text(alphabet=_FUZZ_ALPHABET, max_size=40),
    st.integers(min_value=1, max_value=20),
    st.sampled_from([Wrap.NONE, Wrap.CHAR, Wrap.WORD, Wrap.ELLIPSIS]),
)
def test_no_control_char_reaches_a_cell(text: str, width: int, wrap: Wrap) -> None:
    block = Block.text(text, Style(), width=width, wrap=wrap)
    for r in range(block.height):
        for cell in block.row(r):
            assert not _is_c0_c1(cell.char), f"control char {cell.char!r} reached a cell"


@given(st.text(alphabet=_FUZZ_ALPHABET, max_size=40))
def test_no_control_char_reaches_a_cell_natural_width(text: str) -> None:
    block = Block.text(text, Style())  # width=None → natural sizing path
    for r in range(block.height):
        for cell in block.row(r):
            assert not _is_c0_c1(cell.char), f"control char {cell.char!r} reached a cell"
