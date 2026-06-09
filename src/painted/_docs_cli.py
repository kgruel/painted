"""Docs command: render in-code documents to the terminal via the doc lens.

The terminal front door for the doc-IR (``docs/DOC_IR_DESIGN.md``). The pages
themselves live in ``_doc_pages.py`` — authored node trees shared with the site
publisher — and render through ``run_cli``, so ``-v``/``-vv`` map to
``Fidelity.depth`` and ``--show <tag>`` populates ``Fidelity.visible``, the same
Fidelity that drives every other painted surface. This module is dispatch only.

Render one: ``painted docs primitives -v --show rationale``.
"""

from __future__ import annotations

import argparse

from painted import Block, Style, join_vertical, print_block, run_cli
from painted.cli import OutputMode
from painted.core.fidelity import Fidelity
from painted.core.doc import Doc, doc_lens
from painted._doc_pages import DOCS


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def list_docs(_args: list[str]) -> int:
    rows = [Block.text("Available docs", Style(bold=True)), Block.text(" ", Style())]
    for entry in DOCS.values():
        rows.append(Block.text(f"  {entry.name:<14}{entry.description}", Style()))
    rows.append(Block.text(" ", Style()))
    rows.append(
        Block.text(
            "Run painted docs <name> [-v|-vv] [--show <tag>]",
            Style(dim=True),
        )
    )
    print_block(join_vertical(*rows))
    return 0


def run_doc(name: str, args: list[str]) -> int:
    entry = DOCS.get(name)
    if entry is None:
        print_block(Block.text(f"Unknown doc: {name}", Style(fg="red")))
        list_docs([])
        return 1

    doc = entry.build()

    def _add_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--show",
            action="append",
            default=[],
            metavar="TAG",
            help="Reveal a tagged layer (e.g. rationale)",
        )

    def _build_fidelity(parsed: argparse.Namespace, fid: Fidelity) -> Fidelity:
        tags = getattr(parsed, "show", None) or []
        return fid.with_visible(*tags) if tags else fid

    def render(ctx, d: Doc) -> Block:
        return doc_lens(d, fidelity=ctx.fidelity, width=ctx.width)

    return run_cli(
        args,
        render=render,
        fetch=lambda: doc,
        default_mode=OutputMode.STATIC,
        description=entry.description,
        prog=f"painted docs {name}",
        add_args=_add_args,
        build_fidelity=_build_fidelity,
    )
