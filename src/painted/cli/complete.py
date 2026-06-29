"""Shell completion as a painted capability — the third reflection of an
argparse parser, after parse and help.

This module is the producer: given a built parser and the partial command line,
it yields the candidates the parser *declares* — flags, static choices, and the
dynamic values a consumer hangs on an argument via the ``.completer`` seam. The
governing rule is the honesty-rule analog: a candidate exists only because the
parser (or a declared completer) produces it; we never invent candidates.

Renderer-free by construction — the no-renderer-on-TAB guarantee: completion
discloses nothing and delivers nothing, so it imports none of core.block /
core.doc. Its only painted dependency is the renderer-free ``ArgsView``.

Contract types (loops decision design/completer-contract-shape):
  Candidate         — a (value, description) pair; description powers zsh _describe
  CompletionContext — the parsed args so far (ArgsView) + the prefix being typed
  Completer         — Callable[[CompletionContext], Iterable[str | Candidate]]
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .types import ArgsView, OutputMode, build_parser

if TYPE_CHECKING:
    import argparse

    from ._argwalk import ArgSpec
    from .app_runner import AppCommand


@dataclass(frozen=True)
class Candidate:
    """One completion candidate.

    ``description`` is optional context shown alongside the value (zsh renders it
    via ``_describe``; bash uses only ``value``). Described candidates are
    painted's edge over a names-only completer — the producer returns them when
    a parser action or completer supplies a description. A bare ``str`` candidate
    is normalized to ``Candidate(value, "")``.
    """

    value: str
    description: str = ""


@dataclass(frozen=True)
class CompletionContext:
    """What a completer sees: the args resolved so far plus the token being typed.

    ``args`` is the same ``ArgsView`` the runtime hands ``render``/``fetch`` —
    completion's share of the three-reflection trunk — so a domain completer can
    scope candidates to what's already typed (loops ``--key`` narrowed to the
    vertex already present in ``ctx.args``). ``prefix`` is the partial token under
    the cursor (``""`` when the cursor sits on a fresh word).

    Deliberately *not* ``CliContext``: its fidelity/mode/use_ansi/is_tty are
    resolved rendering context, meaningless at TAB time — reusing it would
    fabricate those fields (the honesty rule). CompletionContext = ArgsView +
    prefix; CliContext = ArgsView + rendering. The shared trunk is ArgsView.
    """

    args: ArgsView = field(default_factory=ArgsView)
    prefix: str = ""


# A completer is the consumer's seam for the dynamic values the parser can't
# hold (loops vertex/--kind/--key): hang it on an argument as ``action.completer``
# (the argcomplete-compatible attribute convention) and the producer invokes it
# with the CompletionContext. It returns bare strings or described Candidates;
# the producer normalizes either.
Completer = Callable[["CompletionContext"], Iterable["str | Candidate"]]


# =============================================================================
# The producer — one parser's candidates for the token under the cursor
# =============================================================================


def complete_args(
    parser: argparse.ArgumentParser,
    preceding: Sequence[str],
    prefix: str = "",
    *,
    args: ArgsView | None = None,
) -> list[Candidate]:
    """Completion candidates for the token being typed on ``parser``.

    ``preceding`` are the fully-typed argument tokens before the cursor (the
    command name already stripped); ``prefix`` is the partial token under it
    (``""`` on a fresh word). ``args`` is the namespace resolved so far, handed
    to completers via ``CompletionContext.args`` (empty when omitted).

    Two contexts, decided by ``preceding``:

    * **value** — the previous token is an option that takes a value
      (``--format <cursor>``): only that option's value candidates (static
      ``choices`` and/or its ``.completer``), nothing else.
    * **word** — otherwise: every declared option string, plus the active
      positional's value candidates. The prefix filter separates them — ``-``
      keeps flags, a bare prefix keeps positional values.

    The result is prefix-filtered, de-duplicated by value, and sorted. Only what
    the parser declares ever appears — no invented candidates (the honesty rule).
    """
    from ._argwalk import walk_args

    specs = walk_args(parser)
    ctx_args = args if args is not None else ArgsView()

    value_spec = _pending_value_spec(specs, preceding)
    if value_spec is not None:
        return _finish(_value_candidates(value_spec, ctx_args, prefix), prefix)

    cands: list[Candidate] = [
        Candidate(opt, spec.help) for spec in specs for opt in spec.option_strings
    ]
    pos_spec = _active_positional(specs, preceding)
    if pos_spec is not None:
        cands.extend(_value_candidates(pos_spec, ctx_args, prefix))
    return _finish(cands, prefix)


def _pending_value_spec(specs: list[ArgSpec], preceding: Sequence[str]) -> ArgSpec | None:
    """The option whose value the cursor is on — the last token is a
    value-taking option string. ``None`` in word context."""
    if not preceding:
        return None
    last = preceding[-1]
    if not last.startswith("-"):
        return None
    for spec in specs:
        if last in spec.option_strings and not spec.is_flag:
            return spec
    return None


def _value_candidates(spec: ArgSpec, ctx_args: ArgsView, prefix: str) -> list[Candidate]:
    """An argument's value candidates: static ``choices`` then its ``.completer``.

    A raising completer yields nothing rather than a traceback into the shell —
    completion must degrade quietly at TAB time."""
    cands: list[Candidate] = []
    if spec.choices:
        cands.extend(Candidate(c) for c in spec.choices)
    if spec.completer is not None:
        ctx = CompletionContext(args=ctx_args, prefix=prefix)
        try:
            items = list(spec.completer(ctx))
        except Exception:
            items = []
        cands.extend(item if isinstance(item, Candidate) else Candidate(item) for item in items)
    return cands


def _active_positional(specs: list[ArgSpec], preceding: Sequence[str]) -> ArgSpec | None:
    """The positional the cursor would fill — the (n+1)th, where n positional
    values are already consumed. Extra tokens fall to the last positional (it may
    be ``nargs='*'``/REMAINDER); ``None`` when the parser has no positionals."""
    positionals = [s for s in specs if s.is_positional]
    if not positionals:
        return None
    consumed = _count_consumed_positionals(specs, preceding)
    return positionals[consumed] if consumed < len(positionals) else positionals[-1]


def _count_consumed_positionals(specs: list[ArgSpec], preceding: Sequence[str]) -> int:
    """How many positional values ``preceding`` already supplies — bare tokens,
    skipping each value-taking option's own value."""
    value_taking = {opt for s in specs for opt in s.option_strings if not s.is_flag}
    count = 0
    skip = False
    for tok in preceding:
        if skip:
            skip = False
            continue
        if tok.startswith("-"):
            if tok in value_taking:
                skip = True  # the next token is this option's value, not a positional
            continue
        count += 1
    return count


