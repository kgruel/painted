"""CLI framework vocabulary: types, context detection, and argument parsing.

This module consolidates the small vocabulary for CLI tools built on painted:

  - Enums: OutputMode, Format
  - Types: CliContext (with backward-compat ctx.zoom property)
  - Context: detect_context(), resolve_mode()
  - Args: add_cli_args(), parse_zoom(), parse_mode(), parse_format(), parse_fidelity()

Zoom and Fidelity live in core/ as shared rendering vocabulary.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum

from ..core.fidelity import Depth, Fidelity
from ..core.zoom import Zoom

__all__ = [
    "Depth",
    "Fidelity",
    "Zoom",
    "OutputMode",
    "Format",
    "CliContext",
    "resolve_mode",
    "detect_context",
    "add_cli_args",
    "parse_zoom",
    "parse_mode",
    "parse_format",
    "parse_fidelity",
]


# =============================================================================
# Enums
# =============================================================================


class OutputMode(Enum):
    """Delivery mechanism."""

    AUTO = "auto"  # Detect from TTY/pipe
    STATIC = "static"  # print_block, scrolls away
    LIVE = "live"  # InPlaceRenderer, cursor control
    INTERACTIVE = "interactive"  # Surface, alt screen


class Format(Enum):
    """Serialization format."""

    AUTO = "auto"  # Detect from TTY
    ANSI = "ansi"  # Styled terminal output
    PLAIN = "plain"  # No escape codes
    JSON = "json"  # Machine-readable


# =============================================================================
# CliContext
# =============================================================================


@dataclass(frozen=True)
class CliContext:
    """Resolved runtime context.

    ``fidelity`` is the canonical field. ``ctx.zoom`` is a backward-compat
    property returning ``Zoom(fidelity.depth)`` so existing callers continue
    to work unchanged.
    """

    fidelity: Fidelity
    mode: OutputMode  # Resolved (never AUTO)
    use_ansi: bool  # Writer fidelity — True for styled, False for plain
    is_tty: bool
    width: int
    height: int

    @property
    def zoom(self) -> Zoom:
        """Backward-compat: fidelity.depth as Zoom."""
        return Zoom(min(self.fidelity.depth, 3))


# =============================================================================
# Context detection
# =============================================================================

_ENV_SIZE_CACHE: tuple[str | None, str | None, tuple[int, int] | None] = (None, None, None)


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
    fidelity: Fidelity,
    mode: OutputMode,
    *,
    force_plain: bool = False,
    default_mode: OutputMode = OutputMode.LIVE,
) -> CliContext:
    """Detect and resolve full runtime context.

    JSON is not a context concern — callers handle it before reaching here.
    ``force_plain`` suppresses ANSI when the user passes ``--plain``.
    """
    stdout = sys.stdout
    is_tty = hasattr(stdout, "isatty") and stdout.isatty()

    if mode == OutputMode.AUTO:
        resolved_mode = default_mode if is_tty else OutputMode.STATIC
    else:
        resolved_mode = mode
    use_ansi = not force_plain and (is_tty or resolved_mode == OutputMode.INTERACTIVE)

    size = _env_terminal_size()
    if size is None:
        ts = shutil.get_terminal_size()
        width, height = ts.columns, ts.lines
    else:
        width, height = size

    return CliContext(
        fidelity=fidelity,
        mode=resolved_mode,
        use_ansi=use_ansi,
        is_tty=is_tty,
        width=width,
        height=height,
    )


# =============================================================================
# Argument parsing
# =============================================================================


def add_cli_args(
    parser: argparse.ArgumentParser,
    *,
    modes: set[OutputMode] | None = None,
) -> None:
    """Add standard zoom/mode/format arguments.

    Args:
        parser: ArgumentParser to add arguments to.
        modes: Supported output modes. When provided, only adds flags for
            modes in the set. When None, adds all flags (backward-compatible).
    """
    # Zoom group
    zoom_group = parser.add_mutually_exclusive_group()
    zoom_group.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Minimal output (zoom=0)",
    )
    zoom_group.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase detail level (-v=detailed, -vv=full)",
    )

    # Mode group — only add flags for supported modes
    has_live = modes is None or OutputMode.LIVE in modes
    has_interactive = modes is None or OutputMode.INTERACTIVE in modes
    if has_live or has_interactive:
        mode_group = parser.add_mutually_exclusive_group()
        if has_interactive:
            mode_group.add_argument(
                "-i",
                "--interactive",
                action="store_true",
                help="Interactive TUI mode",
            )
        # --static is the "force no animation" escape hatch
        mode_group.add_argument(
            "--static",
            action="store_true",
            help="Static output, no animation",
        )
        if has_live:
            mode_group.add_argument(
                "--live",
                action="store_true",
                help="Live output with in-place updates",
            )

    # Format
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON output (implies --static)",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Plain text, no ANSI codes",
    )

    # Density
    parser.add_argument(
        "--max-chars",
        type=int,
        default=None,
        metavar="N",
        help="Max display width for string values. Truncates mid-content — prefer --max-lines for surfaced contexts (e.g. SessionStart hooks) where truncation reads as completeness.",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=None,
        metavar="N",
        help="Max items to show for collections",
    )


def parse_zoom(args: argparse.Namespace, default: Zoom = Zoom.SUMMARY) -> Zoom:
    """Parse zoom level from args."""
    if getattr(args, "quiet", False):
        return Zoom.MINIMAL
    verbose = getattr(args, "verbose", 0)
    if verbose >= 2:
        return Zoom.FULL
    if verbose == 1:
        return Zoom.DETAILED
    return default


def parse_mode(args: argparse.Namespace) -> OutputMode:
    """Parse output mode from args."""
    if getattr(args, "interactive", False):
        return OutputMode.INTERACTIVE
    if getattr(args, "static", False):
        return OutputMode.STATIC
    if getattr(args, "live", False):
        return OutputMode.LIVE
    return OutputMode.AUTO


def parse_format(args: argparse.Namespace) -> Format:
    """Parse format from args."""
    if getattr(args, "json", False):
        return Format.JSON
    if getattr(args, "plain", False):
        return Format.PLAIN
    return Format.AUTO


def parse_fidelity(args: argparse.Namespace, zoom: Zoom = Zoom.SUMMARY) -> Fidelity:
    """Build a Fidelity from parsed args.

    depth comes from the zoom level (parsed separately).
    chars/lines come from --max-chars/--max-lines (0 means unlimited).
    """
    max_chars = getattr(args, "max_chars", None)
    max_lines = getattr(args, "max_lines", None)
    return Fidelity(
        depth=int(zoom),
        chars=max_chars if max_chars is not None else 0,
        lines=max_lines if max_lines is not None else 0,
    )
