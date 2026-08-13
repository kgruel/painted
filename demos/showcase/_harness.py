"""The showcase harness — the scaffolding, so the files can be just the demos.

Ten showcases wrote the same entry point: peel demo args off with a throwaway
parser, hand the parsed values to ``fetch``/``fetch_stream`` closures, then call
``run_cli`` with four settings that are the same every time and a ``help_args``
list restating every arg the throwaway parser already declared. Every argument
was declared twice — once for parsing, once for ``--help`` — and every default
written twice. No demo had drifted yet; the point is that none of them can now.

**Why this is safe here and nowhere else in demos/.** A pattern demo's
``run_cli`` call *is* its lesson — "the invocation IS the lesson", per
demos/CLAUDE.md. Hiding it behind a harness would delete the curriculum. A
showcase is the one tier the same file calls "spectacle, not teaching": the
output is the point, and the entry point is scaffolding that gets pixels on
screen. So the harness stops at the showcase boundary, which is a line the
tier model already drew — not a new one invented here.

What stays in a demo after this: its docstring, its data, its trace, its
carriers, its ``_render``, and a declaration of the args it takes.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from painted import ROUNDED, Block, border, join_vertical, run_cli
from painted.cli import HelpArg, Tag

__all__ = ["ShowcaseArg", "plate", "showcase_main"]


@dataclass(frozen=True)
class ShowcaseArg:
    """One demo argument, declared once.

    The harness spends it twice — on the pre-parser that peels it off before
    ``run_cli`` sees the argv, and on the ``HelpArg`` that puts it back into
    ``--help``. That double spend is exactly the duplication this dissolves:
    the two declarations can no longer disagree about a name or a default.
    """

    name: str  # "--frame"
    help: str  # "pose shown by static output (live spins from 0)"
    default: Any
    type: Callable[[str], Any] | None = None  # None: argparse's str
    choices: tuple[str, ...] = field(default=())


def _pre_parser(args: Iterable[ShowcaseArg]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    for arg in args:
        kwargs: dict[str, Any] = {"default": arg.default}
        if arg.type is not None:
            kwargs["type"] = arg.type
        if arg.choices:
            kwargs["choices"] = arg.choices
        parser.add_argument(arg.name, **kwargs)
    return parser


def showcase_main(
    *,
    doc: str | None,
    file: str,
    renderer: Callable[..., Block],
    fetch: Callable[[argparse.Namespace], Any],
    fetch_stream: Callable[[argparse.Namespace], Any] | None = None,
    args: Iterable[ShowcaseArg] = (),
    tags: Iterable[Tag] = (),
) -> int:
    """Run a showcase: peel its args, then deliver it to a surface.

    ``doc`` and ``file`` are the caller's ``__doc__`` and ``__file__``, passed
    rather than inspected — a harness that reached into its caller's frame to
    find them would be the kind of clever this codebase spends its comments
    arguing against. ``prog`` derives from ``file``, which retires ten
    hand-maintained strings that could each drift from their own filename.

    ``fetch``/``fetch_stream`` take the parsed namespace and return the demo's
    data. The harness does not try to wire arguments into them: which arg feeds
    which call is the demo's business, and a harness guessing at it would be a
    worse contract than a two-line closure.

    Everything a showcase does not vary is fixed here: surface delivery (the
    tier's defining property), the live meter, and ``description=__doc__``.
    """
    declared = tuple(args)
    namespace, rest = _pre_parser(declared).parse_known_args(sys.argv[1:])
    return run_cli(
        rest,
        renderer=renderer,
        fetch=lambda: fetch(namespace),
        fetch_stream=None if fetch_stream is None else (lambda: fetch_stream(namespace)),
        live_delivery="surface",
        live_meter=True,
        description=doc,
        prog=Path(file).name,
        tags=list(tags),
        help_args=[HelpArg(a.name, a.help, default=str(a.default)) for a in declared],
    )


def plate(*rows: Block, title: str) -> Block:
    """The framed viewing plate — every showcase's outer frame.

    Thin by construction: it is exactly the composition all ten already wrote,
    and it earns its place by naming the tier's visual identity rather than by
    being hard. Width is deliberately absent — a demo that pins its inner width
    to its own raster (mandelbrot does) must do that before it gets here, or
    the frame would start moving with the terminal instead of with the work.
    """
    return border(join_vertical(*rows), title=title, chars=ROUNDED)
