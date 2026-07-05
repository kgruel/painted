"""Diagnostics delivery — a logging handler and an excepthook, both renderers.

The delivery glue for the diagnostics arc. A log level is a *declared severity*
(``levelno`` thresholds collapse onto the closed ``Severity`` vocabulary); an
uncaught exception is a *record tree* (``render_traceback``). Both are rendered,
never string-formatted: ``PaintedHandler.emit`` builds a ``Block`` and writes it
under the handler lock, and ``install`` routes ``sys.excepthook`` through
``render_traceback`` + ``print_block``.

    import logging, painted
    logging.getLogger().addHandler(painted.PaintedHandler())
    painted.install()                       # uncaught tracebacks render too

This lives at the package ROOT, not in ``cli/``: the ``_CLI_SEAMS`` tripwire is
frozen at two, and nothing in ``cli/`` may import ``views``. Root modules may
import ``views`` and ``core`` freely (precedent: ``inplace.py``).
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import TYPE_CHECKING, TextIO

from .core._row_ops import row_visible_text
from .core.errors import DeclarationError
from .core.span import Line, Span
from .core.writer import ColorDepth, Writer, print_block, render_block_ansi
from .core.zoom import Zoom
from .palette import current_palette, use_palette
from .views.components._callout import Severity
from .vocabulary import SEVERITY_VOCABULARY, Thresholds, mark_style

if TYPE_CHECKING:
    from .core.block import Block
    from .core.cell import Style
    from .palette import Palette

# --- Declared thresholds -----------------------------------------------------
# A levelno floor → Severity: the mapping IS the declaration. A record's level
# resolves to the Severity of the greatest floor it clears. DEBUG collapses onto
# INFO (the journalctl principle — routine noise stays muted), CRITICAL onto
# ERROR (the palette has no louder role; Severity stays the closed 4-level set).

DEFAULT_THRESHOLDS: Mapping[int, Severity] = MappingProxyType(
    {
        logging.DEBUG: Severity.INFO,
        logging.INFO: Severity.INFO,
        logging.WARNING: Severity.WARNING,
        logging.ERROR: Severity.ERROR,
        logging.CRITICAL: Severity.ERROR,
    }
)

# Standard LogRecord attributes — everything NOT here is a caller-supplied
# `extra` field, rendered as payload continuation at DETAILED+.
_STD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
        "asctime",
    }
)


# --- Handler -----------------------------------------------------------------


class PaintedHandler(logging.Handler):
    """A ``logging.Handler`` that renders records to Blocks, not format strings.

    The severity styles, color depth, and palette are snapshotted at CONSTRUCTION:
    a ContextVar palette does not cross threads, so a worker-thread log must
    render with the same aesthetic the main thread declared. ``emit`` builds a
    Block (timestamp + severity-styled level + logger + message + ``extra``
    payload + any ``exc_info`` traceback) and writes it atomically under the
    handler lock. Any render failure routes to ``handleError`` (honoring
    ``logging.raiseExceptions``); a log emitted *during* our own render falls
    back to a plain one-liner via a thread-local reentrancy guard.
    """

    def __init__(
        self,
        stream: TextIO = sys.stderr,
        *,
        zoom: Zoom = Zoom.SUMMARY,
        width: int | None = None,
        thresholds: Mapping[int, Severity] = DEFAULT_THRESHOLDS,
        traceback_zoom: Zoom = Zoom.DETAILED,
        color_depth: ColorDepth | None = None,
    ) -> None:
        super().__init__()
        self._stream = stream
        self._zoom = zoom
        self._width = width
        self._traceback_zoom = traceback_zoom
        # Snapshot the aesthetic at construction — ContextVar state does not cross
        # threads, so this is what every emit (any thread) renders with. The
        # severity styles resolve through the built-in "severity" vocabulary under
        # the ambient state HERE, so a Theme(roles=...) active at construction is
        # captured too (same snapshot discipline as the palette).
        self._palette: Palette = current_palette()
        self._severity_styles: dict[Severity, Style] = {
            s: mark_style("severity", s.value) for s in Severity
        }
        # Compile the levelno→Severity floors once onto the ordered vocabulary; a
        # record's level resolves per-emit via `Thresholds.resolve`.
        if not thresholds:
            raise DeclarationError(
                "PaintedHandler thresholds= must declare at least one levelno "
                "floor (see DEFAULT_THRESHOLDS)"
            )
        self._compiled_thresholds = Thresholds(
            SEVERITY_VOCABULARY, {float(k): v.value for k, v in thresholds.items()}
        )
        self._color_depth = (
            color_depth if color_depth is not None else Writer(stream).detect_color_depth()
        )
        self._local = threading.local()

    def emit(self, record: logging.LogRecord) -> None:
        # Reentrancy: a log emitted while we are already rendering must not recurse
        # into another full render — degrade to a plain one-liner.
        if getattr(self._local, "in_emit", False):
            try:
                self._stream.write(record.getMessage() + "\n")
                self._stream.flush()
            except Exception:
                self.handleError(record)
            return

        self._local.in_emit = True
        try:
            with use_palette(self._palette):
                block = self._build(record)
                self._write(block)
        except Exception:
            self.handleError(record)
        finally:
            self._local.in_emit = False

    def _message(self, record: logging.LogRecord) -> str:
        """The message string. ``setFormatter`` overrides the STRING only — the
        structure (rows, gutter, traceback) stays ours."""
        if self.formatter is not None:
            record.message = record.getMessage()
            if self.formatter.usesTime():
                record.asctime = self.formatter.formatTime(record, self.formatter.datefmt)
            return self.formatter.formatMessage(record)
        return record.getMessage()

    def _build(self, record: logging.LogRecord) -> Block:
        from .core.block import Block
        from .core.compose import join_vertical

        p = current_palette()
        severity = Severity(self._compiled_thresholds.resolve(record.levelno))
        role = self._severity_styles[severity]

        message = self._message(record)
        msg_lines = message.split("\n")

        head_spans: list[Span] = []
        if self._zoom >= Zoom.SUMMARY:
            ts = time.strftime("%H:%M:%S", time.localtime(record.created))
            head_spans.append(Span(f"{ts} ", p.muted))
        head_spans.append(Span(f"{record.levelname:<8}", role))
        if self._zoom >= Zoom.SUMMARY:
            head_spans.append(Span(f" {record.name}", p.accent))
        head_spans.append(Span(f"  {msg_lines[0]}"))

        rows: list[Block] = [self._line_block(Line(tuple(head_spans)))]
        for extra in msg_lines[1:]:
            rows.append(self._line_block(Line((Span(extra),))))

        # `extra=` fields as payload continuation (DETAILED+).
        if self._zoom >= Zoom.DETAILED:
            for key in sorted(k for k in record.__dict__ if k not in _STD_ATTRS):
                value = record.__dict__[key]
                line = Line((Span(f"  {key} = ", p.muted), Span(str(value))))
                rows.append(self._line_block(line))

        # exc_info → the record tree, capped at traceback_zoom (the ceiling).
        exc = self._exc_value(record)
        if exc is not None:
            from .views import render_traceback

            tb_zoom = min(self._zoom, self._traceback_zoom)
            rows.append(render_traceback(exc, tb_zoom, self._width))

        if record.stack_info:
            for sline in str(record.stack_info).split("\n"):
                rows.append(self._line_block(Line((Span(sline, p.muted),))))

        return join_vertical(*rows) if rows else Block.text("", p.muted)

    @staticmethod
    def _exc_value(record: logging.LogRecord) -> BaseException | None:
        info = record.exc_info
        if isinstance(info, tuple) and len(info) == 3 and info[1] is not None:
            return info[1]
        return None

    def _line_block(self, line: Line) -> Block:
        """A Line as a Block, honoring the width contract (natural when None)."""
        from .core.compose import fit_to_width

        if self._width is None:
            return line.to_block(max(1, line.width))
        return fit_to_width(line.to_block(self._width), self._width)

    def _write(self, block: Block) -> None:
        """One atomic write of the rendered block under the handler lock."""
        if self._color_depth == ColorDepth.NONE:
            text = "".join(
                row_visible_text(block.row(i)).rstrip() + "\n" for i in range(block.height)
            )
        else:
            writer = Writer(self._stream, color_depth=self._color_depth)
            text = render_block_ansi(block, writer)
        self._stream.write(text)
        self._stream.flush()


# --- Excepthook install ------------------------------------------------------


def install(
    *,
    zoom: Zoom = Zoom.DETAILED,
    width: int | None = None,
    suppress: Sequence[str] = (),
    threads: bool = False,
) -> None:
    """Route uncaught exceptions through ``render_traceback`` + ``print_block``.

    Sets ``sys.excepthook``; ``threads=True`` additionally sets
    ``threading.excepthook`` (opt-in — a declared capability; ``threads=False``
    restores the stdlib thread hook, so a repeat ``install`` fully replaces the
    prior declaration — the two hooks can never disagree). A
    ``KeyboardInterrupt`` passes through to the default hook untouched, and the
    thread hook ignores ``SystemExit`` exactly as stdlib's does. The installed
    hook's output is byte-identical to the explicit
    ``print_block(render_traceback(exc, zoom, width, suppress=suppress),
    sys.stderr)`` path for the same exception and params. Should rendering
    itself ever raise, the hook falls back to the default hook with the
    ORIGINAL exception — the never-raise law holds at the delivery boundary.
    """
    from .views import render_traceback

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        try:
            print_block(render_traceback(exc, zoom, width, suppress=suppress), sys.stderr)
        except Exception:
            sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook

    if threads:

        def thread_hook(args):
            # stdlib threading.excepthook silently ignores SystemExit — mirror it,
            # this is delivery glue, not a policy change.
            if args.exc_value is None or issubclass(args.exc_type, (KeyboardInterrupt, SystemExit)):
                return
            try:
                print_block(
                    render_traceback(args.exc_value, zoom, width, suppress=suppress), sys.stderr
                )
            except Exception:
                threading.__excepthook__(args)

        threading.excepthook = thread_hook
    else:
        threading.excepthook = threading.__excepthook__
