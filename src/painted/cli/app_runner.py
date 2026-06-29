"""AppRunner: app-level command routing through painted.

Mirrors the CliRunner + run_cli pattern one level up. CliRunner handles
a single command with zoom/mode/format; AppRunner routes between multiple
commands and renders top-level help through painted.

Usage:
    from painted.cli import run_app, AppCommand

    commands = [
        AppCommand("status", "Show store status", _run_status),
        AppCommand("log", "Show recent facts", _run_log),
    ]
    run_app(sys.argv[1:], commands, prog="myapp")
"""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import Format, Tag, Zoom, check_declarations

if TYPE_CHECKING:
    import argparse

    from ..core.block import Block
    from ..core.doc import Doc, Node
    from .help import HelpArg

# core.doc and .help are imported lazily inside the render methods below, never
# at module top: constructing an AppCommand and completing it must not pull the
# renderer (the no-renderer-on-TAB rule). The render path pays the import only
# when -h / no-args actually renders help — mirroring how _render_doc already
# defers core.fidelity.


def _render_doc(doc: Doc, zoom: Zoom, width: int) -> "Block":
    """Project a help Doc to a Block at the given zoom (Format strips styles)."""
    from ..core.doc import doc_lens
    from ..core.fidelity import Fidelity

    return doc_lens(doc, fidelity=Fidelity(depth=int(zoom)), width=width)


def _command_term(cmd: AppCommand) -> str:
    """The command row's term — its name, plus its aliases parenthesized.

    Aliases ride on the term (``demos (alias: demo)``) rather than a separate
    row: one routable concept, one definition entry. The label pluralizes so the
    single common case reads naturally."""
    if not cmd.aliases:
        return cmd.name
    label = "alias" if len(cmd.aliases) == 1 else "aliases"
    return f"{cmd.name} ({label}: {', '.join(cmd.aliases)})"


@dataclass(frozen=True)
class AppCommand:
    """A routable command with name, description, and handler.

    The handler receives argv (remaining args after command name) and
    returns an exit code. ``tags`` mirrors the handler's own declarations so
    the intercepted ``-h`` path renders the same Layers group the handler's
    run_cli would — declare in one place and pass the same list to both.

    ``add_args`` is the same convention-single-source mirror for the command's
    own arguments: the author passes the *same* callback to both this field and
    the handler's ``run_cli(add_args=...)`` call (cf. ``tags``). Declaring it
    here lets one callback serve three consumers — the parse (the handler's
    run_cli), the intercepted ``-h`` (derived via ``command_defs``), and
    completion (which walks ``build_parser(add_args=...)``) — without the
    handler ceasing to be opaque. It supersedes ``help_args``: where
    ``help_args`` re-describes args already declared in code, ``add_args`` *is*
    the declaration, introspected directly. The callback must be a pure parser
    builder (it is invoked to introspect the args; it must only call
    ``parser.add_argument`` and never act on them).
    """

    name: str  # "status"
    description: str  # "Show store status"
    handler: Callable[[list[str]], int]  # receives argv[1:], returns exit code
    detail: str | None = None  # shown at DETAILED+ zoom, e.g. usage hint
    help_args: Sequence[HelpArg] | None = None  # when set, AppRunner intercepts -h
    tags: Sequence[Tag] | None = None  # declared layers, shown in intercepted help
    add_args: Callable[[argparse.ArgumentParser], None] | None = (
        None  # declared args; intercepts -h
    )
    aliases: tuple[str, ...] = ()  # alternate spellings that route to this command

    def __post_init__(self) -> None:
        # Defensively coerce a caller-owned sequence to a tuple so this frozen
        # value cannot be mutated through a retained reference (cf. Block).
        if self.help_args is not None and not isinstance(self.help_args, tuple):
            object.__setattr__(self, "help_args", tuple(self.help_args))
        if self.tags is not None and not isinstance(self.tags, tuple):
            object.__setattr__(self, "tags", tuple(self.tags))
        if not isinstance(self.aliases, tuple):
            object.__setattr__(self, "aliases", tuple(self.aliases))
        # Declarations are promises — validate here, same as parser construction.
        # Alias↔command collisions need every command's full name set, so they
        # are checked at AppRunner construction (see _check_alias_collisions),
        # not here where only this command is in view.
        check_declarations(self.tags, None)


