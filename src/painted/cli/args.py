"""Argument parsing for painted CLI tools.

Standard zoom/mode/format argument registration and parsing.
"""

from __future__ import annotations

import argparse

from ..core.fidelity import Fidelity
from .types import Format, OutputMode, Zoom


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
        help="Max display width for string values",
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


def parse_fidelity(args: argparse.Namespace) -> Fidelity | None:
    """Parse density limits from args.

    Returns Fidelity when at least one density flag is set, else None.
    """
    max_chars = getattr(args, "max_chars", None)
    max_lines = getattr(args, "max_lines", None)
    if max_chars is None and max_lines is None:
        return None
    return Fidelity(chars=max_chars, lines=max_lines)
