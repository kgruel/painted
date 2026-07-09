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
# the producer normalizes either. A completer that is genuinely expensive to run
# (a scan, a network call) can memoize inside its own callable — the seam is the
# callable, so painted needs no cache framework for it (see docs/COMPLETION_DESIGN.md §7).
Completer = Callable[["CompletionContext"], Iterable["str | Candidate"]]


def complete_via(action: argparse.Action, completer: Completer) -> argparse.Action:
    """Attach a dynamic ``completer`` to an argparse ``action`` and return it.

    The typed front door for the ``.completer`` seam — composes inline with
    ``add_argument`` so the attachment is one declarative line::

        complete_via(parser.add_argument("branch", help="..."), complete_branch)

    ``action.completer = completer`` works too and is what argcomplete reads, but
    argparse's ``Action`` has no ``completer`` field, so a direct assignment
    trips the editor's type checker at every call site. This sets the attribute
    the same way the producer reads it (``getattr(action, "completer", None)``) —
    symmetric ``setattr``/``getattr`` on one conventional attribute — so no site,
    painted's own included, has to reach past the type. A completer attached this
    way stays visible to argcomplete; ``complete_via`` is the front door, not a
    replacement for the underlying attribute."""
    setattr(action, "completer", completer)
    return action


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
    # ctx.args is the args-so-far a completer scopes against. Caller-supplied
    # wins; otherwise derive it by tolerantly parsing ``preceding`` through this
    # parser — but only when a completer is actually present (the parse is the
    # producer's one moment of execution, skipped when nothing reads it).
    if args is not None:
        ctx_args = args
    elif any(s.completer is not None for s in specs):
        ctx_args = _tolerant_args(parser, preceding)
    else:
        ctx_args = ArgsView()

    value_spec = _pending_value_spec(specs, preceding)
    if value_spec is not None:
        return _finish(_value_candidates(value_spec, ctx_args, prefix), prefix)

    blocked = _mutex_blocked(specs, preceding)
    cands: list[Candidate] = [
        Candidate(opt, spec.help)
        for spec in specs
        for opt in spec.option_strings
        if opt not in blocked
    ]
    pos_spec = _active_positional(specs, preceding)
    if pos_spec is not None:
        # A "-" prefix (with no "--" end-of-options marker) is a flag being typed.
        # Static choices are still offered — they're cheap and a value can be
        # dash-leading (a negative-number choice like -1) — but the positional's
        # dynamic completer is skipped: its discovery can be expensive (a scan, a
        # network call) and its values are almost never dash-leading (painted's
        # own demos/docs completers never are). A completer that does emit a
        # dash-leading value (rare) is simply not consulted in flag context.
        completing_flag = prefix.startswith("-") and "--" not in preceding
        cands.extend(
            _value_candidates(pos_spec, ctx_args, prefix, include_completer=not completing_flag)
        )
    return _finish(cands, prefix)


def _tolerant_args(parser: argparse.ArgumentParser, preceding: Sequence[str]) -> ArgsView:
    """The namespace ``preceding`` resolves to on ``parser``, as an ArgsView.

    A completer's typed context (loops ``--key`` narrowed to the vertex already
    on the line) — the args-so-far reflected through the very parser TAB is
    completing. Tolerant by construction: an incomplete line is the normal case
    at TAB time, so a missing required positional or an unknown token must yield
    a partial namespace, never a usage error into the shell. ``parse_known_args``
    keeps what parsed; ``SystemExit`` (argparse's ``error()``) and its usage
    text are swallowed, leaving whatever defaults the parser declared."""
    import argparse as _argparse
    import contextlib
    import io

    namespace = _argparse.Namespace()
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            namespace, _ = parser.parse_known_args(list(preceding), namespace)
    except (SystemExit, Exception):
        pass
    return ArgsView(vars(namespace))


def wants_file_completion(parser: argparse.ArgumentParser, preceding: Sequence[str]) -> bool:
    """True when the value slot under the cursor is an *open* value — one the
    parser can't enumerate (no static ``choices``, no ``.completer``).

    This is the producer's half of file/dir completion: it classifies the slot,
    the shell does the filesystem walk (zsh ``_files`` / bash ``compopt -o
    default``). painted never reads the disk — completion stays render-free and
    side-effect-free; the shell already knows how to complete paths (``~``
    expansion, hidden-file rules, the user's own ``zstyle``).

    The open slot is the value-taking option whose value the cursor is on
    (``--output <cursor>``), or otherwise the active positional. An option or
    positional that declares choices/a completer is *not* open — its candidates
    are the completion, and offering files alongside would be noise. A consumer
    who wants a free-text value with *no* file fallback gives it a completer that
    returns ``[]`` (the explicit opt-out).
    """
    from ._argwalk import walk_args

    specs = walk_args(parser)
    slot = _pending_value_spec(specs, preceding)
    if slot is None:
        slot = _active_positional(specs, preceding)
    return slot is not None and not slot.choices and slot.completer is None