@dataclass(frozen=True)
class AppRunner:
    """App-level command router with painted help rendering.

    Routes argv[0] to the matching AppCommand handler. When no args
    or --help/-h is given, renders help through painted (zoom-aware).

    ``default`` lifts the "primary-noun shorthand" into the framework: when
    argv[0] matches no command and is not a flag, it routes to the default
    handler with the *full* argv (the token is positional data, not a consumed
    command name). This is ``loops <vertex>`` ⇒ ``read <vertex>`` — a CLI whose
    primary noun is a bare token, without a hand-rolled pre-router in front of
    the runner. Omitted (``None``), an unmatched token is an error, unchanged.
    """

    commands: tuple[AppCommand, ...]
    prog: str | None = None
    description: str | None = None
    default: AppCommand | None = None

    def __post_init__(self) -> None:
        # The command table is the place where every name and alias is in view,
        # so cross-command collisions are validated here — the alias analogue of
        # check_declarations. A spelling that routes to two commands, or an alias
        # shadowed by a real command name, is a broken promise, caught at wiring
        # time rather than silently shadowing at dispatch.
        self._check_alias_collisions()

    def _check_alias_collisions(self) -> None:
        """Validate names and aliases route unambiguously — no spelling claimed twice.

        Declarations are promises (cf. check_declarations): a command name
        repeated across commands, an alias that duplicates its own command's
        name, collides with another command's name, or collides with another
        command's alias all raise here, at runner construction. Names and
        aliases share one dispatch namespace (``run`` matches either), so a
        duplicate name is the same broken promise as a duplicate alias — caught
        here rather than silently shadowing at dispatch (first handler wins, the
        rest is dead code).
        """
        names: set[str] = set()
        for cmd in self.commands:
            if cmd.name in names:
                raise ValueError(f"Command name {cmd.name!r} is declared by more than one command")
            names.add(cmd.name)
        seen_aliases: dict[str, str] = {}  # alias → owning command name
        for cmd in self.commands:
            own_aliases: set[str] = set()  # this command's aliases, for intra-command dups
            for alias in cmd.aliases:
                if alias == cmd.name:
                    raise ValueError(f"Command {cmd.name!r} lists {alias!r} as an alias of itself")
                if alias in own_aliases:
                    # A single command listing the same alias twice is its own
                    # error class — reporting it through the alias↔alias branch
                    # below would name this very command as the "other" owner,
                    # which reads as self-referential nonsense.
                    raise ValueError(f"Command {cmd.name!r} lists alias {alias!r} more than once")
                if alias in names:
                    raise ValueError(
                        f"Alias {alias!r} of command {cmd.name!r} collides with command {alias!r}"
                    )
                if alias in seen_aliases:
                    raise ValueError(
                        f"Alias {alias!r} of command {cmd.name!r} collides with "
                        f"the same alias of command {seen_aliases[alias]!r}"
                    )
                own_aliases.add(alias)
                seen_aliases[alias] = cmd.name

    def run(self, argv: list[str]) -> int:
        """Route argv to command handler, or show help."""
        # Completion gate first: when the shell glue calls back (the
        # _PAINTED_COMPLETE env var), emit candidates and exit before any
        # routing or rendering — the no-renderer-on-TAB path. The import is
        # lazy so constructing/running normally never pulls the transport.
        from .completion_shell import completion_active, run_completion

        shell = completion_active()
        if shell is not None:
            return run_completion(self.commands, prog=self.prog, default=self.default, shell=shell)

        # No args → painted help
        if not argv:
            return self._handle_help([])

        name = argv[0]

        # Command name (or alias) first → dispatch (or intercept -h for action commands)
        rest = argv[1:]
        for cmd in self.commands:
            if name == cmd.name or name in cmd.aliases:
                intercepts = cmd.help_args is not None or cmd.add_args is not None
                if intercepts and ("-h" in rest or "--help" in rest):
                    return self._handle_subcommand_help(cmd, rest)
                return cmd.handler(rest)

        # No command matched, but a declared default claims an unmatched
        # non-flag token: route to it with the *full* argv — the token is the
        # primary noun (positional data), not a consumed command name. Note the
        # deliberate slicing asymmetry: matched commands above get ``rest``
        # (argv[1:], name consumed); the default gets ``argv`` (name kept). The
        # ``startswith("-")`` guard keeps ``-h``/``--help`` (and any leading
        # flag) falling through to top-level help below, never to the default.
        if self.default is not None and not name.startswith("-"):
            return self.default.handler(argv)

        # No command matched — check for --help/-h (top-level help)
        if "-h" in argv or "--help" in argv:
            return self._handle_help(argv)

        # Unknown command → error + help to stderr
        from ..core.block import Block
        from ..core.cell import Style
        from ..core.writer import print_block

        try:
            from ..palette import current_palette

            error_style = current_palette().error
        except Exception:
            error_style = Style(fg="red")

        error_block = Block.text(f"Unknown command: {name}", error_style)
        print_block(error_block, sys.stderr, use_ansi=True)

        # Show help to stderr
        width = shutil.get_terminal_size().columns
        help_block = _render_doc(self._help_doc(), Zoom.SUMMARY, width)
        print_block(help_block, sys.stderr, use_ansi=True)

        return 1

    def _handle_help(self, args: list[str]) -> int:
        """Render zoom-aware help and return 0."""
        return self._emit_help(self._help_doc(), args)

    def _handle_subcommand_help(self, cmd: AppCommand, args: list[str]) -> int:
        """Render zoom-aware help for a subcommand and return 0."""
        return self._emit_help(self._subcommand_help_doc(cmd), args)

    def _emit_help(self, doc: Doc, args: list[str]) -> int:
        """Project a help Doc to the active format and print it."""
        from ..core.writer import print_block

        from .help import scan_help_args

        zoom, fmt = scan_help_args(args)

        if fmt == Format.JSON:
            from dataclasses import asdict

            print(json.dumps(asdict(doc), default=str))
            return 0

        use_ansi = fmt != Format.PLAIN
        if fmt == Format.AUTO:
            use_ansi = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

        width = shutil.get_terminal_size().columns
        print_block(_render_doc(doc, zoom, width), use_ansi=use_ansi)
        return 0

    def _subcommand_help_doc(self, cmd: AppCommand) -> Doc:
        """Help Doc for a subcommand — its own args plus the Help group.

        Args come from either declaration mirror: ``help_args`` (re-described)
        or ``add_args`` (introspected). command_defs merges both, so a command
        migrating help_args → add_args renders the same arg list throughout.
        """
        from ..core.doc import Defs, Doc, Prose
        from .help import command_defs, framework_sections

        assert cmd.help_args is not None or cmd.add_args is not None

        cmd_defs = command_defs(cmd.help_args, cmd.add_args)
        # Help subordinates only when the command has its own args to lead with.
        framework_depth = Zoom.SUMMARY if cmd_defs else Zoom.MINIMAL

        body: list[Node] = []
        if cmd.description:
            body.append(Prose(cmd.description))
        if cmd_defs:
            body.append(Defs(cmd_defs))
        body.extend(framework_sections(framework_depth, include_options=False, tags=cmd.tags))

        prog = f"{self.prog} {cmd.name}" if self.prog else cmd.name
        return Doc(title=prog, body=tuple(body))

    def _help_doc(self) -> Doc:
        """Top-level help Doc — the command list leads, framework groups follow."""
        from ..core.doc import Def, Defs, Doc, Prose, Section
        from .help import framework_sections

        body: list[Node] = []
        if self.description:
            body.append(Prose(self.description))
        commands = Defs(
            tuple(
                Def(term=_command_term(cmd), summary=cmd.description, detail=cmd.detail)
                for cmd in self.commands
            )
        )
        body.append(Section("Commands", body=(commands,)))  # min_depth 0 — always expanded
        body.extend(framework_sections(Zoom.SUMMARY))
        return Doc(title=self.prog, body=tuple(body))


