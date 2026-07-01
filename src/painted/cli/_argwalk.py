"""The shared walk over an argparse parser's actions.

painted builds genuine argparse parsers (``build_parser``); ``-h`` and TAB read
the *same* actions. This module is that single read, yielding a neutral
``ArgSpec`` per action so help projects it to a ``Def`` and completion projects
it to ``Candidate``\\ s — one walk, two reflections, no second source of truth.

Renderer-free by construction (it imports only argparse, and the completion
contract types under ``TYPE_CHECKING``), so it sits on the no-renderer-on-TAB
path.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .complete import Completer


@dataclass(frozen=True)
class ArgSpec:
    """A neutral view of one argparse action.

    ``option_strings`` is empty for a positional. ``is_flag`` is True when the
    action consumes no value (store_true/store_false/count) — completion offers
    the flag itself, never a value after it. ``choices`` and ``completer`` are
    the two value sources: static (T2) and dynamic (T3).

    ``mutex_group`` records which mutually-exclusive group the action joins — its
    index into ``parser._mutually_exclusive_groups``, or ``None`` when ungrouped
    — so completion can suppress a group sibling once one member is on the line
    (the honesty half of the walk). Help ignores it.
    """

    dest: str
    option_strings: tuple[str, ...]
    help: str
    choices: tuple[str, ...] | None
    is_flag: bool
    completer: Completer | None
    mutex_group: int | None = None

    @property
    def is_positional(self) -> bool:
        return not self.option_strings

    @property
    def term(self) -> str:
        """The help term: every option string joined (``-s, --since``), or the
        dest for a positional. Kept intact — no lossy single-alias downcast."""
        return ", ".join(self.option_strings) if self.option_strings else self.dest


def walk_args(parser: argparse.ArgumentParser) -> list[ArgSpec]:
    """Every user-facing action on ``parser`` as ArgSpecs.

    Skips the help action and SUPPRESS-helped actions — neither is a candidate
    the user completes nor a row help renders.
    """
    # Which mutually-exclusive group each action joins, keyed by identity (an
    # argparse action belongs to at most one such group). Same private-attribute
    # footing as the ``parser._actions`` read below.
    mutex_of = {
        id(action): index
        for index, group in enumerate(parser._mutually_exclusive_groups)
        for action in group._group_actions
    }
    specs: list[ArgSpec] = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if action.help is argparse.SUPPRESS:
            continue
        choices = tuple(str(c) for c in action.choices) if action.choices else None
        specs.append(
            ArgSpec(
                dest=action.dest,
                option_strings=tuple(action.option_strings),
                help=action.help or "",
                choices=choices,
                is_flag=action.nargs == 0,
                completer=getattr(action, "completer", None),
                mutex_group=mutex_of.get(id(action)),
            )
        )
    return specs
