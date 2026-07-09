"""Inline prompts — the DECLARED rung of the parser's fourth reflection.

A prompt is an **input**, and painted's CLI grammar already has an input channel:
declared flags. ``--force`` and ``Are you sure? [y/N]`` are the same declaration
at different fidelities — one resolves from argv, one resolves interactively at a
TTY. This module ships the *declaration* (``Prompt[T]`` and its three domain
shapes ``Confirm``/``Select``/``Input``), the flag generation those declarations
buy, and the headless resolution contract (``ctx.ask``): argv flag → interactive
at a TTY → declared default → ``ContractError`` naming the channel. See
``docs/PROMPTS_DESIGN.md``.

Scope, DECLARED rung (§12 step 1): construction-time rules, flag generation,
``--no-input``, memoized resolution, the ``(default)`` record line, and the
stderr-routed refusal — testable with a faked ``stdin.isatty()`` and no terminal.

Interactive rungs: cooked-mode rendering lives in the private sibling
``cli/_prompt_line.py`` (LINE, the accessibility floor) and raw-mode repaint in
``.._prompt_cell`` (CELL, the top rung), both imported lazily from
:meth:`PromptSession._render_interactive` — the one point this module reaches
past DECLARED. Every danger tier resolves at both rungs: a ``danger=HARD``
``Confirm`` renders its type-the-challenge ceremony (§9) — only the exact
challenge approves; anything else resolves ``False``, fail-closed.

This is evolving ``painted.cli`` surface (design Q2): the domain shapes and
``ask`` live here, not on the semver-stable renderer surface, until 1.x hardens
them. The module is render-free at import: it imports ``painted.vocabulary`` (the
mark channel, for ``Select(vocabulary=)``) and ``argparse``, never the renderer —
the ``(default)`` record line pulls ``core``/``palette`` lazily, inside the one
function that draws it, matching ``cli/runner.py``'s framework→renderer boundary.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import total_ordering
from typing import TYPE_CHECKING, Any, Generic, TextIO, TypeVar

from ..core.errors import ContractError, DeclarationError
from ..vocabulary import Vocabulary, vocab_style

if TYPE_CHECKING:
    from .complete import Completer

__all__ = [
    "MISSING",
    "Danger",
    "Prompt",
    "Confirm",
    "Select",
    "Input",
]

T = TypeVar("T")


# =============================================================================
# MISSING — the "no declared answer" sentinel
# =============================================================================


class _MissingType:
    """The type of the :data:`MISSING` sentinel — a private singleton.

    ``default`` is sentinel-guarded, not ``None``-guarded (design §6): absent
    means "no declared answer" (non-TTY falls through to ``ContractError``),
    while ``default=None`` declares ``None`` *as* the answer — a distinction a
    ``None`` default could never carry. Falsy so ``if prompt.default:`` reads
    naturally, but identity (``is MISSING``) is the contract.
    """

    _instance: _MissingType | None = None

    def __new__(cls) -> _MissingType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Any = _MissingType()


# The argparse default for every prompt dest — a private sentinel meaning "argv
# did not supply this flag". Presence must be sentinel-based, not None-based:
# an ``Input(parse=...)`` may legally *parse to* ``None`` (or a flag may carry a
# literal that parses to None), which is a supplied answer, not an absent flag.
# ``None`` as the default would collapse those two — the flag-supplied None would
# read as "absent" and refuse (non-TTY) or re-prompt (TTY). A distinct sentinel
# keeps "absent" and "parsed to None" separable at the ``flag_supplied`` seam.
# Separate from ``MISSING`` (which marks an absent *declared default*, a
# different axis): this one lives only in the parked argv namespace.
_UNSET: Any = object()


# =============================================================================
# Danger — the ordered confirmation-ceremony vocabulary
# =============================================================================


@total_ordering
class Danger(Enum):
    """Confirmation ceremony tier — a painted builtin *ordered* vocabulary.

    ``NONE < SOFT < HARD``. Ordered because the ceremony *escalates*: the
    comparisons (``danger >= Danger.SOFT``) drive the construction rules here
    and the interactive ceremony (the rendered prompt), exactly as ``Severity``
    ordering drives gutter escalation. Modeled as a total-ordered enum rather than a
    ``vocabulary.Vocabulary`` because the tiers carry *behavior*, not color —
    the design sanctions "a total-ordered frozen class ... match how Severity is
    done" when a color-bearing Vocabulary doesn't fit (design §9).

    - ``NONE`` — y/N, Enter accepts the default; the only tier that may carry
      ``default=``.
    - ``SOFT`` — "did you mean to proceed?"; an explicit key, no Enter-default,
      ``default=`` forbidden.
    - ``HARD`` — "do you know what you're aiming at?"; type the declared
      ``challenge`` (``Confirm``-only), a value-carrying flag, ``default=``
      forbidden.
    """

    NONE = 0
    SOFT = 1
    HARD = 2

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Danger):
            return NotImplemented
        return self.value < other.value


# A prompt name becomes both a ``--flag`` spelling and a record-line label, so
# it obeys the same kebab discipline as ``Tag``/``Vocabulary``. Deliberate local
# duplicate of ``cli.types._DECLARED_NAME_RE`` (kept in sync by review): this
# module is duck-typed *into* ``cli.types`` — types calls a prompt's methods,
# never the reverse — so importing types' private regex would invert that.
_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def _never_completes(_ctx: Any) -> tuple[str, ...]:
    """The "complete nothing" completer (COMPLETION_DESIGN §5's explicit
    opt-out: a completer returning no candidates suppresses both dynamic
    candidates *and* the open-slot file/dir fallback ``wants_file_completion``
    would otherwise offer). Wired onto HARD's value-carrying challenge flag —
    typing the challenge is the ceremony (design §9); a completer would let a
    shell surface it, defeating the point of demanding it be typed.
    """
    return ()


class PromptContractError(ContractError):
    """A prompt refusal, routed to stderr by the runner (design §8).

    Structurally a ``ContractError`` (so ``except ContractError`` and
    ``pytest.raises(ContractError)`` catch it), but its *stream* is stderr: the
    remediation text ("pass ``--overwrite``") must never ride the stdout data
    pipe into ``jq``. The runner's error-block path recognizes this subclass and
    reroutes; every other ``ContractError`` keeps stdout. Private — the public
    contract names ``ContractError``, not this seam.
    """


class PromptAbort(KeyboardInterrupt):
    """A prompt was aborted at the terminal — Ctrl-C or EOF at the read (§7).

    A ``KeyboardInterrupt`` subclass so §7's rule "a prompt abort is a
    ``KeyboardInterrupt``" stays literally true: every ``except
    KeyboardInterrupt`` still catches it, and the terminal-restore paths (LINE's
    restoring newline, CELL's cbreak exit) fire unchanged. The subclass exists so
    the runner's live/surface loops — which catch ``KeyboardInterrupt`` as a
    *graceful stop* (exit 0) — can tell a prompt abort apart and re-raise it,
    letting it propagate out of ``run_cli`` exactly as it already does from
    static mode (terminal restored, no exit-0). Private, like
    ``PromptContractError``: the contract names the abort, not this seam.
    """


# =============================================================================
# Prompt[T] — one primitive, three domain shapes
# =============================================================================


@dataclass(frozen=True)
class Prompt(Generic[T]):
    """A declared question — the semantic primitive (design §6).

    ``name`` is the flag spelling and the record-line label; ``question`` is the
    rendered text; ``default`` is the declared non-TTY answer
    (:data:`MISSING`-guarded); ``danger`` is the ceremony tier. The *domain*
    ("what answers exist, and ``str → T``") is realized by the three concrete
    shapes below — each supplies answer parsing, membership, and its flag
    shape — rather than a standalone field: ``Confirm``/``Select``/``Input`` are
    subclasses of this one primitive, so the resolution ladder, the stdin gate,
    the record-line collapse, and the danger tiers are written once here.

    Not instantiated directly — use a domain shape. The shared construction
    rules (name discipline, ``danger >= SOFT`` forbids ``default=``, a declared
    default must be in the domain) live in :meth:`__post_init__`; each subclass
    adds its own rules and calls up.
    """

    name: str
    question: str
    default: T | _MissingType = MISSING
    danger: Danger = Danger.NONE

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise DeclarationError(
                f"Prompt name {self.name!r} must be lowercase kebab-case "
                "(it becomes both the --flag and the record-line label)"
            )
        if self.danger >= Danger.SOFT and self.default is not MISSING:
            raise DeclarationError(
                f"Prompt {self.name!r}: danger={self.danger.name} forbids default= "
                "— a default that silently resolves in a script evaporates the "
                "guard exactly where nobody is watching; only Danger.NONE may "
                "carry a default"
            )
        if self.default is not MISSING and not self._admits(self.default):
            raise DeclarationError(
                f"Prompt {self.name!r}: default {self.default!r} is not in the "
                "prompt's domain (a declared default is validated at construction)"
            )

    # --- domain hooks (each shape overrides) ---------------------------------

    def _admits(self, value: object) -> bool:
        """Whether ``value`` is a member of this prompt's domain."""
        raise NotImplementedError

    def _format(self, value: T) -> str:
        """Human spelling of a resolved answer, for the record line."""
        return str(value)

    # --- flag grammar (duck-typed by cli.types) ------------------------------

    @property
    def dest(self) -> str:
        """The primary argparse dest — kebab name to snake."""
        return self.name.replace("-", "_")

    def dests(self) -> tuple[str, ...]:
        """Every namespace dest this prompt owns (stripped from ``ctx.args``)."""
        return (self.dest,)

    def flag_spellings(self) -> tuple[str, ...]:
        """The ``--flag`` spellings this declaration generates.

        Read by the reserved-registry collision check at parser construction and
        named in the refusal message. A subclass overrides to describe its shape
        (``Confirm`` → both boolean spellings; ``Select``/``Input`` → one).
        """
        raise NotImplementedError

    def add_to_parser(self, container: argparse._ActionsContainer) -> None:
        """Register this prompt's argument(s) on ``container``."""
        raise NotImplementedError

    def flag_supplied(self, parked: Mapping[str, object]) -> bool:
        """Whether argv supplied an answer (read off the parked namespace)."""
        raise NotImplementedError

    def resolve_flag(self, parked: Mapping[str, object]) -> T:
        """The answer argv supplied — may raise ``PromptContractError``.

        Called lazily (on ``ctx.ask``), never at parse time: a HARD challenge
        mismatch is a resolution-time refusal, so eager validation cannot refuse
        a run over a question never asked. (``Input``'s ``parse`` is the one
        exception — it runs eagerly as argparse ``type=``, so a malformed
        ``--reason`` fails at parse like any typed flag.)
        """
        raise NotImplementedError

    def resolve_default(self) -> T:
        """The answer form of the declared default (design §3 rule 2).

        Identity for most shapes — the default *is* the answer. ``Input``
        overrides: its declared default is the raw string form, mapped through
        ``parse`` so the default rides the same ``str → T`` path as the flag,
        keeping "same declaration, same domain" across the flag and default
        channels. Only called when ``default is not MISSING``.
        """
        return self.default  # type: ignore[return-value]  # guarded: not MISSING


# --- Confirm — Prompt[bool] --------------------------------------------------


@dataclass(frozen=True)
class Confirm(Prompt[bool]):
    """A yes/no question over the two-element domain ``{True, False}``.

    Generates ``--{name}`` / ``--no-{name}`` (BooleanOptionalAction-shaped). The
    only shape that carries ``challenge=`` and admits ``danger=HARD`` (design
    §9): a HARD confirm demands the operator type a declared token to proceed,
    and its flags become the pair ``--{name} <challenge>`` (value-carrying yes)
    + bare ``--no-{name}`` (no ceremony needed to decline).
    """

    challenge: str | None = None

    def __post_init__(self) -> None:
        if self.danger is Danger.HARD:
            if self.challenge is None:
                raise DeclarationError(
                    f"Confirm {self.name!r}: danger=HARD requires challenge= (the "
                    "token the operator types to proceed); ceremony with nothing "
                    "to type is a dead declaration"
                )
            if not self.challenge.strip():
                raise DeclarationError(
                    f"Confirm {self.name!r}: challenge= must be a non-empty token; "
                    "an empty or whitespace-only challenge is satisfied by --"
                    f'{self.name} "" (an unset shell variable), the very accident '
                    "the HARD tier exists to refuse (§9)"
                )
        if self.challenge is not None and self.danger is not Danger.HARD:
            raise DeclarationError(
                f"Confirm {self.name!r}: challenge= is only meaningful at "
                "danger=HARD (a challenge that can never fire is a dead "
                "declaration)"
            )
        super().__post_init__()

    def _admits(self, value: object) -> bool:
        return isinstance(value, bool)

    def _format(self, value: bool) -> str:
        return "yes" if value else "no"

    @property
    def _no_dest(self) -> str:
        return f"no_{self.dest}"

    def dests(self) -> tuple[str, ...]:
        if self.danger is Danger.HARD:
            return (self.dest, self._no_dest)
        return (self.dest,)

    def flag_spellings(self) -> tuple[str, ...]:
        return (f"--{self.name}", f"--no-{self.name}")

    def add_to_parser(self, container: argparse._ActionsContainer) -> None:
        if self.danger is Danger.HARD:
            # A mutually exclusive pair: the value-carrying yes and the bare no.
            group = container.add_mutually_exclusive_group()
            challenge_action = group.add_argument(
                f"--{self.name}",
                dest=self.dest,
                default=_UNSET,
                metavar="CHALLENGE",
                help=f"{self.question} (type the challenge to proceed)",
            )
            # The challenge value never completes (design §9): typing it is the
            # ceremony, so a shell must not surface it as a candidate.
            from .complete import complete_via

            complete_via(challenge_action, _never_completes)
            group.add_argument(
                f"--no-{self.name}",
                dest=self._no_dest,
                action="store_true",
                help=f"Decline: {self.question}",
            )
            return
        # NONE / SOFT: a boolean pair. default=_UNSET so "not passed" is
        # distinguishable from an explicit --{name}/--no-{name} (which set
        # True/False) — the presence sentinel, not None.
        container.add_argument(
            f"--{self.name}",
            action=argparse.BooleanOptionalAction,
            default=_UNSET,
            dest=self.dest,
            help=self.question,
        )

    def flag_supplied(self, parked: Mapping[str, object]) -> bool:
        if self.danger is Danger.HARD:
            return parked.get(self.dest, _UNSET) is not _UNSET or bool(parked.get(self._no_dest))
        return parked.get(self.dest, _UNSET) is not _UNSET

    def resolve_flag(self, parked: Mapping[str, object]) -> bool:
        if self.danger is Danger.HARD:
            if parked.get(self._no_dest):
                return False
            attempt = parked.get(self.dest)
            if attempt != self.challenge:
                raise PromptContractError(
                    f"--{self.name} {attempt!r} does not match the required "
                    f"challenge {self.challenge!r}; type the challenge exactly to "
                    "proceed (a generic affirmative never satisfies a HARD confirm)"
                )
            return True
        return bool(parked.get(self.dest))


# --- Select — Prompt over an enumerable domain -------------------------------


@dataclass(frozen=True)
class Select(Prompt[str]):
    """A choice over an *enumerable* domain — a values tuple XOR a Vocabulary.

    ``values=`` is an open tuple (the series-shaped case); ``vocabulary=`` is a
    declared :class:`~painted.vocabulary.Vocabulary` whose members *are* the
    legal values (so completion completes them and the mark channel styles them
    in the rendered prompt — one declaration feeding several generators). Exactly
    one of the two is required. Generates ``--{name} {choices}``,
    choices-validated by the parser. ``danger=HARD`` is a ``DeclarationError``:
    the ecosystem has no dangerous select — decompose "dangerously choose" into
    choose (harmless) → HARD confirm (design §9).
    """

    values: tuple[str, ...] | None = None
    vocabulary: Vocabulary | None = None

    def __post_init__(self) -> None:
        if self.values is not None:
            values = tuple(self.values)
            object.__setattr__(self, "values", values)
            # Domain coherence: the flag channel is str, so the domain must be a
            # non-empty set of unique, non-empty strings — otherwise a default or
            # runtime answer could carry a value the flag could never produce
            # (mirrors Vocabulary's own construction checks).
            if not values:
                raise DeclarationError(f"Select {self.name!r} declares no values")
            if any(not isinstance(v, str) or not v for v in values):
                raise DeclarationError(
                    f"Select {self.name!r} values must be non-empty strings (the "
                    "flag channel is str, so the domain is too)"
                )
            if len(set(values)) != len(values):
                raise DeclarationError(f"Select {self.name!r} has duplicate values")
        has_values = self.values is not None
        has_vocab = self.vocabulary is not None
        if has_values == has_vocab:
            raise DeclarationError(
                f"Select {self.name!r} needs exactly one of values= or "
                "vocabulary= (got " + ("both" if has_values else "neither") + ")"
            )
        if self.danger is Danger.HARD:
            raise DeclarationError(
                f"Select {self.name!r}: danger=HARD is Confirm-only — decompose a "
                "dangerous choice into choose (harmless) then a HARD Confirm that "
                "knows the target's name"
            )
        super().__post_init__()

    @property
    def choices(self) -> tuple[str, ...]:
        """The legal values — the tuple, or the vocabulary's members."""
        if self.values is not None:
            return self.values
        assert self.vocabulary is not None  # XOR guaranteed at construction
        return tuple(self.vocabulary.values)

    def _admits(self, value: object) -> bool:
        return value in self.choices

    def flag_spellings(self) -> tuple[str, ...]:
        return (f"--{self.name}",)

    def add_to_parser(self, container: argparse._ActionsContainer) -> None:
        container.add_argument(
            f"--{self.name}",
            dest=self.dest,
            choices=list(self.choices),
            default=_UNSET,
            help=self.question,
        )

    def flag_supplied(self, parked: Mapping[str, object]) -> bool:
        return parked.get(self.dest, _UNSET) is not _UNSET

    def resolve_flag(self, parked: Mapping[str, object]) -> str:
        # argparse already validated membership via choices=.
        return str(parked[self.dest])


# --- Input — Prompt over an open domain --------------------------------------


@dataclass(frozen=True)
class Input(Prompt[T]):
    """A free-text question over an *open* domain (design §6).

    ``parse=`` is an optional ``str → T`` callable: it raises to reject, and its
    return value *becomes the answer* (``Input("count", parse=int)`` resolves the
    int ``42``). It is the domain — the same callable runs on both channels, so
    the flag and the default produce the same ``T``. On the flag channel it is
    argparse's ``type=``, so a malformed ``--count abc`` fails at parse like any
    typed flag; the declared ``default`` is the raw string form, mapped through
    ``parse`` at resolution (validated at construction). Without ``parse``,
    ``Input`` is a ``Prompt[str]`` and the answer is the raw string.

    ``completer=`` rides the third reflection (design §6's domain table):
    attached to the generated flag's action via ``complete_via``, its
    candidates replace the open-slot file/dir fallback ``wants_file_completion``
    would otherwise offer. Without one, the flag stays an open slot and gets
    that fallback. ``danger=HARD`` is a ``DeclarationError`` (HARD is
    ``Confirm``-only, §9).
    """

    parse: Callable[[str], T] | None = None
    completer: Completer | None = None

    def __post_init__(self) -> None:
        if self.danger is Danger.HARD:
            raise DeclarationError(
                f"Input {self.name!r}: danger=HARD is Confirm-only — lift a "
                "dangerous free-text action into a HARD Confirm (design §9)"
            )
        super().__post_init__()

    def _admits(self, value: object) -> bool:
        # The declared default is the raw string form (the same shape argv
        # supplies), so parse maps it exactly as it maps a flag value.
        if not isinstance(value, str):
            return False
        if self.parse is not None:
            try:
                self.parse(value)
            except Exception:
                return False
        return True

    def resolve_default(self) -> T:
        if self.parse is not None:
            return self.parse(self.default)  # type: ignore[arg-type]  # default is the raw str form
        return self.default  # type: ignore[return-value]  # Prompt[str] when parse is None

    def flag_spellings(self) -> tuple[str, ...]:
        return (f"--{self.name}",)

    def add_to_parser(self, container: argparse._ActionsContainer) -> None:
        # parse is argparse's type=, so the flag and the default share one
        # str → T map. Omitted when parse is None — the open-domain str default.
        if self.parse is not None:
            action = container.add_argument(
                f"--{self.name}",
                dest=self.dest,
                default=_UNSET,
                type=self.parse,
                metavar=self.dest.upper(),
                help=self.question,
            )
        else:
            action = container.add_argument(
                f"--{self.name}",
                dest=self.dest,
                default=_UNSET,
                metavar=self.dest.upper(),
                help=self.question,
            )
        if self.completer is not None:
            # Riding the third reflection (design §6's domain table): a
            # declared completer's candidates, in place of the open-slot
            # file/dir fallback wants_file_completion would otherwise offer.
            from .complete import complete_via

            complete_via(action, self.completer)

    def flag_supplied(self, parked: Mapping[str, object]) -> bool:
        return parked.get(self.dest, _UNSET) is not _UNSET

    def resolve_flag(self, parked: Mapping[str, object]) -> T:
        # argparse already applied parse via type=, so the parked value is T
        # (which may legally be None — flag_supplied's sentinel test kept this
        # answer distinct from an absent flag).
        return parked[self.dest]  # type: ignore[return-value]


# =============================================================================
# PromptSession — the memoized answer store behind ctx.ask
# =============================================================================


class PromptSession:
    """The resolution engine ``ctx.ask`` delegates to.

    Holds the parse-time declared prompts, the parked argv answers, the stream
    state that gates interaction (§3, §8), and the memo. Not a dataclass — it
    owns mutable memo state that a frozen ``CliContext`` references by one
    field, so the frozen-collection invariant sees a plain object, not a dict.
    Every ``CliContext`` carries one (an empty, non-interactive session by
    default) so a runtime ``ctx.ask(Select(...))`` always has the stream policy.
    """

    def __init__(
        self,
        prompts: Sequence[Prompt[Any]] = (),
        parked: Mapping[str, object] | None = None,
        *,
        stdin_tty: bool = False,
        stderr_tty: bool = False,
        no_input: bool = False,
        force_plain: bool = False,
        stdin: TextIO | None = None,
    ) -> None:
        self._by_name: dict[str, Prompt[Any]] = {p.name: p for p in prompts}
        self._declared: frozenset[str] = frozenset(self._by_name)
        self._parked: Mapping[str, object] = dict(parked or {})
        self._stdin_tty = stdin_tty
        self._stderr_tty = stderr_tty
        self._no_input = no_input
        # --plain forces the LINE rung and strips ANSI from the *whole* prompt UI
        # (§5, §8): plain requested → LINE, byte-for-byte the accessibility
        # exchange, no cbreak repaint and no SGR — even at a full TTY, and the
        # answer→record line follows suit (:attr:`_use_ansi`).
        self._force_plain = force_plain
        # The LINE rung's injectable read stream (design §10) — for tests only;
        # the public contract stays §3. Captured once, at construction, the same
        # moment stdin_tty/stderr_tty are — not re-read per ask() the way a bare
        # `sys.stdin` reference would drift if something reassigned it mid-run.
        self._stdin: TextIO = stdin if stdin is not None else sys.stdin
        self._answers: dict[str, Any] = {}

    @property
    def _use_ansi(self) -> bool:
        """Whether prompt UI on stderr may carry SGR — the one ANSI gate.

        Styled only when stderr is a TTY *and* ``--plain`` was not requested
        (§8): the render fidelity follows stderr's own TTY-ness, but ``--plain``
        overrides it to a plain exchange across the whole prompt UI (the rendered
        prompt and its answer→record line alike).
        """
        return self._stderr_tty and not self._force_plain

    def ask(self, prompt: str | Prompt[Any]) -> Any:
        """Resolve a prompt once — the single door (design Q3).

        Accepts a declared name (str) or a runtime declaration object. Memoized
        by name: a prompt fires at most once, and a second read returns the
        recorded answer. An undeclared name is a ``DeclarationError`` naming the
        declared prompts, never a bare ``KeyError``. A runtime declaration whose
        name collides with a parse-time declared prompt is also a
        ``DeclarationError``: it would otherwise silently resolve against the
        declared prompt's parked flag answer — outside the runtime domain — so
        the caller is told to reach the declared prompt by name instead.
        """
        if isinstance(prompt, str):
            resolved = self._by_name.get(prompt)
            if resolved is None:
                declared = sorted(self._by_name)
                raise DeclarationError(
                    f"ctx.ask({prompt!r}): no prompt named {prompt!r} is declared. "
                    f"Declared prompts: {declared or '(none)'}"
                )
            p: Prompt[Any] = resolved
            name = prompt
        else:
            p = prompt
            name = p.name
            if name in self._declared:
                raise DeclarationError(
                    f"ctx.ask() was handed a runtime prompt named {name!r}, which "
                    "is already declared at parse time; resolve the declared "
                    f"prompt by name — ctx.ask({name!r}) — so its flag and domain "
                    "apply, rather than shadowing it with a second declaration"
                )

        if name in self._answers:
            return self._answers[name]
        value = self._resolve(p)
        self._answers[name] = value
        return value

    def _resolve(self, p: Prompt[Any]) -> Any:
        # Resolution order (design §6): argv flag → interactive at a TTY →
        # declared default → ContractError naming the channel.
        if p.flag_supplied(self._parked):
            return p.resolve_flag(self._parked)
        if self._stdin_tty and not self._no_input:
            # A human is driving and no flag answered: render an interactive
            # prompt and read the answer.
            return self._interactive(p)
        # No terminal (or --no-input): the default fires on *absence of a
        # terminal*, not on EOF (§3 rule 5).
        if p.default is not MISSING:
            value = p.resolve_default()
            self._emit_record(p, value, suffix=" (default)")
            return value
        # A runtime Select whose domain collapsed to a single value resolves to
        # it through the declared channel (§6, the gum --select-if-one shape):
        # there is nothing to ask when exactly one answer is legal. Runtime-only
        # — a parse-time Select keeps its flag channel and refuses without it,
        # so a scripted invocation stays explicit. Echoes like (default): an
        # assumed answer the invocation doesn't show.
        if isinstance(p, Select) and p.name not in self._declared and len(p.choices) == 1:
            value = p.choices[0]
            self._emit_record(p, value, suffix=" (only choice)")
            return value
        raise self._refusal(p)

    def _interactive(self, p: Prompt[Any]) -> Any:
        """Render an interactive prompt and read its answer (design §5).

        Every danger tier has a live path at both rungs — a HARD confirm renders
        its type-the-challenge ceremony (§9) at CELL and at LINE alike, chosen
        capability-honestly by :meth:`_render_interactive`, and either rung feeds
        the same answer→record collapse (§7).
        """
        value = self._render_interactive(p)
        self._emit_record(p, value, suffix="")
        return value

    def _render_interactive(self, p: Prompt[Any]) -> Any:
        """Pick the fidelity rung and render (design §5).

        Capability-honest, same as mode resolution: CELL (raw-mode repaint) needs
        stdin a TTY *and* stderr a TTY (CELL repaints on the stream it draws —
        repainting into a log is not a render) *and* cbreak actually available on
        stdin, probed before any terminal mutation. ``--plain`` forces the floor
        regardless of capability (§5): plain requested → LINE, no ANSI. Anything
        short of the CELL bar falls to LINE, the accessibility floor — same
        options, same answer type (§5), so a downgrade is byte-for-byte the
        slice-2 exchange. The stdin gate itself was already cleared by the caller.
        """
        if not self._force_plain and self._stdin_tty and self._stderr_tty:
            from ..keyboard import cbreak_supported

            if cbreak_supported(self._stdin):
                from .._prompt_cell import resolve_cell

                return resolve_cell(p, stdin=self._stdin, stderr=sys.stderr)

        from ._prompt_line import resolve_line

        return resolve_line(p, stdin=self._stdin, stderr=sys.stderr, use_ansi=self._use_ansi)

    def _refusal(self, p: Prompt[Any]) -> PromptContractError:
        """The terraform-shaped rule-3 refusal (design §3, §8), stderr-routed."""
        if p.name in self._declared:
            flags = " / ".join(f"`{s}`" for s in p.flag_spellings())
            return PromptContractError(
                f"stdin is not a terminal and no answer was provided for {p.name!r} — pass {flags}"
            )
        # A runtime declaration has no flag; name the channel that does exist.
        return PromptContractError(
            f"stdin is not a terminal and no answer was provided for {p.name!r}; "
            "it was declared at runtime, so no flag exists — supply a default= at "
            "the ctx.ask call site for non-interactive use"
        )

    def _emit_record(self, p: Prompt[Any], value: Any, *, suffix: str) -> None:
        """Emit the one static ``✓ name: value`` collapse line to stderr (§7).

        Shared by both resolution paths that produce a *new* answer this run
        (a declared default firing non-interactively, or a LINE/CELL prompt
        actually asked) — a flag-supplied answer never reaches here, because
        it is already visible in the invocation (§7's "the record line marks
        an answer the invocation doesn't show"). ``suffix`` is the only
        difference between the two: ``" (default)"`` marks an answer nobody
        chose; an interactively-asked answer gets none. Drawn with core
        primitives only (never ``views`` — the cli→views boundary) and
        imported lazily here, the single point this module touches the
        renderer. Fidelity follows :attr:`_use_ansi` (§8): piped stderr —
        or ``--plain`` at any TTY — renders plain, no ANSI.

        The answer's own style is its declared mark when the prompt is a
        vocabulary-backed ``Select`` (design §7: "styled by the answer's mark
        where a vocabulary is declared") — resolved through ``vocab_style``,
        the same by-reference seam ``views/record.py`` uses, so the record
        line matches the mark everywhere else it appears. Every other shape
        (and a ``values=``-tuple ``Select``, which has no vocabulary to mark
        with) keeps the plain ``accent`` role, unchanged.
        """
        from ..core.cell import Style
        from ..core.span import Line, Span
        from ..core.writer import print_block
        from ..icon_set import current_icons
        from ..palette import current_palette

        palette = current_palette()
        icons = current_icons()
        value_style = palette.accent
        if isinstance(p, Select) and p.vocabulary is not None:
            value_style = vocab_style(p.vocabulary, value)
        line = Line(
            (
                Span(f"{icons.ok} ", palette.success),
                Span(f"{p.name}: ", Style()),
                Span(p._format(value), value_style),
                Span(suffix, palette.muted),
            )
        )
        block = line.to_block(max(1, line.width))
        print_block(block, sys.stderr, use_ansi=self._use_ansi)
