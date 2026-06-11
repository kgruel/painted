"""CLI framework vocabulary: types, context detection, and argument parsing.

This module consolidates the small vocabulary for CLI tools built on painted:

  - Enums: OutputMode, Format
  - Types: CliContext (with the rung-1 ctx.zoom porthole), Tag
  - Context: detect_context(), resolve_mode()
  - Args: add_cli_args(), parse_zoom(), parse_mode(), parse_format(), parse_fidelity()

Zoom and Fidelity live in core/ as shared rendering vocabulary. The disclosure
grammar (Tag declarations, depth aliases, budget gating) lives here beside the
parsing it configures — spec in core, grammar in cli. See
docs/FIDELITY_DESIGN.md.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from ..core.fidelity import Fidelity
from ..core.zoom import Zoom

__all__ = [
    "Fidelity",
    "Zoom",
    "Tag",
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
    "implied_visible",
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

    ``fidelity`` is the compiled disclosure spec — the canonical field.
    ``ctx.zoom`` is the rung-1 view of it, blessed permanently.
    """

    fidelity: Fidelity
    mode: OutputMode  # Resolved (never AUTO)
    use_ansi: bool  # Writer fidelity — True for styled, False for plain
    is_tty: bool
    width: int
    height: int

    @property
    def zoom(self) -> Zoom:
        """The rung-1 view of the spec: fidelity.depth as Zoom.

        Not a compat shim — the honest name for the first axis; day-one code
        that reads it stays load-bearing forever. depth is an open int in the
        spec; the porthole is bounded by the enum, hence the two-sided clamp
        (a build_fidelity hook can hand back any int).
        """
        return Zoom(min(max(self.fidelity.depth, 0), 3))


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
# Disclosure grammar: Tag declarations and depth aliases
# =============================================================================


@dataclass(frozen=True)
class Tag:
    """A named, toggleable layer of a view — the rung-2 disclosure declaration.

    Declaring a tag buys the ``--{name}`` flag, its help entry, and its
    compilation into ``Fidelity.visible`` in one move. ``implied_at`` turns
    the tag on implicitly at that depth and above (``-vv`` ⇒ depth 3), so the
    bundle convenience survives without smuggling the facet into depth.

    Depth is anonymous detail; tags are named facets. Declare a tag when a
    user would want the layer by name at low depth (``--thinking`` at brief);
    keep "only ever more of the same" on the depth axis.
    """

    name: str  # the noun; generates --{name}
    help: str  # one-line help text
    implied_at: int | None = None  # depth at which the tag turns on implicitly


# Long-form names of every flag the framework itself may register. Declared
# names are checked against the full set regardless of modes=/budgets=
# filtering, so a declaration that works in one configuration cannot break in
# another.
_FRAMEWORK_FLAG_NAMES = frozenset(
    {
        "help",
        "quiet",
        "verbose",
        "interactive",
        "static",
        "live",
        "json",
        "plain",
        "max-chars",
        "max-lines",
    }
)

_DECLARED_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _dest(name: str) -> str:
    """argparse dest for a declared flag name (kebab → snake)."""
    return name.replace("-", "_")


def check_declarations(
    tags: Sequence[Tag] | None,
    depth_aliases: Mapping[str, int] | None,
) -> None:
    """Validate declarations at parser construction.

    Declarations are promises: a malformed name, a colliding name, or an
    out-of-domain alias depth raises here, not at runtime. Collisions are
    checked tag↔framework, alias↔framework, tag↔tag, and tag↔alias.
    """
    seen: set[str] = set()
    declared = [t.name for t in tags or ()] + list(depth_aliases or ())
    for name in declared:
        if not _DECLARED_NAME_RE.match(name):
            raise ValueError(
                f"Declared flag name {name!r} must be lowercase kebab-case "
                "(it becomes both the --flag and the visible-set key)"
            )
        if name in _FRAMEWORK_FLAG_NAMES:
            raise ValueError(f"Declared flag name {name!r} collides with a framework flag")
        if name in seen:
            raise ValueError(f"Declared flag name {name!r} collides with another declaration")
        seen.add(name)
    for alias_name, alias_depth in (depth_aliases or {}).items():
        if alias_depth < 0:
            raise ValueError(
                f"Depth alias {alias_name!r} maps to {alias_depth}: depth is a "
                "non-negative int (0=minimal; open above 3)"
            )


