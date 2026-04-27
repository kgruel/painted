"""CLI framework layer for painted.

Argument parsing, context detection, mode dispatch, help rendering,
and lifecycle management for CLI tools built on painted's renderer.

    from painted.cli import run_cli, CliContext, Zoom
"""

from .types import (
    Depth,
    Fidelity,
    Zoom,
    OutputMode,
    Format,
    CliContext,
    resolve_mode,
    detect_context,
    add_cli_args,
    parse_zoom,
    parse_mode,
    parse_format,
    parse_fidelity,
)
from .help import (
    HelpArg,
    HelpData,
    HelpFlag,
    HelpGroup,
    help_args_to_flags,
    render_help,
    scan_help_args,
)
from .runner import CliRunner, run_cli
from .app_runner import AppCommand, AppRunner, run_app

__all__ = [
    # Types
    "Depth",
    "Zoom",
    "OutputMode",
    "Format",
    "Fidelity",
    "CliContext",
    # Context
    "resolve_mode",
    "detect_context",
    # Args
    "add_cli_args",
    "parse_zoom",
    "parse_mode",
    "parse_format",
    "parse_fidelity",
    # Help
    "HelpArg",
    "HelpData",
    "HelpFlag",
    "HelpGroup",
    "help_args_to_flags",
    "render_help",
    "scan_help_args",
    # Runner
    "CliRunner",
    "run_cli",
    # App runner
    "AppCommand",
    "AppRunner",
    "run_app",
]
