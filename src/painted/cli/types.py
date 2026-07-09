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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ..core.errors import DeclarationError
from ..core.fidelity import Fidelity
from ..core.zoom import Zoom

if TYPE_CHECKING:
    from .prompts import Prompt

__all__ = [
    "Fidelity",
    "Zoom",
    "Tag",
    "OutputMode",
    "Format",
    "CliContext",
    "ArgsView",
    "resolve_mode",
    "detect_context",
    "add_cli_args",
    "build_parser",
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
# ArgsView — the shared parsed-args substrate
# =============================================================================


class ArgsView:
    """Read-only attribute view over the consumer's parsed CLI args.

    The shared trunk of the three parser reflections: PARSE exposes it as
    ``ctx.args`` (``ctx.args.frame``), and COMPLETE reuses the same view so a
    domain completer can scope candidates to what's already been typed without
    re-parsing the line. Attribute access over a frozen snapshot — assignment
    raises (honoring the frozen-state invariant), and an unknown name raises
    ``AttributeError`` rather than fabricating a value (the honesty rule).
    """

    __slots__ = ("_data",)

    _data: Mapping[str, object]

    def __init__(self, data: Mapping[str, object] | None = None) -> None:
        object.__setattr__(self, "_data", MappingProxyType(dict(data or {})))

    def __getattr__(self, name: str) -> object:
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name) from None

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("ArgsView is read-only")

    def __getitem__(self, name: str) -> object:
        return self._data[name]

    def __contains__(self, name: object) -> bool:
        return name in self._data

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def get(self, name: str, default: object = None) -> object:
        return self._data.get(name, default)

    def __repr__(self) -> str:
        return f"ArgsView({dict(self._data)!r})"


# =============================================================================
# CliContext
# =============================================================================


def _empty_session() -> Any:
    """A non-interactive, prompt-free PromptSession — the ``CliContext`` default.

    Imported lazily so ``cli.types`` stays render-free at module load (the
    completion path imports this module and must not pay for the mark channel
    ``prompts`` pulls). ``detect_context`` overrides this with a session carrying
    the real stream state and declared prompts; a directly-constructed
    ``CliContext`` gets this empty, stdin-not-a-TTY session, so ``ctx.ask`` there
    resolves by flag/default or refuses — it never tries to prompt.
    """
    from .prompts import PromptSession

    return PromptSession()


