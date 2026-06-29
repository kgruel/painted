"""CLI framework layer for painted.

Argument parsing, context detection, mode dispatch, help rendering,
and lifecycle management for CLI tools built on painted's renderer.

    from painted.cli import run_cli, CliContext, Zoom
"""

from .types import (
    Fidelity,
    Zoom,
    Tag,
    OutputMode,
    Format,
    CliContext,
    ArgsView,
    resolve_mode,
    detect_context,
    add_cli_args,
    build_parser,
    parse_zoom,
    parse_mode,
    parse_format,
    parse_fidelity,
    implied_visible,
)
from .help import (
    HelpArg,
    help_doc,
    scan_help_args,
)
from .runner import CliRunner, run_cli
from .app_runner import AppCommand, AppRunner, run_app

__all__ = [
    # Types
    "Zoom",
    "Tag",
    "OutputMode",
    "Format",
    "Fidelity",
    "CliContext",
    "ArgsView",
    # Context
    "resolve_mode",
    "detect_context",
    # Args
    "add_cli_args",
    "build_parser",
    "parse_zoom",
    "parse_mode",
    "parse_format",
    "parse_fidelity",
    "implied_visible",
    # Help
    "HelpArg",
    "help_doc",
    "scan_help_args",
    # Runner
    "CliRunner",
    "run_cli",
    # App runner
    "AppCommand",
    "AppRunner",
    "run_app",
]
