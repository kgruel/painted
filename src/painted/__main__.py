"""Entry point for python -m painted.

painted's own front door dogfoods its multi-command CLI framework: the command
table below is dispatched by ``run_app`` (``cli/app_runner.py``) — the same
``run_app`` + ``AppCommand`` painted ships for its consumers. Help, ``-h``
interception, unknown-command handling, and the ``demo`` alias of ``demos`` all
fall out of the framework, not hand-rolled dispatch here."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from painted.cli import AppCommand, complete_via, run_app

if TYPE_CHECKING:
    import argparse

    from painted.cli import Candidate, CompletionContext

# painted's own front door stays render-free until it actually renders: the
# top-level `from painted import Block, …` is deferred into the dispatch
# functions that print, so `painted <TAB>` (the completion gate) and the demos
# completer below never pull the renderer.


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    commands = [
        AppCommand(
            "demos",
            "List available demos, or run one by name",
            _demo_dispatch,
            detail="painted demos [name] — list demos, or run <name>; 'list'/'run' subcommands too.",
            aliases=("demo",),
            add_args=_demos_add_args,
        ),
        AppCommand(
            "docs",
            "List available docs, or render one by name",
            _docs_dispatch,
            add_args=_docs_add_args,
        ),
        AppCommand("tour", "Interactive tour", _tour_dispatch),
    ]
    # Hidden completion smoke backdoor — a render-free way to eyeball the
    # producer without the shell transport's env vars (the real path is the
    # injected `completion` command + the _PAINTED_COMPLETE gate, S4). Pokes the
    # *raw* roster directly: `painted __complete "painted de"` → demos/demo/docs.
    if args and args[0] == "__complete":
        return _complete_dispatch(args[1:], commands)

    return run_app(
        args,
        commands,
        prog="painted",
        description="painted — a semantic renderer for the terminal",
    )


def _complete_dispatch(args: list[str], commands: list[AppCommand]) -> int:
    """Print completion candidates for a raw line — value, then a tab and the
    description when present (the zsh _describe shape the S4 transport formats)."""
    from painted.cli.complete import complete_line

    line = args[0] if args else ""
    point = int(args[1]) if len(args) > 1 else None
    for cand in complete_line(line, point, commands=commands, prog="painted"):
        print(f"{cand.value}\t{cand.description}" if cand.description else cand.value)
    return 0


def _demos_add_args(parser: argparse.ArgumentParser) -> None:
    """Declare the demos `name` positional and hang the demo-name completer.

    The handler stays opaque (it dispatches name/list/run itself); this mirror
    exists so completion and intercepted `-h` can see the one argument that
    matters — the demo to run. The completer is the T3 dynamic seam: demo names
    are runtime data no static `choices` can hold."""
    complete_via(
        parser.add_argument("name", nargs="?", help="Demo to run (omit to list)"),
        _complete_demo_names,
    )


def _complete_demo_names(ctx: CompletionContext) -> list[Candidate]:
    """Every runnable demo as a described candidate (render-free discovery)."""
    from painted._demo_discovery import discover_demos
    from painted.cli import Candidate

    # tour has its own command (group == "") — exclude it, mirroring the list.
    return [Candidate(e.name, e.description) for e in discover_demos() if e.group]


def _docs_add_args(parser: argparse.ArgumentParser) -> None:
    """Declare the docs `name` positional and hang the doc-name completer.

    Unlike demos, the doc registry *is* doc-IR (each page carries live figures),
    so this completer legitimately loads the renderer when invoked — the honest
    contrast to the render-free demos completer: a domain completer pays for the
    data it reflects (cf. loops `--key` hitting the store)."""
    complete_via(
        parser.add_argument("name", nargs="?", help="Doc to render (omit to list)"),
        _complete_doc_names,
    )


def _complete_doc_names(ctx: CompletionContext) -> list[Candidate]:
    """Every doc page as a described candidate."""
    from painted._doc_pages import DOCS
    from painted.cli import Candidate

    return [Candidate(entry.name, entry.description) for entry in DOCS.values()]


def _demo_dispatch(args: list[str]) -> int:
    from painted import Block, Style, print_block
    from painted._demo_cli import list_demos, run_demo

    # No args or flags only → list demos
    if not args or args[0].startswith("-"):
        return list_demos(args)

    sub = args[0]

    # Explicit "list" subcommand
    if sub == "list":
        return list_demos(args[1:])

    # Legacy "run" subcommand
    if sub == "run":
        if len(args) < 2:
            print_block(Block.text("Usage: painted demos <name> [flags]", Style(dim=True)))
            return 1
        return run_demo(args[1], args[2:])

    # Otherwise, first arg is a demo name
    return run_demo(sub, args[1:])


def _docs_dispatch(args: list[str]) -> int:
    from painted._docs_cli import list_docs, run_doc

    # No args or flags only → list docs
    if not args or args[0].startswith("-"):
        return list_docs(args)

    return run_doc(args[0], args[1:])


def _tour_dispatch(args: list[str]) -> int:
    import asyncio
    import importlib.util

    from painted import Block, Style, print_block
    from painted._demo_discovery import _find_demos_root

    root = _find_demos_root()
    if root is None:
        print_block(Block.text("Cannot find demos/ directory", Style(fg="red")))
        return 1

    tour_path = root / "tour.py"
    if not tour_path.exists():
        print_block(Block.text(f"Tour not found: {tour_path}", Style(fg="red")))
        return 1

    spec = importlib.util.spec_from_file_location("demo_tour", tour_path)
    if spec is None or spec.loader is None:
        print_block(Block.text(f"Cannot load: {tour_path}", Style(fg="red")))
        return 1

    module = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv[:]
    saved_mod = sys.modules.get("demo_tour")
    try:
        sys.argv = [str(tour_path)] + args
        sys.modules["demo_tour"] = module
        spec.loader.exec_module(module)
        asyncio.run(module.main())
        return 0
    finally:
        sys.argv = saved_argv
        if saved_mod is None:
            sys.modules.pop("demo_tour", None)
        else:
            sys.modules["demo_tour"] = saved_mod


if __name__ == "__main__":
    sys.exit(main())