@dataclass(frozen=True)
class CliContext:
    """Resolved runtime context.

    ``fidelity`` is the compiled disclosure spec — the canonical field.
    ``ctx.zoom`` is the rung-1 view of it, blessed permanently.
    ``args`` is the read-only view of the consumer's parsed args (the same
    trunk completion walks); empty when no ``add_args`` were declared.

    ``is_tty``/``use_ansi`` are stdout-derived (they govern how the program's
    *output* renders). ``stdin_is_tty`` is the prompt gate — "is a human
    driving?" is a question about stdin (design §3) — and ``stderr_is_tty``
    governs a prompt's own render fidelity, since prompt UI draws on stderr
    (design §8). Both are added for the inline-prompt subsystem and leave the
    stdout-derived rendering path untouched.
    """

    fidelity: Fidelity
    mode: OutputMode  # Resolved (never AUTO)
    use_ansi: bool  # Writer fidelity — True for styled, False for plain
    is_tty: bool
    width: int
    height: int
    args: ArgsView = field(default_factory=ArgsView)
    stdin_is_tty: bool = False
    stderr_is_tty: bool = False
    # The memoized prompt resolver behind ctx.ask. A plain object (not a
    # dataclass), referenced by one field, so the frozen-collection invariant
    # sees an opaque holder, not a mutable dict. Excluded from eq/repr — it is
    # runtime resolution state, not part of the context's identity.
    _session: Any = field(default_factory=_empty_session, repr=False, compare=False)

    def ask(self, prompt: object) -> Any:
        """Resolve a declared prompt — the single door (design §6, Q3).

        ``prompt`` is a declared prompt *name* (str) or a runtime declaration
        object. Resolution is memoized by name (a prompt fires at most once) and
        follows the ladder argv flag → interactive at a TTY → declared default →
        ``ContractError``. An undeclared name raises ``DeclarationError``.
        """
        return self._session.ask(prompt)

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
    args: ArgsView | None = None,
    prompts: Sequence[Prompt[Any]] | None = None,
    parked: Mapping[str, object] | None = None,
    no_input: bool = False,
) -> CliContext:
    """Detect and resolve full runtime context.

    JSON is not a context concern — callers handle it before reaching here.
    ``force_plain`` suppresses ANSI when the user passes ``--plain``.
    ``args`` carries the consumer's parsed args onto ``ctx.args``.

    ``prompts``/``parked``/``no_input`` seed the prompt session behind
    ``ctx.ask`` (design §6, §8): stdin's TTY-ness is the gate (never stdout's),
    stderr's is the prompt render fidelity, and ``no_input`` makes every prompt
    behave as if stdin were not a TTY. Omitted, the context still carries an
    empty session — a runtime ``ctx.ask(Select(...))`` always sees the stream
    policy.
    """
    stdout = sys.stdout
    stdin = sys.stdin
    stderr = sys.stderr
    is_tty = hasattr(stdout, "isatty") and stdout.isatty()
    stdin_is_tty = hasattr(stdin, "isatty") and stdin.isatty()
    stderr_is_tty = hasattr(stderr, "isatty") and stderr.isatty()

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

    from .prompts import PromptSession

    session = PromptSession(
        tuple(prompts or ()),
        parked or {},
        stdin_tty=stdin_is_tty,
        stderr_tty=stderr_is_tty,
        no_input=no_input,
        force_plain=force_plain,
        stdin=stdin,
    )

    return CliContext(
        fidelity=fidelity,
        mode=resolved_mode,
        use_ansi=use_ansi,
        is_tty=is_tty,
        width=width,
        height=height,
        args=args if args is not None else ArgsView(),
        stdin_is_tty=stdin_is_tty,
        stderr_is_tty=stderr_is_tty,
        _session=session,
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
        "no-input",
        "max-chars",
        "max-lines",
    }
)

# Every flag *spelling* the framework itself may register — long forms plus the
# short flags argparse would otherwise let a declared prompt shadow. The prompt
# collision check (a fourth-reflection declaration, docs/PROMPTS_DESIGN.md §6)
# compares generated ``--flag`` spellings against this set so ``Confirm("input")``
# → ``--no-input`` is a DeclarationError at construction, not an argparse
# conflict at runtime. Tag/alias collisions stay name-based (they generate a
# single ``--{name}``); prompts generate spelling *pairs*, so they check
# spellings.
_RESERVED_FLAG_SPELLINGS = frozenset(
    {
        "-h",
        "--help",
        "-q",
        "--quiet",
        "-v",
        "--verbose",
        "-i",
        "--interactive",
        "--static",
        "--live",
        "--json",
        "--plain",
        "--no-input",
        "--max-chars",
        "--max-lines",
    }
)

_DECLARED_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _dest(name: str) -> str:
    """argparse dest for a declared flag name (kebab → snake)."""
    return name.replace("-", "_")


# check_declarations / declared_dests / depth_alias_help below are package
# internals shared with the sibling runner/help/app_runner modules. They are
# public-named (the arch gate forbids cross-module private imports) but
# deliberately not in __all__ — not part of the consumer surface.


