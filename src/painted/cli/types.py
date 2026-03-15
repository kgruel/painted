"""Types for the CLI framework layer.

OutputMode, Format, and CliContext — the vocabulary for CLI argument
parsing, context detection, and dispatch. Zoom lives in core/ as shared
rendering vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..core.zoom import Zoom


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


@dataclass(frozen=True)
class CliContext:
    """Resolved runtime context."""

    zoom: Zoom
    mode: OutputMode  # Resolved (never AUTO)
    use_ansi: bool  # Writer fidelity — True for styled, False for plain
    is_tty: bool
    width: int
    height: int