def app_wants_file_completion(
    commands: Sequence[AppCommand],
    preceding: Sequence[str],
    *,
    prog: str | None = None,
    default: AppCommand | None = None,
) -> bool:
    """``wants_file_completion`` at the app level — mirrors ``complete_app``'s
    routing so the transport asks the same parser the candidates came from.

    Completing the command name itself (empty ``preceding``) is never a file
    slot — you're choosing a verb, not a path."""
    if not preceding:
        return False
    head, rest = preceding[0], preceding[1:]
    cmd = _match_command(commands, head)
    if cmd is not None:
        return wants_file_completion(_command_parser(cmd, prog), rest)
    if default is not None:
        return wants_file_completion(_command_parser(default, prog), preceding)
    return False


def _walk_preceding(
    specs: list[ArgSpec], preceding: Sequence[str]
) -> list[tuple[str, frozenset[str]]]:
    """Walk ``preceding`` once, classifying each token as one of four kinds.

    Returns a list of ``(kind, present)`` pairs where:

    * ``kind`` is one of ``"option"`` / ``"option_value"`` / ``"positional"`` /
      ``"separator"``.
    * ``present`` is a ``frozenset`` of the option strings this token marks as
      *present on the line* — non-empty only for ``"option"`` tokens.

    This is the **single walk** that both ``_count_consumed_positionals`` and
    ``_present_option_strings`` are built on, so they can never disagree. Before
    this shared walk they were independent and could produce contradictory results
    for inline short values (``-n5``) because one walk would classify the token
    differently from the other.

    Token forms handled:

    * Exact long option (``--verbose``): kind ``option``, present ``{"--verbose"}``.
    * Long option with inline value (``--opt=val``): ONE token, kind ``option``,
      present ``{"--opt"}``; the next token is *not* consumed as a value.
    * Long value-taking option without inline value (``--since 2020``): TWO tokens;
      ``--since`` → ``option``, ``2020`` → ``option_value``.
    * Exact short option (``-q``): kind ``option``; next consumed if value-taking.
    * Short cluster — all-flag (``-vv``, ``-qv``): kind ``option``, present is the
      union of recognized short flags.
    * Short cluster with inline value (``-n5``): kind ``option``, present ``{"-n"}``;
      the inline value is part of the same token, so the next token is *not* skipped.
    * Bare ``-`` and ``--``: kind ``separator``.
    * Anything else (non-option-starting): kind ``positional``.

    Documented limitation: ``nargs=N>1`` positionals are not modelled — each token
    is counted independently of how many tokens one positional action actually
    consumes. Completing multi-token positionals correctly would require the
    ``nargs`` field from ``ArgSpec`` and a more complex walk; that is a completeness
    gap, documented here and deferred, not a regression from the prior independent
    walks (which had the same blind spot)."""
    value_taking = {opt for s in specs for opt in s.option_strings if not s.is_flag}
    short_flags = {
        opt
        for s in specs
        if s.is_flag
        for opt in s.option_strings
        if len(opt) == 2 and opt.startswith("-") and not opt.startswith("--")
    }

    result: list[tuple[str, frozenset[str]]] = []
    skip_next = False
    for tok in preceding:
        if skip_next:
            skip_next = False
            result.append(("option_value", frozenset()))
            continue
        if not tok.startswith("-") or tok in ("-", "--"):
            kind = "separator" if tok in ("-", "--") else "positional"
            result.append((kind, frozenset()))
            continue
        if tok.startswith("--"):
            head = tok.split("=", 1)[0]
            if "=" not in tok and head in value_taking:
                skip_next = True
            result.append(("option", frozenset([head])))
        elif len(tok) == 2:
            # exact short option
            if tok in value_taking:
                skip_next = True
            result.append(("option", frozenset([tok])))
        else:
            # short cluster: -vv / -qv / -n5 (value-taking short with inline value)
            present: set[str] = set()
            for ch in tok[1:]:
                opt = f"-{ch}"
                if opt in short_flags:
                    present.add(opt)
                elif opt in value_taking:
                    # inline value: rest of cluster is the value, no next-token skip
                    present.add(opt)
                    break
                else:
                    break  # unknown char — stop decomposing
            result.append(("option", frozenset(present)))
    return result


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