def check_declarations(
    tags: Sequence[Tag] | None,
    depth_aliases: Mapping[str, int] | None,
    prompts: Sequence[Prompt[Any]] | None = None,
) -> None:
    """Validate declarations at parser construction.

    Declarations are promises: a malformed name, a colliding name, or an
    out-of-domain alias depth raises here, not at runtime. Collisions are
    checked tag↔framework, alias↔framework, tag↔tag, and tag↔alias.

    ``prompts`` (the fourth reflection, docs/PROMPTS_DESIGN.md §6) generate flag
    *spellings*, not a single ``--{name}``, so they are checked against the
    reserved-spelling registry and against every tag/alias/prompt spelling
    claimed so far — ``Confirm("input")`` → ``--no-input`` collides with the
    framework flag here, not as an argparse conflict at dispatch. Prompt name
    discipline itself is enforced at ``Prompt`` construction; this is purely the
    cross-declaration collision half.
    """
    seen: set[str] = set()
    declared = [t.name for t in tags or ()] + list(depth_aliases or ())
    for name in declared:
        if not _DECLARED_NAME_RE.match(name):
            raise DeclarationError(
                f"Declared flag name {name!r} must be lowercase kebab-case "
                "(it becomes both the --flag and the visible-set key)"
            )
        if name in _FRAMEWORK_FLAG_NAMES:
            raise DeclarationError(f"Declared flag name {name!r} collides with a framework flag")
        if name in seen:
            raise DeclarationError(f"Declared flag name {name!r} collides with another declaration")
        seen.add(name)
    for alias_name, alias_depth in (depth_aliases or {}).items():
        if alias_depth < 0:
            raise DeclarationError(
                f"Depth alias {alias_name!r} maps to {alias_depth}: depth is a "
                "non-negative int (0=minimal; open above 3)"
            )

    if prompts:
        claimed: set[str] = set(_RESERVED_FLAG_SPELLINGS)
        claimed.update(f"--{t.name}" for t in tags or ())
        claimed.update(f"--{a}" for a in depth_aliases or {})
        for prompt in prompts:
            for spelling in prompt.flag_spellings():
                if spelling in claimed:
                    raise DeclarationError(
                        f"Prompt {prompt.name!r} generates {spelling!r}, which "
                        "collides with a framework flag or another declaration"
                    )
                claimed.add(spelling)


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
    prompts: Sequence[Prompt[Any]] | None = None,
) -> frozenset[str]:
    """The argparse dests the declarations own — what compilation reads back
    off the namespace. Exposed so the runner can keep add_args from landing
    a custom arg on a declared dest.

    Prompt dests are owned too: a prompt's answer rides ``ctx.ask``, never
    ``ctx.args``, so its dest(s) are stripped from the consumer view (a HARD
    Confirm owns two — the value-carrying yes and the bare no)."""
    owned = frozenset(_dest(t.name) for t in tags or ()) | frozenset(
        _dest(a) for a in depth_aliases or ()
    )
    for prompt in prompts or ():
        owned |= frozenset(prompt.dests())
    return owned


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


# Namespace dests the framework itself owns. Everything else on a parsed
# namespace came from the consumer's add_args, and that is what ctx.args
# surfaces. Declared tag/alias dests are owned too — they compile into
# fidelity, so re-exposing them as args would double-carry the same intent.
_FRAMEWORK_DESTS = frozenset(
    {
        "quiet",
        "verbose",
        "interactive",
        "static",
        "live",
        "json",
        "plain",
        "no_input",
        "max_chars",
        "max_lines",
    }
)


def _check_add_args_dests(
    added: Sequence[argparse.Action],
    tags: Sequence[Tag] | None,
    depth_aliases: Mapping[str, int] | None,
    prompts: Sequence[Prompt[Any]] | None = None,
) -> None:
    """Custom args must not land on a declared tag/alias/prompt dest.

    argparse raises only on duplicate option strings, not duplicate dests — a
    custom arg (or positional) whose dest matches a declared name would
    silently turn the tag on, override depth, or shadow a prompt's parked answer
    at compile time. Same promise as the name collision check, extended to the
    escape hatch.
    """
    declared = declared_dests(tags, depth_aliases, prompts)
    if not declared:
        return
    for action in added:
        if action.dest in declared:
            raise DeclarationError(
                f"add_args registers dest {action.dest!r}, which collides "
                "with a declared tag, depth alias, or prompt"
            )


