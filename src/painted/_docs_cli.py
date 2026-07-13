"""Docs command: render in-code documents to the terminal via the doc lens.

The terminal front door for the doc-IR (``docs/DOC_IR_DESIGN.md``). The pages
themselves live in ``_doc_pages.py`` — authored node trees shared with the site
publisher — and render through ``run_cli``, so ``-v``/``-vv`` map to
``Fidelity.depth`` and each page's tagged layers surface as declared flags:
``--rationale`` exists exactly on pages that have rationale nodes. (The generic
``--show TAG`` spelling retired with the declaration grammar — one spelling per
facet; see docs/FIDELITY_DESIGN.md §7d.) This module is dispatch only.

Render one: ``painted docs primitives -v --rationale``.
"""

from __future__ import annotations

from painted import Block, Fidelity, Style, join_vertical, print_block, run_cli
from painted.cli import OutputMode, Tag
from painted.core.doc import Doc, Node, Section, doc_lens
from painted._doc_pages import DOCS


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _collect_tags(doc: Doc) -> list[Tag]:
    """The page's tagged layers as declarations — the doc is built before
    run_cli, so its node tags are the flag surface."""
    names: set[str] = set()

    def walk(nodes: tuple[Node, ...]) -> None:
        for node in nodes:
            if node.tag is not None:
                names.add(node.tag)
            if isinstance(node, Section):
                walk(node.body)

    walk(doc.body)
    return [Tag(name, f"Reveal the {name} layer") for name in sorted(names)]


def list_docs(_args: list[str]) -> int:
    rows = [Block.text("Available docs", Style(bold=True)), Block.text(" ", Style())]
    for entry in DOCS.values():
        rows.append(Block.text(f"  {entry.name:<14}{entry.description}", Style()))
    rows.append(Block.text(" ", Style()))
    rows.append(
        Block.text(
            "Run painted docs <name> [-v|-vv]; each page's layers appear in its -h",
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

    def renderer(d: Doc, fidelity: Fidelity, width: int | None) -> Block:
        return doc_lens(d, fidelity=fidelity, width=width)

    return run_cli(
        args,
        renderer=renderer,
        fetch=lambda: doc,
        default_mode=OutputMode.STATIC,
        description=entry.description,
        prog=f"painted docs {name}",
        tags=_collect_tags(doc),
    )