def run_app(
    argv: list[str],
    commands: list[AppCommand] | tuple[AppCommand, ...],
    *,
    prog: str | None = None,
    description: str | None = None,
    default: AppCommand | None = None,
) -> int:
    """Run an app with command routing and painted help.

    Convenience function that creates an AppRunner and runs it.

    Each command's handler receives the remaining argv and returns an exit
    code; the expected shape is a function that calls ``run_cli`` with that
    argv, so every subcommand gets the framework flags (zoom, format, mode,
    declared tags). Per-subcommand ``-h`` is intercepted when the AppCommand
    sets ``help_args`` *or* ``add_args`` (and ``tags``, mirroring the handler's
    own declarations) — without any of them, ``-h`` falls through to the
    handler. Prefer ``add_args`` (the same callback the handler passes to
    ``run_cli``): one declaration introspected for help and completion alike.

    Args:
        argv: Command-line arguments (sys.argv[1:])
        commands: Available commands
        prog: Program name for help
        description: Program description for help
        default: Command for an unmatched non-flag argv[0] (the primary-noun
            shorthand). Its handler receives the *full* argv. Often the same
            AppCommand also appears in ``commands`` so it stays in help; omitted,
            an unmatched token is an error.

    Returns:
        Exit code (0 for success)
    """
    return AppRunner(
        commands=_with_completion(tuple(commands), prog),
        prog=prog,
        description=description,
        default=default,
    ).run(argv)


def _with_completion(commands: tuple[AppCommand, ...], prog: str | None) -> tuple[AppCommand, ...]:
    """Append the framework's ``completion`` command unless the app owns the name.

    Every ``run_app`` roster gains ``completion`` (emit shell glue) for free —
    the third reflection delivered without per-app wiring. If the consumer
    already declares a ``completion`` command or alias, theirs stands and the
    injection is skipped: the auto-add must not turn a working app into a
    construction-time collision (the alias-collision check would otherwise
    raise). Lazy import keeps the transport off the module-load path."""
    from .completion_shell import (
        COMPLETION_COMMAND_NAME,
        completion_add_args,
        completion_handler,
    )

    taken = {c.name for c in commands} | {a for c in commands for a in c.aliases}
    if COMPLETION_COMMAND_NAME in taken:
        return commands
    return commands + (
        AppCommand(
            COMPLETION_COMMAND_NAME,
            "Print shell completion setup (e.g. `completion zsh`)",
            completion_handler(prog),
            detail=f'{prog or "app"} completion zsh > "${{fpath[1]}}/_{prog or "app"}"',
            add_args=completion_add_args,
        ),
    )