def build_parser(
    *,
    add_args: Callable[[argparse.ArgumentParser], None] | None = None,
    tags: Sequence[Tag] | None = None,
    depth_aliases: Mapping[str, int] | None = None,
    budgets: bool = False,
    prompts: Sequence[Prompt[Any]] | None = None,
    modes: set[OutputMode] | None = None,
    prog: str | None = None,
    description: str | None = None,
) -> argparse.ArgumentParser:
    """Build a painted CLI parser without render/fetch.

    The single parser the three reflections share: PARSE dispatches it, HELP
    harvests it, COMPLETE lists its options. Extracted from
    ``CliRunner._get_parser`` (minus render/fetch) so completion can construct
    the same parser — same flags, same declaration checks — without
    instantiating a runner or touching the renderer.

    ``modes`` selects which mode flags exist (``-i``/``--live``/``--static``);
    that set depends on fetch_stream/handlers, which the runner computes and
    passes in — the parser stays render/fetch-free.
    """
    parser = argparse.ArgumentParser(description=description, prog=prog, add_help=False)
    # Re-add -h/--help so argparse still recognizes it for error messages.
    parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)

    add_cli_args(
        parser,
        modes=modes,
        tags=tags,
        depth_aliases=depth_aliases,
        budgets=budgets,
        prompts=prompts,
    )

    if add_args is not None:
        framework_actions = len(parser._actions)
        add_args(parser)
        _check_add_args_dests(parser._actions[framework_actions:], tags, depth_aliases, prompts)

    return parser


def consumer_args(
    parsed: argparse.Namespace,
    tags: Sequence[Tag] | None = None,
    depth_aliases: Mapping[str, int] | None = None,
    prompts: Sequence[Prompt[Any]] | None = None,
) -> ArgsView:
    """The add_args-declared args on a parsed namespace, as a read-only view.

    Framework flags and declared tag/alias/prompt dests are the framework's own
    carriers (tags/aliases compile into fidelity; prompt answers ride
    ``ctx.ask``); everything else came from the consumer's add_args, and that is
    what ``ctx.args`` exposes. A prompt's dest never appears in ``ctx.args`` —
    one door for a prompt's answer (design Q3).
    """
    owned = _FRAMEWORK_DESTS | declared_dests(tags, depth_aliases, prompts)
    return ArgsView({k: v for k, v in vars(parsed).items() if k not in owned})


def add_cli_args(
    parser: argparse.ArgumentParser,
    *,
    modes: set[OutputMode] | None = None,
    tags: Sequence[Tag] | None = None,
    depth_aliases: Mapping[str, int] | None = None,
    budgets: bool = False,
    prompts: Sequence[Prompt[Any]] | None = None,
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
        prompts: Declared inline prompts (docs/PROMPTS_DESIGN.md §6). Each
            generates its flag(s) — a Confirm's boolean (or HARD value-carrying)
            pair, a Select's choices-validated flag, an Input's typed value —
            grouped under "Prompts".
    """
    check_declarations(tags, depth_aliases, prompts)

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

    # Interactivity — clig-standard --no-input: disable every prompt (design
    # §6, Q4). Orthogonal to --plain's no *style*; this is no *interactivity*.
    # Wired like every other framework flag so a future framework-flag opt-out
    # suppresses it with the rest (thread/framework-flags-optout).
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Never prompt; resolve inline prompts by flag/default or fail",
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

    # Prompts — declared inline prompts each register their own flag(s). Added
    # last so the "Prompts" group trails the framework flags in bare-argparse
    # help; run_cli intercepts -h, so the rendered doc is what users see.
    if prompts:
        prompt_group = parser.add_argument_group("Prompts")
        for prompt in prompts:
            prompt.add_to_parser(prompt_group)


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
