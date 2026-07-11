import io
import os

import pytest

from painted import Block, Cell, Style
from painted.core.errors import LifecycleError
from painted.inplace import InPlaceRenderer


def _block(rows: list[list[Cell]]) -> Block:
    width = len(rows[0]) if rows else 0
    return Block(rows, width)


class TestInPlaceRenderer:
    def test_render_writes_ansi_sequences(self):
        stream = io.StringIO()
        red = Style(fg="red")
        default = Style()
        block = _block([[Cell("A", red), Cell("B", red), Cell("C", default)]])

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block)
            renderer.finalize()

        out = stream.getvalue()
        assert "\x1b[?25l" in out  # hide cursor on enter
        assert "\x1b[?25h" in out  # show cursor on finalize
        assert "\x1b[0m\x1b[31mAB\x1b[0mC\x1b[0m\x1b[0K\n" in out

    def test_render_second_call_moves_up_and_overwrites(self):
        stream = io.StringIO()
        s = Style()
        block1 = _block([[Cell("A", s)], [Cell("B", s)]])  # height 2
        block2 = _block([[Cell("C", s)], [Cell("D", s)]])  # height 2

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block1)
            renderer.render(block2)
            renderer.finalize()

        out = stream.getvalue()
        first_frame = "\x1b[0mA\x1b[0m\x1b[0K\n\x1b[0mB\x1b[0m\x1b[0K\n"
        second_frame = "\x1b[0mC\x1b[0m\x1b[0K\n\x1b[0mD\x1b[0m\x1b[0K\n"

        assert first_frame in out
        assert second_frame in out
        assert "\x1b[2A" in out  # move up over the old frame
        assert out.index(first_frame) < out.index(second_frame)

    def test_render_has_no_blank_phase(self):
        """The anti-flicker law: a same-height redraw never blanks a line.

        Erase-line (CSI 2K) blanks content ahead of its redraw — the torn
        empty region a compositor can catch. Overwrite-in-place means it
        must not appear unless the frame shrank.
        """
        stream = io.StringIO()
        s = Style()
        block1 = _block([[Cell("A", s)], [Cell("B", s)]])
        block2 = _block([[Cell("C", s)], [Cell("D", s)]])

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block1)
            renderer.render(block2)
            renderer.finalize()

        assert "\x1b[2K" not in stream.getvalue()

    def test_same_height_redraw_diffs_unchanged_rows(self):
        """The churn law: only changed rows are rewritten; unchanged rows
        become cursor hops (CSI nB), so the write scales with the churn."""
        stream = io.StringIO()
        s = Style()
        # Letters chosen to never collide with CSI final bytes (A, B, K, ...).
        block1 = _block([[Cell("q", s)], [Cell("w", s)], [Cell("z", s)]])
        block2 = _block([[Cell("q", s)], [Cell("x", s)], [Cell("z", s)]])  # only row 1 changed

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block1)
            mark = stream.tell()
            renderer.render(block2)
            frame2 = stream.getvalue()[mark:]
            renderer.finalize()

        assert "x" in frame2
        assert "q" not in frame2 and "z" not in frame2  # unchanged rows untouched
        assert "\x1b[1B" in frame2  # hop over row 0, hop over row 2

    def test_identical_redraw_writes_no_rows(self):
        stream = io.StringIO()
        s = Style()
        block = _block([[Cell("A", s)], [Cell("B", s)]])

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block)
            mark = stream.tell()
            renderer.render(block)
            frame2 = stream.getvalue()[mark:]
            renderer.finalize()

        # Just the sync wrap and cursor motion — up over the frame, hop back down.
        assert frame2 == "\x1b[?2026h\x1b[2A\x1b[2B\x1b[?2026l"

    def test_ref_only_row_change_redraws_the_row(self):
        """Row equality includes the ref row: same glyphs + style, changed
        denotation still redraws (else a stale hyperlink lingers). Redraw happens
        even with no scheme declared — the comparison is resolver-agnostic."""
        stream = io.StringIO()
        s = Style()
        rows = [[Cell("q", s)], [Cell("w", s)], [Cell("z", s)]]
        block1 = Block(rows, 1, refs=[["fact:a"], ["fact:b"], ["fact:c"]])
        block2 = Block(rows, 1, refs=[["fact:a"], ["fact:X"], ["fact:c"]])  # row 1 ref changed

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block1)
            mark = stream.tell()
            renderer.render(block2)
            frame2 = stream.getvalue()[mark:]
            renderer.finalize()

        assert "w" in frame2  # the ref-changed row is rewritten
        assert "q" not in frame2 and "z" not in frame2  # unchanged rows hopped
        assert "\x1b[1B" in frame2

    def test_identical_rows_including_refs_are_not_redrawn(self):
        stream = io.StringIO()
        s = Style()
        rows = [[Cell("A", s)], [Cell("B", s)]]
        block = Block(rows, 1, refs=[["fact:a"], ["fact:b"]])

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block)
            mark = stream.tell()
            renderer.render(block)
            frame2 = stream.getvalue()[mark:]
            renderer.finalize()

        assert frame2 == "\x1b[?2026h\x1b[2A\x1b[2B\x1b[?2026l"

    def test_clear_forgets_the_previous_frame(self):
        """After clear() the screen is blank; the next render must not diff
        against a frame that is no longer on screen."""
        stream = io.StringIO()
        s = Style()
        block = _block([[Cell("A", s)], [Cell("B", s)]])

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block)
            renderer.clear()
            mark = stream.tell()
            renderer.render(block)  # identical block — but must be fully redrawn
            renderer.finalize()

        frame2 = stream.getvalue()[mark:]
        assert "A" in frame2 and "B" in frame2

    def test_render_emits_one_synchronized_atomic_write(self):
        """Each frame: exactly one stream.write, wrapped in DEC 2026 markers."""
        writes: list[str] = []

        class Spy(io.StringIO):
            def write(self, text: str) -> int:
                writes.append(text)
                return super().write(text)

        stream = Spy()
        s = Style()
        with InPlaceRenderer(stream) as renderer:
            writes.clear()
            renderer.render(_block([[Cell("A", s)]]))
            (frame,) = writes
            assert frame.startswith("\x1b[?2026h")
            assert frame.endswith("\x1b[?2026l")
            renderer.finalize()

    def test_render_outside_context_raises(self):
        stream = io.StringIO()
        block = Block.text("hi", Style())
        renderer = InPlaceRenderer(stream)

        with pytest.raises(LifecycleError, match="outside of a context manager"):
            renderer.render(block)

    def test_finalize_shows_cursor_and_deactivates(self):
        stream = io.StringIO()
        block = Block.text("ok", Style())

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block)
            renderer.finalize()
            assert renderer._active is False

        out = stream.getvalue()
        assert "\x1b[?25h" in out

    def test_exit_after_finalize_does_not_double_show_cursor(self):
        stream = io.StringIO()

        with InPlaceRenderer(stream) as renderer:
            renderer.finalize()

        out = stream.getvalue()
        assert out.count("\x1b[?25h") == 1

    def test_clear_clears_content_and_resets_height(self):
        stream = io.StringIO()
        s = Style()
        block2 = _block([[Cell("A", s)], [Cell("B", s)]])  # height 2
        block1 = _block([[Cell("C", s)]])  # height 1
        clear_seq = "\x1b[2A\x1b[2K\n\x1b[2K\n\x1b[2A"

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block2)
            renderer.clear()
            assert renderer._height == 0
            renderer.render(block1)
            renderer.finalize()

        out = stream.getvalue()
        assert out.count(clear_seq) == 1

    def test_shrinking_frame_blanks_only_leftover_rows(self):
        stream = io.StringIO()
        s = Style()
        block3 = _block([[Cell("A", s)], [Cell("B", s)], [Cell("C", s)]])  # height 3
        block1 = _block([[Cell("D", s)]])  # height 1

        with InPlaceRenderer(stream) as renderer:
            renderer.render(block3)
            assert renderer._height == 3
            renderer.render(block1)
            assert renderer._height == 1
            renderer.finalize()

        out = stream.getvalue()
        # After overwriting line 1, the two rows the frame no longer covers
        # are blanked and the cursor parks at the end of the new content.
        assert "\x1b[0K\n\x1b[2K\n\x1b[2K\n\x1b[2A" in out

    def test_clear_outside_context_raises(self):
        stream = io.StringIO()
        renderer = InPlaceRenderer(stream)

        with pytest.raises(LifecycleError, match="outside of a context manager"):
            renderer.clear()