def _finish(cands: list[Candidate], prefix: str) -> list[Candidate]:
    """Prefix-filter, de-dup by value, sort."""
    seen: set[str] = set()
    out: list[Candidate] = []
    for c in cands:
        if not c.value.startswith(prefix) or c.value in seen:
            continue
        seen.add(c.value)
        out.append(c)
    out.sort(key=lambda c: c.value)
    return out


# =============================================================================
# The app level — roster completion + forwarding into a command's parser
# =============================================================================


def complete_app(
    commands: Sequence[AppCommand],
    preceding: Sequence[str],
    prefix: str = "",
    *,
    prog: str | None = None,
    default: AppCommand | None = None,
    args: ArgsView | None = None,
) -> list[Candidate]:
    """Completion candidates for a ``run_app`` command line.

    ``preceding`` are the typed tokens after the program name; ``prefix`` is the
    token under the cursor. The first token is the command name:

    * **empty preceding** — completing the command itself: every command name and
      alias (described by the command's summary), plus, when a ``default`` is
      declared, that command's first positional (the ``loops <vertex>``
      shorthand — names *and* vertices coexist at the first slot).
    * **matched command** — forward to that command's parser, built render-free
      via ``build_parser`` with the conservative mode default (``-i``/``--live``/
      ``--static`` omitted unless the command declares delivery — it can't yet,
      so they stay off; the honesty rule prefers under-listing).
    * **no match but a default** — forward to the default's parser with the full
      ``preceding`` (the default keeps argv[0] as positional data).

    ``AppCommand`` is read by attribute only (never imported at runtime) so this
    stays on the no-renderer-on-TAB path.
    """
    if not preceding:
        cands = _roster_candidates(commands)
        if default is not None:
            cands.extend(complete_args(_command_parser(default, prog), [], prefix, args=args))
        return _finish(cands, prefix)

    head, rest = preceding[0], preceding[1:]
    cmd = _match_command(commands, head)
    if cmd is not None:
        return complete_args(_command_parser(cmd, prog), rest, prefix, args=args)
    if default is not None:
        return complete_args(_command_parser(default, prog), preceding, prefix, args=args)
    return []


def _roster_candidates(commands: Sequence[AppCommand]) -> list[Candidate]:
    """Every command name and alias, described by its command's summary."""
    cands: list[Candidate] = []
    for cmd in commands:
        cands.append(Candidate(cmd.name, cmd.description))
        cands.extend(Candidate(alias, cmd.description) for alias in cmd.aliases)
    return cands


def _match_command(commands: Sequence[AppCommand], token: str) -> AppCommand | None:
    """The command a token routes to — its name or one of its aliases."""
    for cmd in commands:
        if token == cmd.name or token in cmd.aliases:
            return cmd
    return None


def complete_line(
    line: str,
    point: int | None = None,
    *,
    commands: Sequence[AppCommand],
    prog: str | None = None,
    default: AppCommand | None = None,
) -> list[Candidate]:
    """Candidates for a raw command line, completing the token at ``point``.

    A convenience over ``complete_app`` for smoke-testing and simple transports:
    it splits the line and locates the prefix token (the partial word under the
    cursor, or ``""`` after a trailing space), drops the program name, and
    forwards to ``complete_app``. ``point`` defaults to the end of the line.

    This is the *naive* split — robust COMP_LINE/COMP_POINT handling (quoting,
    ``--opt=val`` splitting, word boundaries) is the shell transport's job (S4).
    """
    if point is None:
        point = len(line)
    left = line[:point]
    words = _split_line(left)
    if left and not left[-1].isspace():
        prefix = words[-1] if words else ""
        preceding = words[1:-1]
    else:
        prefix = ""
        preceding = words[1:]
    return complete_app(commands, preceding, prefix, prog=prog, default=default)


def _split_line(text: str) -> list[str]:
    """Tokenize a partial command line, tolerating an unbalanced quote."""
    import shlex

    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _command_parser(cmd: AppCommand, prog: str | None) -> argparse.ArgumentParser:
    """The command's parser, built render-free with the conservative mode set.

    modes={STATIC} suppresses the whole mode group (-i/--live/--static): an
    AppCommand can't declare its delivery capability, so completion under-lists
    rather than suggest a flag the command may reject."""
    prog_str = f"{prog} {cmd.name}" if prog else cmd.name
    return build_parser(
        add_args=cmd.add_args,
        tags=cmd.tags,
        modes={OutputMode.STATIC},
        prog=prog_str,
    )
