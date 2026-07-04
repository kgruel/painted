"""Diagnostics under threads — the construction snapshot crosses thread boundaries.

A palette lives in a ContextVar, which does NOT propagate to worker threads.
PaintedHandler snapshots the palette (and color depth) at CONSTRUCTION, so a log
emitted from a worker renders with the aesthetic the main thread declared — not
the worker's default. This is the reason the snapshot exists; pin it.
"""

from __future__ import annotations

import io
import logging
import threading

from painted import MONO_PALETTE, PaintedHandler, Zoom, use_palette
from painted.core.writer import ColorDepth


def _emit_from_thread(handler: PaintedHandler, record: logging.LogRecord) -> None:
    t = threading.Thread(target=handler.emit, args=(record,))
    t.start()
    t.join()


def _record(level: int = logging.WARNING, msg: str = "watch") -> logging.LogRecord:
    return logging.LogRecord("wk", level, __file__, 1, msg, (), None)


def test_worker_thread_uses_construction_snapshot() -> None:
    """Handler built under a scoped MONO palette renders MONO from a worker,
    even though the worker thread sees the default palette."""
    buf = io.StringIO()
    with use_palette(MONO_PALETTE):
        handler = PaintedHandler(buf, zoom=Zoom.SUMMARY, color_depth=ColorDepth.TRUECOLOR)

    # Baseline: same handler emitting a MONO-rendered warning on the main thread.
    main_buf = io.StringIO()
    with use_palette(MONO_PALETTE):
        ref = PaintedHandler(main_buf, zoom=Zoom.SUMMARY, color_depth=ColorDepth.TRUECOLOR)
    ref.emit(_record())

    _emit_from_thread(handler, _record())

    # The worker output matches the MONO-palette main-thread output — the snapshot
    # carried, not the worker's ambient default.
    assert buf.getvalue() == main_buf.getvalue()


def test_pipe_vs_tty_depth_snapshot() -> None:
    """Forced NONE depth (pipe) emits no ANSI; forced TRUECOLOR does."""
    plain = io.StringIO()
    PaintedHandler(plain, color_depth=ColorDepth.NONE).emit(_record(logging.ERROR))
    color = io.StringIO()
    PaintedHandler(color, color_depth=ColorDepth.TRUECOLOR).emit(_record(logging.ERROR))
    assert "\x1b[" not in plain.getvalue()
    assert "\x1b[" in color.getvalue()
