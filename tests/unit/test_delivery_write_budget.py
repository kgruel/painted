"""One-shot delivery write budget (roadmap M8, structural gate).

``print_block`` is the one-shot sink every STATIC route ends in. Its write count
must not scale with the block: a 10,000-row table piped to a file is one
``write`` call, not 20,000. Timing gates are unstable; this count is exact.
The live tiers' counterparts are pinned beside their implementations:
``test_inplace_renderer.py`` (one atomic write per frame, identical redraw
writes no rows) and ``test_diff_render.py`` (unchanged Surface frames write no
cells).
"""

from __future__ import annotations

import io

import pytest

from painted import Block, Style
from painted.core.compose import join_vertical
from painted.core.writer import print_block


class _CountingStream(io.StringIO):
    def __init__(self, *, tty: bool) -> None:
        super().__init__()
        self._tty = tty
        self.writes = 0

    def isatty(self) -> bool:
        return self._tty

    def write(self, s: str) -> int:
        self.writes += 1
        return super().write(s)


def _tall_block(rows: int) -> Block:
    return join_vertical(
        *(Block.text(f"row {i}  ", Style(fg="green" if i % 2 else None)) for i in range(rows))
    )


@pytest.mark.parametrize("tty", [False, True], ids=["plain", "ansi"])
@pytest.mark.parametrize("rows", [0, 1, 500])
def test_print_block_is_one_write_at_any_height(tty: bool, rows: int) -> None:
    stream = _CountingStream(tty=tty)
    print_block(_tall_block(rows) if rows else Block.empty(0, 0), stream)
    assert stream.writes == 1


def test_plain_output_bytes_unchanged_by_batching() -> None:
    stream = _CountingStream(tty=False)
    print_block(_tall_block(3), stream)
    assert stream.getvalue() == "row 0\nrow 1\nrow 2\n"
