#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""PaintedHandler — log levels as declared severities.

A logging.Handler that renders records instead of formatting strings: the
levelno resolves through a declared threshold table onto the closed Severity
vocabulary (DEBUG stays muted — the journalctl principle), `extra=` fields are
payload rows, and `exc_info` mounts a render_traceback record tree under the
log line. Structure comes from the record, never from markup in the message.

Run: uv run demos/primitives/logging_handler.py
"""

import logging
import sys

from painted import Block, PaintedHandler, Style, Zoom, join_vertical, print_block

# One fixed timestamp for every record — the output is about severity and
# structure, not about when the demo ran.
_CREATED = 1751600000.0


def _record(
    level: int,
    msg: str,
    *,
    name: str = "app.worker",
    exc_info: tuple | None = None,
    extra: dict | None = None,
) -> logging.LogRecord:
    record = logging.LogRecord(name, level, __file__, 0, msg, (), exc_info)
    record.created = _CREATED
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def _failure() -> tuple:
    """A caught failure, as the exc_info triple logging.error(..., exc_info=True) carries."""
    try:
        config = {"port": "eight"}
        int(config["port"])
    except ValueError as exc:
        return (type(exc), exc, exc.__traceback__)


def _label(text: str) -> Block:
    return join_vertical(Block.text("", Style()), Block.text(f"  {text}", Style(dim=True)), Block.text("", Style()))


def demo() -> None:
    print_block(_label("the level quartet — DEBUG muted, WARNING/ERROR in role color"))
    handler = PaintedHandler(sys.stdout, zoom=Zoom.SUMMARY)
    handler.emit(_record(logging.DEBUG, "cache warm (12 entries)"))
    handler.emit(_record(logging.INFO, "job 8241 started"))
    handler.emit(_record(logging.WARNING, "quota at 91% — throttling soon"))
    handler.emit(_record(logging.ERROR, "job 8241 failed"))

    print_block(_label("extra= at DETAILED — structure from the record, not the message"))
    detailed = PaintedHandler(sys.stdout, zoom=Zoom.DETAILED)
    detailed.emit(
        _record(
            logging.INFO,
            "request served",
            extra={"user": "kyle", "request_id": "req-7c2f", "elapsed_ms": 42},
        )
    )

    print_block(_label("exc_info — a record tree mounted under the log line"))
    detailed.emit(_record(logging.ERROR, "job 8241 failed", exc_info=_failure()))


if __name__ == "__main__":
    demo()
