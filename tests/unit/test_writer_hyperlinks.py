"""OSC 8 hyperlink delivery — the ANSI ref reader (design §5).

Two emission loops read the denotation channel: ``Writer.write_ops`` (the
Surface/TUI diff path) and ``render_row_ansi`` (the print_block/InPlaceRenderer
path). Both wrap a resolvable ref's cells in OSC 8 and hold an independent
``last_ref`` state machine parallel to ``last_style``. The three honesty gates —
a declared scheme must resolve the ref, ANSI format only, and the ``hyperlinks``
opt-out — decide whether a single byte of OSC 8 is emitted at all.
"""

from __future__ import annotations

import io

from painted import Block, Style
from painted.core.buffer import CellWrite
from painted.core.cell import Cell
from painted.core.writer import ColorDepth, ScrollOp, Writer, render_block_ansi
from painted.refs import RefScheme, use_refs

PLAIN = Style()


def _open(uri: str) -> str:
    return f"\x1b]8;;{uri}\x1b\\"


CLOSE = "\x1b]8;;\x1b\\"


def _fact(value: str = "https://loops.dev/f/{}") -> RefScheme:
    return RefScheme("fact", lambda v: value.format(v))


def _capture(ops, *, hyperlinks: bool = True) -> str:
    buf = io.StringIO()
    w = Writer(buf, color_depth=ColorDepth.TRUECOLOR, hyperlinks=hyperlinks)
    w.write_ops(ops)
    return buf.getvalue()


def _cw(x: int, y: int, ch: str, ref: str | None = None) -> CellWrite:
    return CellWrite(x, y, Cell(ch, PLAIN), ref)


class TestWriteOpsHyperlinks:
    def test_adjacent_same_ref_cells_coalesce_into_one_link(self):
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a", "fact:1"), _cw(1, 0, "b", "fact:1")])
        assert out.count(_open("https://loops.dev/f/1")) == 1
        assert out.count(CLOSE) == 1
        assert _open("https://loops.dev/f/1") + "ab" in out

    def test_ref_change_closes_then_reopens(self):
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a", "fact:1"), _cw(1, 0, "b", "fact:2")])
        assert (
            _open("https://loops.dev/f/1") + "a" + CLOSE + _open("https://loops.dev/f/2") + "b"
            in out
        )

    def test_cursor_jump_closes_link(self):
        # Same ref, but a non-adjacent write: the link must not bleed across the gap.
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a", "fact:1"), _cw(5, 0, "b", "fact:1")])
        assert out.count(_open("https://loops.dev/f/1")) == 2
        assert out.count(CLOSE) == 2

    def test_scroll_reset_closes_link(self):
        with use_refs(_fact()):
            out = _capture(
                [
                    _cw(0, 0, "a", "fact:1"),
                    ScrollOp(top=0, bottom=10, n=1),
                    _cw(2, 0, "b", "fact:1"),
                ]
            )
        # The link opened before the scroll closes before the scroll region set.
        assert _open("https://loops.dev/f/1") + "a" + CLOSE in out
        assert out.index(CLOSE) < out.index("\x1b[1;11r")

    def test_stream_end_closes_link_before_final_reset(self):
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a", "fact:1")])
        # Close the OSC 8 before the terminating SGR reset — no link leaks past.
        assert CLOSE + "\x1b[0m\x1b[?2026l" in out

    def test_ref_only_transition_emits_even_when_style_unchanged(self):
        # a: no ref; b: ref; c: no ref — all identical style. The link opens at b
        # and closes at c though the SGR never changes.
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a"), _cw(1, 0, "b", "fact:1"), _cw(2, 0, "c")])
        assert "a" + _open("https://loops.dev/f/1") + "b" + CLOSE + "c" in out


class TestWriteOpsHonestyGates:
    def test_no_scheme_declared_emits_zero_osc8(self):
        # Ref present, but no RefScheme declared → inert, zero OSC 8 bytes.
        out = _capture([_cw(0, 0, "a", "fact:1")])
        assert "\x1b]8" not in out

    def test_hyperlinks_off_emits_zero_osc8(self):
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a", "fact:1")], hyperlinks=False)
        assert "\x1b]8" not in out

    def test_resolver_declines_emits_zero_osc8(self):
        with use_refs(RefScheme("fact", lambda v: None)):
            out = _capture([_cw(0, 0, "a", "fact:1")])
        assert "\x1b]8" not in out

    def test_scheme_less_ref_emits_zero_osc8(self):
        # A scheme-less ref (the hit-testing idiom) is inert in link deliveries.
        with use_refs(_fact()):
            out = _capture([_cw(0, 0, "a", "sidebar")])
        assert "\x1b]8" not in out


def _refblock(chars: str, refs: list[str | None]) -> Block:
    row = [Cell(c, PLAIN) for c in chars]
    return Block([row], len(chars), refs=[refs])


def _render(block: Block, *, hyperlinks: bool = True) -> str:
    w = Writer(io.StringIO(), color_depth=ColorDepth.TRUECOLOR, hyperlinks=hyperlinks)
    return render_block_ansi(block, w)


class TestRenderRowAnsiHyperlinks:
    def test_adjacent_same_ref_cells_coalesce_into_one_link(self):
        with use_refs(_fact()):
            out = _render(_refblock("ab", ["fact:1", "fact:1"]))
        assert out.count(_open("https://loops.dev/f/1")) == 1
        assert out.count(CLOSE) == 1

    def test_ref_change_closes_then_reopens_within_row(self):
        with use_refs(_fact()):
            out = _render(_refblock("ab", ["fact:1", "fact:2"]))
        assert (
            _open("https://loops.dev/f/1") + "a" + CLOSE + _open("https://loops.dev/f/2") + "b"
            in out
        )

    def test_link_closes_at_row_end_before_reset_style(self):
        with use_refs(_fact()):
            out = _render(_refblock("a", ["fact:1"]))
        # An OSC 8 must never leak across the newline: close, then SGR reset, then \n.
        assert CLOSE + "\x1b[0m\n" in out

    def test_no_scheme_declared_emits_zero_osc8(self):
        out = _render(_refblock("a", ["fact:1"]))
        assert "\x1b]8" not in out

    def test_hyperlinks_off_emits_zero_osc8(self):
        with use_refs(_fact()):
            out = _render(_refblock("a", ["fact:1"]), hyperlinks=False)
        assert "\x1b]8" not in out

    def test_resolver_declines_emits_zero_osc8(self):
        with use_refs(RefScheme("fact", lambda v: None)):
            out = _render(_refblock("a", ["fact:1"]))
        assert "\x1b]8" not in out

    def test_uniform_block_ref_links_the_whole_row(self):
        # A whole-block uniform ref (Block.ref, no per-cell grid) resolves too.
        with use_refs(_fact()):
            out = _render(Block.text("ab", PLAIN, ref="fact:9"))
        assert out.count(_open("https://loops.dev/f/9")) == 1
        assert out.count(CLOSE) == 1