def _value_candidates(
    spec: ArgSpec, ctx_args: ArgsView, prefix: str, *, include_completer: bool = True
) -> list[Candidate]:
    """An argument's value candidates: static ``choices`` then its ``.completer``.

    ``include_completer=False`` yields only the (cheap, static) ``choices`` and
    skips the dynamic completer — used in flag context, where the completer's
    discovery can be expensive and its values are almost never dash-leading.
    A raising completer yields nothing rather than a traceback into the shell —
    completion must degrade quietly at TAB time."""
    cands: list[Candidate] = []
    if spec.choices:
        cands.extend(Candidate(c) for c in spec.choices)
    if include_completer and spec.completer is not None:
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
    """How many positional values ``preceding`` already supplies.

    Counts tokens classified as ``"positional"`` by ``_walk_preceding`` — bare
    non-option tokens that are not the value of a value-taking option."""
    return sum(1 for kind, _ in _walk_preceding(specs, preceding) if kind == "positional")


def _present_option_strings(specs: list[ArgSpec], preceding: Sequence[str]) -> set[str]:
    """Option strings already on the line — the input to mutex suppression.

    Collects the ``present`` sets from ``_walk_preceding`` so the classification
    is guaranteed consistent with ``_count_consumed_positionals`` (both walk the
    same shared tokenizer; independent walks could disagree on inline short values
    like ``-n5``).

    Handles: exact options (``--static``, ``-q``), the ``--opt=val`` inline form
    (head is present), and short-flag clusters (``-vv`` / ``-qv`` members count
    as present). A value-taking option's *separate* value token is classified as
    ``"option_value"`` by the walk and contributes nothing to ``present``.

    Abbreviations (argparse's ``allow_abbrev``) are matched by exact spelling,
    not resolved — a typed ``--stat`` does not register ``--static``. Documented
    limitation, not a correctness claim: suppression is a strict improvement over
    the pre-mutex behavior even where it under-fires."""
    result: set[str] = set()
    for _kind, present in _walk_preceding(specs, preceding):
        result |= present
    return result


def _mutex_blocked(specs: list[ArgSpec], preceding: Sequence[str]) -> set[str]:
    """Option strings to drop from the word-context flag list because a
    mutually-exclusive *sibling* is already present.

    A member is never blocked by its OWN presence — argparse accepts ``-v -v``
    (=``-vv``) and ``-q -q``, so the honesty rule keeps offering it; only a
    *different* group member blocks. So ``-v`` present suppresses ``-q``/
    ``--quiet``/``--brief``/``--full`` (its zoom-group siblings) but not
    ``-v``/``--verbose`` (its own spelling)."""
    present = _present_option_strings(specs, preceding)
    present_by_group: dict[int, set[str]] = {}
    for spec in specs:
        if spec.mutex_group is None:
            continue
        hit = present.intersection(spec.option_strings)
        if hit:
            present_by_group.setdefault(spec.mutex_group, set()).update(hit)
    blocked: set[str] = set()
    for spec in specs:
        if spec.mutex_group is None:
            continue
        group_present = present_by_group.get(spec.mutex_group)
        if group_present and (group_present - set(spec.option_strings)):
            blocked.update(spec.option_strings)
    return blocked


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
    words = _tolerant_split(left)
    if left and not left[-1].isspace():
        prefix = words[-1] if words else ""
        preceding = words[1:-1]
    else:
        prefix = ""
        preceding = words[1:]
    return complete_app(commands, preceding, prefix, prog=prog, default=default)


def _tolerant_split(text: str) -> list[str]:
    """Tokenize a partial line, tolerating an unbalanced quote.

    Canonical home for this helper — ``completion_shell.py`` re-imports it from
    here so both the transport and ``complete_line`` share one implementation.

    A half-typed ``--kind "lo`` makes ``shlex`` raise; closing the quote recovers
    the intended token (``lo``, without the stray quote char) so the prefix filter
    still matches. If even that fails, fall back to a naive whitespace split rather
    than dropping the completion request."""
    import shlex

    try:
        return shlex.split(text)
    except ValueError:
        for close in ('"', "'"):
            try:
                return shlex.split(text + close)
            except ValueError:
                continue
        return text.split()


def _command_parser(cmd: AppCommand, prog: str | None) -> argparse.ArgumentParser:
    """The command's parser, built render-free with the conservative mode set.

    modes={STATIC} suppresses the whole mode group (-i/--live/--static): an
    AppCommand can't declare its delivery capability, so completion under-lists
    rather than suggest a flag the command may reject. ``prompts`` rides the
    same ``build_parser`` every other declaration does (docs/PROMPTS_DESIGN.md
    §12 step 4) — a prompt-generated flag completes exactly as a ``tags``- or
    ``add_args``-declared one does, with zero completion-specific code: the
    producer walks whatever actions the parser holds, never asking who
    registered them."""
    prog_str = f"{prog} {cmd.name}" if prog else cmd.name
    return build_parser(
        add_args=cmd.add_args,
        tags=cmd.tags,
        prompts=cmd.prompts,
        modes={OutputMode.STATIC},
        prog=prog_str,
    )
