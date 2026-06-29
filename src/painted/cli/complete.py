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

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .types import ArgsView


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
