"""Help rendering for painted CLI tools.

Data types for structured help, zoom-aware rendering, and
argument introspection utilities.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import Format, Zoom

if TYPE_CHECKING:
    from .runner import CliRunner


# =============================================================================
# Help Data Types
# =============================================================================


@dataclass(frozen=True)
class HelpFlag:
    """A single CLI flag for help rendering."""

    short: str | None  # "-v"
    long: str | None  # "--verbose"
    description: str  # shown at all zoom levels
    detail: str | None = None  # shown at DETAILED+


@dataclass(frozen=True)
class HelpGroup:
    """A group of related flags."""

    name: str  # "Zoom"
    hint: str | None = None  # "(what to show)" — after name at SUMMARY+
    detail: str | None = None  # longer description at DETAILED+
    flags: tuple[HelpFlag, ...] = ()
    min_zoom: Zoom = Zoom.MINIMAL  # zoom level where this group first appears (compact)


@dataclass(frozen=True)
class HelpData:
    """Complete help information for a CLI tool."""

    prog: str | None
    description: str | None
    groups: tuple[HelpGroup, ...]


@dataclass(frozen=True)
class HelpArg:
    """Describes a command argument for help rendering.

    For commands that pre-parse their own args before calling run_cli,
    use this to describe those args so they appear in --help output.
    """

    name: str  # "--since" or "vertex"
    description: str = ""
    default: str | None = None
    positional: bool = False


# =============================================================================
# Help Utilities
# =============================================================================


def help_args_to_flags(help_args: list[HelpArg]) -> tuple[HelpFlag, ...]:
    """Convert HelpArgs to HelpFlags for rendering."""
    flags: list[HelpFlag] = []
    for arg in help_args:
        desc = arg.description
        if arg.default is not None:
            suffix = f"(default: {arg.default})"
            desc = f"{desc} {suffix}" if desc else suffix
        flags.append(HelpFlag(short=None, long=arg.name, description=desc))
    return tuple(flags)


def _extract_add_args_flags(
    add_args_fn: Callable[[argparse.ArgumentParser], None],
) -> tuple[HelpFlag, ...]:
    """Extract help flags from an add_args callback by introspecting a temp parser."""
    parser = argparse.ArgumentParser(add_help=False)
    add_args_fn(parser)
    flags: list[HelpFlag] = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if action.help is argparse.SUPPRESS:
            continue
        if not action.option_strings:  # positional
            desc = action.help or ""
            flags.append(HelpFlag(short=None, long=action.dest, description=desc))
        else:
            short = None
            long = None
            for s in action.option_strings:
                if s.startswith("--"):
                    long = s
                elif s.startswith("-"):
                    short = s
            desc = action.help or ""
            flags.append(HelpFlag(short=short, long=long, description=desc))
    return tuple(flags)


def scan_help_args(args: list[str]) -> tuple[Zoom, Format]:
    """Quick-scan args for zoom and format when --help is present."""
    zoom = Zoom.SUMMARY
    fmt = Format.AUTO

    v_count = 0
    for arg in args:
        if arg == "-h" or arg == "--help":
            continue
        if arg == "-q" or arg == "--quiet":
            zoom = Zoom.MINIMAL
        elif arg.startswith("-v"):
            # Count v's: -v, -vv, -vvv
            if arg.startswith("--verbose"):
                v_count += 1
            else:
                v_count += len(arg) - 1  # strip the dash
        elif arg == "--json":
            fmt = Format.JSON
        elif arg == "--plain":
            fmt = Format.PLAIN

    if zoom != Zoom.MINIMAL and v_count > 0:
        zoom = Zoom.FULL if v_count >= 2 else Zoom.DETAILED

    return zoom, fmt


# =============================================================================
# Help Data Construction
# =============================================================================


def build_help_data(runner: CliRunner) -> HelpData:
    """Construct help data from a CliRunner's config."""
    from .types import OutputMode

    # Command args (primary) — from help_args and/or add_args
    command_flags: list[HelpFlag] = []
    if runner.help_args is not None:
        command_flags.extend(help_args_to_flags(runner.help_args))
    if runner.add_args is not None:
        command_flags.extend(_extract_add_args_flags(runner.add_args))

    has_command_args = len(command_flags) > 0
    framework_zoom = Zoom.SUMMARY if has_command_args else Zoom.MINIMAL

    # Zoom group — always present
    zoom_flags = (
        HelpFlag("-q", "--quiet", "Minimal output", detail="Also implies --static (no animation)."),
        HelpFlag("-v", "--verbose", "Detailed (-v) or full (-vv)"),
    )
    zoom_group = HelpGroup(
        name="Zoom",
        hint="(what to show)",
        detail="Controls how much detail is rendered. Stackable: -v for detailed, -vv for full.",
        flags=zoom_flags,
        min_zoom=framework_zoom,
    )

    # Mode group — filtered by capability (same logic as add_cli_args)
    has_live = runner.fetch_stream is not None
    has_interactive = runner.handlers is not None and OutputMode.INTERACTIVE in runner.handlers
    mode_flags: list[HelpFlag] = []
    if has_interactive:
        mode_flags.append(HelpFlag("-i", "--interactive", "Interactive TUI"))
    mode_flags.append(
        HelpFlag(None, "--static", "Static output, no animation"),
    )
    if has_live:
        mode_flags.append(
            HelpFlag(None, "--live", "Live output with in-place updates"),
        )

    mode_group: HelpGroup | None = None
    if has_live or has_interactive:
        mode_group = HelpGroup(
            name="Mode",
            hint="(how to deliver)",
            detail="Delivery mechanism. AUTO selects LIVE for TTY, STATIC for pipes.",
            flags=tuple(mode_flags),
            min_zoom=framework_zoom,
        )

    # Format group — always present
    format_flags = (
        HelpFlag(None, "--json", "JSON output", detail="Implies --static."),
        HelpFlag(
            None, "--plain", "Plain text, no ANSI codes", detail="Implies --static when piped."
        ),
    )
    format_group = HelpGroup(
        name="Format",
        hint="(serialization)",
        detail="Output serialization. ANSI is default for TTY, PLAIN for pipes.",
        flags=format_flags,
        min_zoom=framework_zoom,
    )

    # Help flag itself
    help_flags = (HelpFlag("-h", "--help", "Show this help", detail="Add -v for more detail."),)
    help_group = HelpGroup(name="Help", flags=help_flags, min_zoom=framework_zoom)

    groups: list[HelpGroup] = []
    if command_flags:
        groups.append(HelpGroup(name="", flags=tuple(command_flags)))
    groups.append(zoom_group)
    if mode_group is not None:
        groups.append(mode_group)
    groups.append(format_group)
    groups.append(help_group)

    return HelpData(
        prog=runner.prog,
        description=runner.description,
        groups=tuple(groups),
    )


