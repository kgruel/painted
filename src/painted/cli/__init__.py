"""CLI framework layer for painted.

Argument parsing, context detection, mode dispatch, help rendering,
and lifecycle management for CLI tools built on painted's renderer.

    from painted.cli import run_cli, CliContext, Zoom
"""

from .args import add_cli_args, parse_format, parse_mode, parse_zoom
from .context import detect_context, resolve_mode
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
from .types import CliContext, Format, OutputMode, Zoom
from .app_runner import AppCommand, AppRunner, run_app

__all__ = [
    # Types
    "Zoom",
    "OutputMode",
    "Format",
    "CliContext",
    # Context
    "resolve_mode",
    "detect_context",
    # Args
    "add_cli_args",
    "parse_zoom",
    "parse_mode",
    "parse_format",
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
