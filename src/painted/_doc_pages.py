"""Authored doc-IR pages: the node trees behind ``painted docs`` and the site.

Content lives here — a neutral module — rather than in the CLI dispatch
(``_docs_cli.py``) because TWO consumers read the same trees: the terminal front
door (``painted docs <name>`` via ``doc_lens``) and the site publisher
(``tools/doc_publish.py`` via ``to_html``). That shared readership is the doc-IR
thesis (``docs/DOC_IR_DESIGN.md``): one tree, projected per medium, so the docs
cannot drift from the code. A page is authored as code on purpose — its
``Figure`` nodes embed live-rendered Blocks from the real API (doc == demo).

Private module: the node vocabulary is still provisional (not in
``core.__all__``), so the pages that use it stay out of the public surface too.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from painted import Block, Style, join_vertical
from painted.core.doc import (
    Code,
    Def,
    Defs,
    Doc,
    Figure,
    Prose,
    Section,
)


@dataclass(frozen=True)
class DocEntry:
    name: str
    description: str
    build: Callable[[], Doc]


# ---------------------------------------------------------------------------
# Pages (authored as code — the whole point)
# ---------------------------------------------------------------------------


def _style_gallery() -> Block:
    """A genuine Figure: Style attributes rendered live from the real API."""
    return join_vertical(
        Block.text("bold", Style(bold=True)),
        Block.text("red", Style(fg="red")),
        Block.text("green", Style(fg="green")),
        Block.text("blue", Style(fg="blue")),
        Block.text("dim italic", Style(dim=True, italic=True)),
        Block.text("reverse cyan", Style(fg="cyan", reverse=True)),
    )


def primitives_doc() -> Doc:
    return Doc(
        title="Primitives and Blocks",
        body=(
            Prose(
                "painted is built from a small set of immutable render-layer value "
                "types. These are the inputs to every higher-level feature — "
                "composition, buffers, the TUI, widgets."
            ),
            Defs(
                (
                    Def("Primitives", "Style, Cell, Span, Line"),
                    Def("Rectangles", "Block"),
                )
            ),
            Section(
                "Style",
                body=(
                    Prose(
                        "Style is an immutable bundle of attributes — colors plus "
                        "bold/italic/underline/reverse/dim. Styles combine via "
                        "merge(), where the overlay wins."
                    ),
                    Code(
                        text="base = Style(fg='blue', bold=True)\nmerged = base.merge(Style(italic=True))"
                    ),
                    Figure(_style_gallery(), caption="Style attributes, rendered live"),
                ),
            ),
            Section(
                "Cell",
                body=(
                    Prose(
                        "Cell is the atom: one character plus one Style. Most code "
                        "manipulates Blocks rather than individual cells."
                    ),
                ),
            ),
            Section(
                "Span and Line",
                body=(
                    Prose(
                        "Span is text plus Style, measured in display columns "
                        "(wide-char aware). A Line is a tuple of spans that paints "
                        "into a buffer or converts to a Block."
                    ),
                ),
            ),
            Section(
                "Why this matters",
                min_depth=2,
                body=(
                    Prose(
                        "painted pushes complexity up the stack: these immutable "
                        "values are safe to share and cache, so higher-level systems "
                        "treat rendering as a pure transformation — state to blocks."
                    ),
                ),
            ),
            Section(
                "Design note",
                tag="rationale",
                body=(
                    Prose(
                        "This page is itself a doc-IR node tree. The terminal you are "
                        "reading it in and the docs site render the same tree through "
                        "different projectors — so the docs cannot drift from the code."
                    ),
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Guides — the consumer ladder, one page per rung (task-shaped)
# ---------------------------------------------------------------------------


def _show_figure() -> Block:
    from painted.views import shape_lens

    return shape_lens({"status": "ok", "items": 42, "regions": ["us", "eu"]}, 1, 44)


def show_guide_doc() -> Doc:
    return Doc(
        title="Guide 0 — Display data",
        body=(
            Prose(
                "You have data and want it to look decent in a terminal. "
                "show() is the whole API at this rung: it auto-dispatches by "
                "data shape — dict to key-value, list to items, numeric to "
                "chart, nested to tree."
            ),
            Code(text='from painted import show\n\nshow({"status": "ok", "items": 42})'),
            Figure(_show_figure(), caption="shape_lens output — what show() prints"),
            Prose(
                "show(data, zoom=Zoom.DETAILED) asks for more, "
                "show(data, zoom=Zoom.MINIMAL) for a one-liner. That zoom "
                "argument is the first rung of the disclosure ladder — the "
                "same axis -q/-v will control once you have a CLI.",
                min_depth=1,
            ),
            Section(
                "Why start here",
                tag="rationale",
                body=(
                    Prose(
                        "Every later rung is additive. A show() call you outgrow "
                        "becomes a render function without rewriting what it "
                        "displays — the no-framework-switch invariant."
                    ),
                ),
            ),
        ),
    )


def _compose_figure() -> Block:
    from painted import border, join_horizontal, pad

    left = Block.text("Name: Alice", Style(bold=True))
    right = Block.text("Score: 98", Style(fg="green"))
    row = join_horizontal(left, Block.text("  ", Style()), right)
    return border(pad(row, left=1, right=1))


def compose_guide_doc() -> Doc:
    return Doc(
        title="Guide 1 — Compose layout",
        body=(
            Prose(
                "You need custom layout: columns, borders, padding. The unit "
                "of composition is Block — an immutable rectangle of styled "
                "cells. Every operation takes Blocks and returns a new Block."
            ),
            Code(
                text=(
                    "from painted import Block, Style, join_horizontal, border, pad, print_block\n"
                    "\n"
                    'left = Block.text("Name: Alice", Style(bold=True))\n'
                    'right = Block.text("Score: 98", Style(fg="green"))\n'
                    'row = join_horizontal(left, Block.text("  ", Style()), right)\n'
                    "print_block(border(pad(row, left=1, right=1)))"
                )
            ),
            Figure(_compose_figure(), caption="The composed row, rendered live"),
            Defs(
                (
                    Def("join_vertical / join_horizontal", "stack or abut Blocks"),
                    Def("border / pad / truncate", "wrap, inset, or clip a Block"),
                    Def("Block.text / Block.empty", "construct from a string or blank"),
                )
            ),
            Prose(
                "Width is a contract: pass width= and it is exact (clip or pad; "
                "wrap=Wrap.CHAR/WORD to reflow); omit it for natural sizing. "
                "Display width is wcwidth-measured, never len().",
                min_depth=1,
            ),
            Section(
                "Why immutability",
                tag="rationale",
                body=(
                    Prose(
                        "Blocks are frozen so composition is a pure expression "
                        "tree — safe to share, cache, and diff. The TUI's "
                        "changed-cells-only rendering falls out of this."
                    ),
                ),
            ),
        ),
    )


def _cli_figures() -> tuple[Block, Block]:
    quiet = Block.text("ok · 42 items", Style())
    verbose = join_vertical(
        Block.text("status   ok", Style(bold=True)),
        Block.text("items    42", Style()),
        Block.text("regions  us, eu", Style()),
    )
    return quiet, verbose


def cli_guide_doc() -> Doc:
    quiet, verbose = _cli_figures()
    return Doc(
        title="Guide 2 — A CLI tool",
        body=(
            Prose(
                "You need -v/-q, --json, pipe detection, and help text. Write "
                "two functions — render(ctx, data) -> Block and fetch() -> data "
                "— and run_cli owns the rest: flag parsing, TTY detection, "
                "mode dispatch."
            ),
            Code(
                text=(
                    "from painted import run_cli, CliContext, Block\n"
                    "\n"
                    "def render(ctx: CliContext, data: dict) -> Block:\n"
                    "    return status_view(data, zoom=ctx.zoom, width=ctx.width)\n"
                    "\n"
                    "run_cli(sys.argv[1:], render=render, fetch=fetch)"
                )
            ),
            Figure(quiet, caption="the same render fn at -q ..."),
            Figure(verbose, caption="... and at -v — one function, two depths"),
            Section(
                "The disclosure ladder",
                body=(
                    Prose("Each rung is additive; climbing never rewrites the rung below."),
                    Defs(
                        (
                            Def("depth", "gate detail on ctx.zoom — -q/-v/-vv come free"),
                            Def(
                                "tags",
                                'declare Tag("thinking", "...", implied_at=3); gate on '
                                'ctx.fidelity.shows("thinking") — the flag, help entry, '
                                "and implication are generated",
                            ),
                            Def(
                                "budgets",
                                "pass budgets=True; read fidelity.chars/.lines — only "
                                "now do --max-chars/--max-lines exist",
                            ),
                        )
                    ),
                    Prose(
                        "Depth is anonymous detail; a tag is a named facet a user "
                        "would ask for at low depth (--thinking at -q). The honesty "
                        "rule: a flag exists only because a capability was declared, "
                        "and a declared capability must change output.",
                        min_depth=1,
                    ),
                ),
            ),
            Prose(
                "The other two axes resolve without you: Format (--json/--plain, "
                "ANSI for TTY, PLAIN for pipes) and Mode (--static/--live, AUTO "
                "from TTY state). depth_aliases={'brief': 0, 'full': 3} adds "
                "app-local depth spellings.",
                min_depth=1,
            ),
        ),
    )


def _live_figure() -> Block:
    from painted.views import ProgressState, progress_bar, sparkline

    bar = progress_bar(ProgressState(value=0.62), 30)
    spark = sparkline([3, 5, 4, 8, 6, 9, 7, 12, 10, 14], 20)
    return join_vertical(_label_row("sync  ", bar), _label_row("rate  ", spark))


def _label_row(label: str, block: Block) -> Block:
    from painted import join_horizontal

    return join_horizontal(Block.text(label, Style(dim=True)), block)


def live_guide_doc() -> Doc:
    return Doc(
        title="Guide 3 — Live updates",
        body=(
            Prose(
                "You need progress that moves. Add fetch_stream — an async "
                "iterator of states — and run_cli renders each one in place. "
                "The same render function you already wrote; delivery is the "
                "only thing that changes."
            ),
            Code(
                text=(
                    "async def fetch_stream():\n"
                    "    async for tick in source():\n"
                    "        yield tick\n"
                    "\n"
                    "run_cli(sys.argv[1:], render=render, fetch=fetch,\n"
                    "        fetch_stream=fetch_stream)"
                )
            ),
            Figure(_live_figure(), caption="One live frame — progress and a sparkline"),
            Defs(
                (
                    Def("inplace", "default delivery: cursor-rewrite, scrollback preserved"),
                    Def(
                        "surface",
                        'live_delivery="surface": alt-screen, diff-rendered — for '
                        "sustained animation",
                    ),
                )
            ),
            Prose(
                "Both tiers deposit a final frame into scrollback on exit, and "
                "--static (or piping) collapses to a single render of the last "
                "state. run_cli(live_meter=True) overlays a cost gauge: measured "
                "frame cost against the delivery budget.",
                min_depth=1,
            ),
            Section(
                "Why two tiers",
                tag="rationale",
                body=(
                    Prose(
                        "In-place rewriting respects the shell session (your "
                        "history stays); alt-screen owns the terminal for "
                        "flicker-free animation. They share one contract, so a "
                        "demo graduates from one to the other by changing a "
                        "keyword, not its render code."
                    ),
                ),
            ),
        ),
    )


def _tui_figure() -> Block:
    from painted import border, pad

    dialog = border(
        pad(Block.text("Quit without saving? [y/n]", Style(bold=True)), left=1, right=1)
    )
    backdrop = join_vertical(
        Block.text("item 1   ready", Style(dim=True)),
        Block.text("item 2   ready", Style(dim=True)),
        Block.text("item 3   running", Style(dim=True)),
    )
    return join_vertical(backdrop, dialog)


def tui_guide_doc() -> Doc:
    return Doc(
        title="Guide 4 — Interactive TUI",
        body=(
            Prose(
                "You need keyboard input, full-screen, modal dialogs. Most "
                "tools don't — exhaust the earlier rungs first. When you do: "
                "subclass Surface, override render() and on_key(), call run()."
            ),
            Code(
                text=(
                    "from painted.tui import Surface\n"
                    "\n"
                    "class MyApp(Surface):\n"
                    "    def render(self, buf):\n"
                    '        Block.text(f"Count: {self.count}", Style()).paint(buf, 0, 0)\n'
                    "\n"
                    "    def on_key(self, key):\n"
                    '        if key == "q":\n'
                    "            self.quit()"
                )
            ),
            Figure(_tui_figure(), caption="A modal layer over a base view"),
            Defs(
                (
                    Def("Surface", "alt-screen loop: keyboard in, diff-rendered frames out"),
                    Def("Layer", "modal stack — top layer handles keys, all render"),
                    Def("Focus / Search", "navigation ring and query filtering"),
                    Def("TestSurface", "replay keys, capture frames — no terminal needed"),
                )
            ),
            Prose(
                "State stays yours: Surface subclasses hold mutable app state, "
                "but rendering is still Blocks painted into a buffer — the same "
                "compose vocabulary from Guide 1. Emit is the feedback boundary: "
                "the Surface reports observations upstream instead of mutating "
                "the world.",
                min_depth=1,
            ),
            Section(
                "Testing is the design",
                tag="rationale",
                body=(
                    Prose(
                        "TestSurface(app, input_queue) replays keys against a "
                        "fixed-size buffer and captures every frame. If your app "
                        "is hard to drive that way, its state is hiding somewhere "
                        "rendering can't see — fix the app, not the test."
                    ),
                ),
            ),
        ),
    )


DOCS: dict[str, DocEntry] = {
    "primitives": DocEntry(
        "primitives",
        "The render-layer value types: Style, Cell, Span, Line, Block",
        primitives_doc,
    ),
    "show": DocEntry(
        "show",
        "Guide 0 — display data with show(), zero ceremony",
        show_guide_doc,
    ),
    "compose": DocEntry(
        "compose",
        "Guide 1 — custom layout with Blocks: join, border, pad",
        compose_guide_doc,
    ),
    "cli": DocEntry(
        "cli",
        "Guide 2 — a CLI tool: run_cli and the disclosure ladder",
        cli_guide_doc,
    ),
    "live": DocEntry(
        "live",
        "Guide 3 — live updates: fetch_stream and the two delivery tiers",
        live_guide_doc,
    ),
    "tui": DocEntry(
        "tui",
        "Guide 4 — interactive TUI: Surface, Layer, TestSurface",
        tui_guide_doc,
    ),
}