class _TtyStream(io.StringIO):
    """A StringIO that claims a viewport — the oversized-frame gate opens."""

    def isatty(self) -> bool:
        return True


class TestOversizedFrames:
    """The declared oversized-frame behavior: clip with evidence
    (LIVE_DELIVERY_DESIGN §10, RENDER_MODEL §7 Q2b). A live frame taller
    than the viewport cannot be repainted — its top rows are already in
    scrollback — so render() keeps the head and marks the cut; the
    finalize() deposit and non-TTY streams pass through whole."""

    def _tall_block(self, height: int) -> Block:
        s = Style()
        return _block([[Cell(str(i % 10), s)] for i in range(height)])

    def test_render_clips_to_viewport_with_evidence(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((80, 5))
        )
        stream = _TtyStream()
        with InPlaceRenderer(stream) as renderer:
            renderer.render(self._tall_block(9))
            assert renderer._height == 5  # 4 content rows + the evidence row
        out = stream.getvalue()
        assert "… +5 rows" in out  # 9 authored - 4 kept, named exactly

    def test_fitting_frame_is_untouched(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((80, 5))
        )
        stream = _TtyStream()
        with InPlaceRenderer(stream) as renderer:
            renderer.render(self._tall_block(5))
            assert renderer._height == 5
        assert "rows" not in stream.getvalue()  # no false evidence without loss

    def test_non_tty_stream_is_never_clipped(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((80, 5))
        )
        stream = io.StringIO()  # no viewport, nothing to tear
        with InPlaceRenderer(stream) as renderer:
            renderer.render(self._tall_block(9))
            assert renderer._height == 9
        assert "rows" not in stream.getvalue()

    def test_finalize_deposit_writes_full_height(self, monkeypatch):
        monkeypatch.setattr(
            "shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((80, 5))
        )
        stream = _TtyStream()
        with InPlaceRenderer(stream) as renderer:
            renderer.render(self._tall_block(9))
            renderer.finalize(self._tall_block(9))
        out = stream.getvalue()
        # The deposit is history: all 9 rows land, after the clipped live frame.
        assert renderer._height == 9
        assert out.count("… +5 rows") == 1  # only the live frame carried evidence

    def test_evidence_marker_degrades_with_ascii_icons(self, monkeypatch):
        from painted import ASCII_ICONS, use_icons

        monkeypatch.setattr(
            "shutil.get_terminal_size", lambda fallback=(80, 24): os.terminal_size((80, 3))
        )
        stream = _TtyStream()
        with use_icons(ASCII_ICONS), InPlaceRenderer(stream) as renderer:
            renderer.render(self._tall_block(6))
        out = stream.getvalue()
        assert f"{ASCII_ICONS.ellipsis} +4 rows" in out