def implied_visible(tags: Sequence[Tag] | None, depth: int) -> frozenset[str]:
    """The tags a depth turns on implicitly — the implication half of
    compilation, shared so non-CLI harnesses (capture, tests) can resolve a
    depth into the same visible set the compiler would."""
    return frozenset(
        t.name for t in tags or () if t.implied_at is not None and depth >= t.implied_at
    )


def declared_dests(
    tags: Sequence[Tag] | None,
    depth_aliases: Mapping[str, int] | None,
) -> frozenset[str]:
    """The argparse dests the declarations own — what compilation reads back
    off the namespace. Exposed so the runner can keep add_args from landing
    a custom arg on a declared dest."""
    return frozenset(_dest(t.name) for t in tags or ()) | frozenset(
        _dest(a) for a in depth_aliases or ()
    )


def depth_alias_help(depth: int) -> str:
    """Generated help text for a depth alias flag — pure spelling, so the
    help says only what depth it sets."""
    try:
        label = f"{depth} ({Zoom(depth).name.lower()})"
    except ValueError:
        label = str(depth)
    return f"Set detail depth to {label}"


# =============================================================================
# Argument parsing
# =============================================================================


def add_cli_args(
    parser: argparse.ArgumentParser,
    *,
    modes: set[OutputMode] | None = None,
    tags: Sequence[Tag] | None = None,
    depth_aliases: Mapping[str, int] | None = None,
    budgets: bool = False,
) -> None:
    """Add standard zoom/mode/format arguments.

    Args:
        parser: ArgumentParser to add arguments to.
        modes: Supported output modes. When provided, only adds flags for
            modes in the set. When None, adds all mode flags.
        tags: Declared disclosure layers. Each generates a ``--{name}`` flag
            grouped under "Layers".
        depth_aliases: App-local depth spellings (``{"brief": 0, "full": 3}``
            generates ``--brief``/``--full``). Pure spelling: an alias sets
            depth, mutually exclusive with ``-q``/``-v``.
        budgets: Whether the app honors density budgets. Only when True do
            ``--max-chars``/``--max-lines`` exist — a flag exists only because
            a capability was declared, and a declared capability must change
            output (the honesty rule).
    """
    check_declarations(tags, depth_aliases)

    # Zoom group — depth aliases join -q/-v, mutually exclusive spellings of
    # the same axis
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
    for alias_name, alias_depth in (depth_aliases or {}).items():
        zoom_group.add_argument(
            f"--{alias_name}",
            action="store_true",
            help=depth_alias_help(alias_depth),
        )

    # Layers — declared tags. (argparse's own --help lists this group after
    # the default options group; painted's rendered help places Layers right
    # after Zoom. run_cli intercepts -h, so the rendered doc is the surface
    # users see — the argparse ordering matters only to bare-argparse hosts.)
    if tags:
        layers = parser.add_argument_group("Layers")
        for tag in tags:
            layers.add_argument(
                f"--{tag.name}",
                action="store_true",
                help=tag.help,
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

    # Density — only when the app declared it honors budgets
    if budgets:
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


def parse_fidelity(
    args: argparse.Namespace,
    zoom: Zoom = Zoom.SUMMARY,
    *,
    tags: Sequence[Tag] | None = None,
    depth_aliases: Mapping[str, int] | None = None,
) -> Fidelity:
    """Compile parsed args into a Fidelity.

    depth comes from the zoom level (parsed separately), overridden by a
    passed depth alias — the alias is just another spelling of the same axis,
    so argparse's exclusive group guarantees at most one source.

    visible = tags whose flag was passed ∪ tags implied by the resolved depth
    (``implied_at is not None and depth >= implied_at``). Implications resolve
    here, at compile time — the spec stays dumb, consumers just call
    ``shows()``.

    chars/lines come from --max-chars/--max-lines (0 means unlimited).
    """
    depth = int(zoom)
    for alias_name, alias_depth in (depth_aliases or {}).items():
        if getattr(args, _dest(alias_name), False):
            depth = alias_depth

    visible: set[str] = set(implied_visible(tags, depth))
    for tag in tags or ():
        if getattr(args, _dest(tag.name), False):
            visible.add(tag.name)

    max_chars = getattr(args, "max_chars", None)
    max_lines = getattr(args, "max_lines", None)
    return Fidelity(
        depth=depth,
        visible=frozenset(visible),
        chars=max_chars if max_chars is not None else 0,
        lines=max_lines if max_lines is not None else 0,
    )