# =============================================================================
# Help Rendering
# =============================================================================


def render_help(data: HelpData, zoom: Zoom, width: int, use_ansi: bool):
    """Render help data as a composed Block.

    Each group has a min_zoom that controls when it appears and how much
    detail it shows. The effective zoom for a group is:

        eff = global_zoom - group.min_zoom

    Three rendering states:
      eff < 0  → hidden
      eff == 0 → compact (flag names only, single dim line)
      eff == 1 → expanded (flag columns with descriptions)
      eff >= 2 → expanded + group.detail + flag.detail
    """
    from ..core.block import Block
    from ..core.cell import Style
    from ..core.compose import join_vertical

    rows: list[Block] = []
    dim = Style(dim=True) if use_ansi else Style()
    bold = Style(bold=True) if use_ansi else Style()
    normal = Style()

    # Header: prog + description
    if data.prog or data.description:
        parts: list[str] = []
        if data.prog:
            parts.append(data.prog)
        desc = data.description
        if desc:
            first_line = desc.strip().split("\n")[0].strip()
            parts.append(first_line)
        header = " — ".join(parts) if len(parts) > 1 else parts[0]
        rows.append(Block.text(header, bold))
        rows.append(Block.text("", normal))

    # Flag column width: find widest flag string across visible groups
    flag_strs: list[str] = []
    for group in data.groups:
        for flag in group.flags:
            parts_f: list[str] = []
            if flag.short:
                parts_f.append(flag.short)
            if flag.long:
                parts_f.append(flag.long)
            flag_strs.append(", ".join(parts_f))
    col_width = max((len(s) for s in flag_strs), default=10) + 2  # padding

    def _render_expanded(
        group: HelpGroup, style: Style, header_style: Style, show_detail: bool
    ) -> None:
        """Render a group in expanded form (eff >= 1)."""
        if group.name:
            group_label = group.name
            if group.hint:
                group_label += f" {group.hint}"
            rows.append(Block.text(group_label, header_style))

        if show_detail and group.detail:
            rows.append(Block.text(f"  {group.detail}", dim))

        for flag in group.flags:
            parts_f: list[str] = []
            if flag.short:
                parts_f.append(flag.short)
            if flag.long:
                parts_f.append(flag.long)
            flag_str = ", ".join(parts_f)
            line = f"  {flag_str:<{col_width}}{flag.description}"
            rows.append(Block.text(line, style))

            if show_detail and flag.detail:
                detail_indent = "  " + " " * col_width
                rows.append(Block.text(f"{detail_indent}{flag.detail}", dim))

        rows.append(Block.text("", normal))

    # Collect consecutive compact groups, flush them as a single dim line
    compact_groups: list[HelpGroup] = []

    def _flush_compact() -> None:
        if not compact_groups:
            return
        flag_names: list[str] = []
        for g in compact_groups:
            for flag in g.flags:
                flag_names.append(flag.short or flag.long or "")
        rows.append(Block.text("  " + "  ".join(flag_names), dim))
        rows.append(Block.text("", normal))
        compact_groups.clear()

    for group in data.groups:
        eff = zoom.value - group.min_zoom.value
        if eff < 0:
            continue  # hidden

        if eff == 0:
            compact_groups.append(group)
        else:
            _flush_compact()
            # Dim styling when group is just one step above compact
            if eff == 1:
                dim_bold = Style(bold=True, dim=True) if use_ansi else normal
                _render_expanded(group, dim, dim_bold, show_detail=False)
            else:
                _render_expanded(group, normal, bold, show_detail=True)

    _flush_compact()

    return join_vertical(*rows)
