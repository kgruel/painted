"""Context detection and resolution for CLI tools.

Resolves AUTO mode to concrete delivery, detects TTY/pipe,
and sets up ambient defaults (icon set).
"""

from __future__ import annotations

import os
import shutil
import sys

_ENV_SIZE_CACHE: tuple[str | None, str | None, tuple[int, int] | None] = (None, None, None)

from .types import CliContext, OutputMode, Zoom


def resolve_mode(
    requested: OutputMode,
    is_tty: bool,
    is_pipe: bool,
    default_mode: OutputMode = OutputMode.LIVE,
) -> OutputMode:
    """Resolve AUTO to concrete mode.

    When requested is AUTO, pipes always get STATIC. TTYs get default_mode
    (LIVE by default, but callers can override to STATIC for run-and-exit
    commands that support --live as opt-in).
    """
    if requested != OutputMode.AUTO:
        return requested
    if is_pipe:
        return OutputMode.STATIC
    if is_tty:
        return default_mode
    return OutputMode.STATIC


def _env_terminal_size() -> tuple[int, int] | None:
    """Return terminal size from COLUMNS/LINES when both are valid positive ints."""
    global _ENV_SIZE_CACHE

    cols = os.environ.get("COLUMNS")
    lines = os.environ.get("LINES")
    cached_cols, cached_lines, cached_size = _ENV_SIZE_CACHE
    if cols == cached_cols and lines == cached_lines:
        return cached_size

    size: tuple[int, int] | None
    if cols is None or lines is None:
        size = None
    else:
        try:
            width = int(cols)
            height = int(lines)
        except ValueError:
            size = None
        else:
            size = (width, height) if width > 0 and height > 0 else None

    _ENV_SIZE_CACHE = (cols, lines, size)
    return size


def detect_context(
    zoom: Zoom,
    mode: OutputMode,
    *,
    force_plain: bool = False,
    default_mode: OutputMode = OutputMode.LIVE,
) -> CliContext:
    """Detect and resolve full runtime context.

    JSON is not a context concern — callers handle it before reaching here.
    ``force_plain`` suppresses ANSI when the user passes ``--plain``.
    """
    is_tty = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    is_pipe = not is_tty

    resolved_mode = resolve_mode(mode, is_tty, is_pipe, default_mode)
    use_ansi = not force_plain and (is_tty or resolved_mode == OutputMode.INTERACTIVE)

    size = _env_terminal_size()
    if size is None:
        ts = shutil.get_terminal_size()
        width, height = ts.columns, ts.lines
    else:
        width, height = size

    return CliContext(
        zoom=zoom,
        mode=resolved_mode,
        use_ansi=use_ansi,
        is_tty=is_tty,
        width=width,
        height=height,
    )
