"""Deterministic, non-TTY Surface test harness.

This module provides a small runner that exercises a Surface's render loop
without touching the real terminal (no alt screen, no cbreak/raw mode, no
signals). It is intended for pytest/CI usage.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TextIO

from ..mouse import MouseEvent
from .surface import Surface
from ..core.buffer import Buffer, CellWrite
from ..core.writer import ColorDepth, Writer

InputItem = str | MouseEvent


def buffer_to_lines(buf: Buffer) -> list[str]:
    """Return the buffer as a list of text lines (characters only)."""
    width = buf.width
    cells = buf._cells
    out: list[str] = []
    append = out.append
    row_start = 0
    for _ in range(buf.height):
        row_end = row_start + width
        append("".join(cell.char for cell in cells[row_start:row_end]))
        row_start = row_end
    return out


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """A captured render result from a single flush."""

    buffer: Buffer
    writes: tuple[CellWrite, ...]
    _lines_cache: list[str] | None = field(default=None, init=False, repr=False)
    _text_cache: str | None = field(default=None, init=False, repr=False)

    @property
    def lines(self) -> list[str]:
        cached = self._lines_cache
        if cached is None:
            cached = buffer_to_lines(self.buffer)
            object.__setattr__(self, "_lines_cache", cached)
        return cached

    @property
    def text(self) -> str:
        cached = self._text_cache
        if cached is None:
            cached = "\n".join(self.lines)
            object.__setattr__(self, "_text_cache", cached)
        return cached


class TestSurface:
    """Deterministic Surface runner for tests.

    Example:
        app = MySurface()
        harness = TestSurface(app, width=20, height=5, input_queue=["j", "q"])
        frames = harness.run_to_completion()
        assert "hello" in frames[0].text
    """

    # Prevent pytest from trying to collect this as a test case when imported.
    __test__ = False

    def __init__(
        self,
        surface: Surface,
        *,
        width: int,
        height: int,
        color_depth: ColorDepth = ColorDepth.BASIC,
        input_queue: Iterable[InputItem] = (),
        stream: TextIO | None = None,
        write_ansi: bool = False,
        capture_writes: bool = True,
    ):
        self.surface = surface
        self.width = width
        self.height = height
        self.input_queue = list(input_queue)
        self.stream = stream if stream is not None else io.StringIO()
        self.write_ansi = write_ansi
        self.capture_writes = capture_writes
        self.emissions: list[tuple[str, dict]] = []

        original_emit = self.surface._on_emit

        def _capture_emit(kind: str, data: dict) -> None:
            self.emissions.append((kind, data))
            if original_emit is not None:
                original_emit(kind, data)

        self.surface._on_emit = _capture_emit

        # Ensure the Surface has deterministic dimensions and no TTY dependency.
        # no_color=False keeps the harness hermetic: the writer resolves NO_COLOR
        # ambiently at construction, so without this a run under NO_COLOR=1 would
        # strip fg/bg from every write_ansi=True frame and the harness would stop
        # being a function of its inputs alone.
        self.surface._writer = Writer(self.stream, color_depth=color_depth, no_color=False)
        self.surface._buf = Buffer(width, height)
        self.surface._prev = Buffer(width, height)
        self.surface.layout(width, height)

    def run_to_completion(self) -> list[CapturedFrame]:
        """Run initial render + each queued input, capturing frames after flushes."""
        self.surface._running = True
        self.surface._dirty = True

        frames: list[CapturedFrame] = []

        # Initial frame (matches production loop: update() then render if dirty).
        self.surface.update()
        self._render_and_capture(frames)

        for item in self.input_queue:
            if not self.surface._running:
                break

            if isinstance(item, MouseEvent):
                self.surface.on_mouse(item)
                self.surface.emit(
                    "ui.mouse",
                    action=item.action.name,
                    button=item.button.name,
                    x=item.x,
                    y=item.y,
                    shift=item.shift,
                    meta=item.meta,
                    ctrl=item.ctrl,
                )
            else:
                self.surface.on_key(item)
                self.surface.emit("ui.key", key=item)

            # Production loop always renders after any input.
            self.surface._dirty = True

            self.surface.update()
            self._render_and_capture(frames)

        return frames

    def resize(self, width: int, height: int) -> None:
        """Simulate a terminal resize (SIGWINCH) for the harness dimensions."""
        self.width = width
        self.height = height
        self.surface._resize(width, height)

    def _render_and_capture(self, frames: list[CapturedFrame]) -> None:
        if not self.surface._dirty:
            return
        self.surface._dirty = False

        # Mirrors the production loop's bracket (Surface.run()): render and
        # flush happen inside one _frame_scope(), so a StreamSurface under
        # test exercises its ref_schemes= bracket exactly as it would live.
        with self.surface._frame_scope():
            self.surface.render()

            surface = self.surface
            buf = surface._buf
            prev = surface._prev
            if buf is None or prev is None:
                return

            needs_clear = surface._needs_clear
            surface._needs_clear = False

            writes: list[CellWrite]
            if self.capture_writes or self.write_ansi:
                writes = buf.diff(prev)
            else:
                writes = []

            if self.write_ansi and (writes or needs_clear):
                surface._writer.write_frame(writes, clear_first=needs_clear)

            # Snapshot once: previous frame state for next diff + captured frame payload.
            snapshot = buf.clone()
            surface._prev = snapshot

            frames.append(CapturedFrame(buffer=snapshot, writes=tuple(writes)))
