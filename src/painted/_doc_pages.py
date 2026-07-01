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

from painted import Block, Style, border, join_horizontal, join_vertical, pad
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


def _candidate_gallery() -> Block:
    """A genuine Figure: real completion candidates from the real producer.

    Runs ``complete_args`` over a tiny parser at word-context with prefix ``--``,
    so the rows are exactly what pressing TAB would offer — a consumer's two
    declared flags plus the framework flags every painted CLI gets free, each
    with the help text that doubles as its zsh description. No post-filtering, so
    the figure cannot show a candidate the engine wouldn't. Imports are local to
    keep this module off the completion producer at import time."""
    import argparse

    from painted.cli import OutputMode
    from painted.cli.complete import complete_args
    from painted.cli.types import build_parser

    def add_args(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--since", help="only rows after this time")
        parser.add_argument("--kind", choices=("fact", "spec"), help="filter by kind")

    parser = build_parser(add_args=add_args, modes={OutputMode.STATIC})
    cands = complete_args(parser, [], "--")
    col = max(len(c.value) for c in cands) + 2
    rows = [
        join_horizontal(
            Block.text(c.value, Style(fg="cyan")),
            Block.text(" " * (col - len(c.value)) + c.description, Style(dim=True)),
        )
        for c in cands
    ]
    return join_vertical(*rows)


def _reflections_diagram() -> Block:
    """A genuine Figure: the one-walk-three-reflections architecture as a Block.

    A labeled diagram, honest as architecture (not a mock of shell behavior):
    one trunk feeds three projectors, exactly as the code does."""

    def box(label: str, sub: str) -> Block:
        return border(
            pad(
                join_vertical(
                    Block.text(label, Style(bold=True)),
                    Block.text(sub, Style(dim=True)),
                ),
                left=1,
                right=1,
            )
        )

    trunk = Block.text("build_parser → walk_args → ArgSpec", Style(fg="cyan"))
    reflections = join_horizontal(
        box("parse", "→ Namespace"),
        Block.text("  ", Style()),
        box("help", "→ Def"),
        Block.text("  ", Style()),
        box("complete", "→ Candidate"),
    )
    return join_vertical(trunk, Block.text(" ", Style()), reflections)


def completion_doc() -> Doc:
    return Doc(
        title="Shell completion",
        body=(
            Prose(
                "Press TAB and your painted CLI completes itself — command names, "
                "flags, their choices, and the dynamic values you hang on an "
                "argument. Completion is the third reflection of your argparse "
                "parser, after parse and help: the same declarations that drive "
                "-h drive TAB, so what completes is exactly what the parser "
                "accepts — never a flag it would reject."
            ),
            Defs(
                (
                    Def(
                        "yourapp completion zsh|bash",
                        "Print the shell glue to install — completion is opt-in setup "
                        "you run once.",
                        "run_app adds this command for you; painted prints the "
                        "function, you install it, painted never edits a dotfile.",
                    ),
                    Def(
                        "Candidate(value, description)",
                        "One completion result. The description shows beside the value in zsh.",
                        "A bare str candidate is normalized to Candidate(value, ''); "
                        "descriptions are painted's edge over a names-only completer.",
                    ),
                    Def(
                        ".completer",
                        "A callable you hang on an argument to complete values the "
                        "parser can't enumerate.",
                        "action.completer = fn — the argcomplete-compatible attribute; "
                        "the producer invokes it with a CompletionContext.",
                    ),
                    Def(
                        "CompletionContext",
                        "What a completer sees: the args typed so far (ctx.args) plus "
                        "the prefix under the cursor.",
                        "ctx.args is the same read-only view render/fetch receive, so a "
                        "completer can scope candidates to what's already on the line.",
                    ),
                )
            ),
            Section(
                "Install",
                body=(
                    Prose(
                        "Completion is opt-in: painted prints the shell glue and you "
                        "install it once. Nothing is edited on your behalf — the glue "
                        "is a small function that calls your program back for "
                        "candidates as you type."
                    ),
                    Code(
                        text=(
                            "# zsh — save the function on your $fpath, then restart the shell\n"
                            'yourapp completion zsh > "${fpath[1]}/_yourapp"'
                        ),
                        lang="bash",
                    ),
                    Code(
                        text=(
                            "# bash — source the function from your ~/.bashrc\n"
                            'eval "$(yourapp completion bash)"'
                        ),
                        lang="bash",
                    ),
                    Prose(
                        "Or let painted write the file for you: yourapp completion "
                        "--install detects your shell from $SHELL and drops the glue in "
                        "your completions directory (--dry-run previews it first). It "
                        "writes only a file painted owns and prints the one line to add "
                        "if your shell isn't already looking there — it never edits a "
                        "dotfile on your behalf."
                    ),
                    Prose(
                        "A multi-command app built with run_app gets the completion "
                        "command for free — yourapp completion <TAB> even completes its "
                        "own shell argument (zsh, bash). The same machinery drives a "
                        "single-command run_cli tool: once the glue is installed, TAB "
                        "completes its flags too."
                    ),
                ),
            ),
            Section(
                "What you get for free",
                body=(
                    Prose(
                        "Every command name (with its one-line summary), every flag "
                        "your parser declares, and every static choice complete with no "
                        "extra work — they are already in the parser that powers -h. In "
                        "zsh, each candidate's help text rides along as a description; "
                        "bash shows the values alone."
                    ),
                    Figure(
                        _candidate_gallery(),
                        caption=(
                            "Live producer output for `yourapp --<TAB>`: your declared "
                            "flags plus the framework flags you get free, each with its "
                            "description."
                        ),
                    ),
                ),
            ),
            Section(
                "Dynamic values: the .completer seam",
                body=(
                    Prose(
                        "Static choices cover the values you know at parse time. For "
                        "values that are runtime data — a record id, a branch name, a "
                        "vertex — hang a completer on the argument. It receives a "
                        "CompletionContext and returns bare strings or described "
                        "Candidates; painted normalizes either and never invents a "
                        "result the completer didn't yield."
                    ),
                    Code(
                        text=(
                            "from painted.cli import Candidate, CompletionContext\n"
                            "\n"
                            "def complete_branch(ctx: CompletionContext) -> list[Candidate]:\n"
                            "    # ctx.prefix is the partial token; ctx.args is what's already typed.\n"
                            "    return [Candidate(name, subject) for name, subject in recent_branches()]\n"
                            "\n"
                            "def add_args(parser):\n"
                            '    arg = parser.add_argument("branch", help="branch to check out")\n'
                            "    arg.completer = complete_branch   # the .completer seam"
                        ),
                    ),
                    Prose(
                        "Return Candidate(value, description) to show context in zsh, or "
                        "a bare string when the value speaks for itself. Scope to the "
                        "line via ctx.args — a --to completer can narrow to branches "
                        "that aren't the --from already typed. A completer that raises "
                        "degrades to no candidates rather than spilling a traceback into "
                        "the shell."
                    ),
                ),
            ),
            Section(
                "File and directory completion",
                body=(
                    Prose(
                        "An argument with no choices and no completer is an open slot — "
                        "a free-text value the parser can't enumerate. painted "
                        "classifies it and lets the shell complete paths there (zsh "
                        "_files, bash's default), so ~ expansion, hidden-file rules, and "
                        "your own zstyle all keep working. painted never reads the disk; "
                        "the shell already knows how. To take a free-text value with no "
                        "path fallback, give the argument a completer that returns an "
                        "empty list — the explicit opt-out."
                    ),
                    Code(
                        text=(
                            "def add_args(parser):\n"
                            "    # open slot -> shell completes paths here\n"
                            '    parser.add_argument("path", help="file to read")\n'
                            "    # free text, no file fallback -> explicit opt-out\n"
                            '    msg = parser.add_argument("--message", help="commit message")\n'
                            "    msg.completer = lambda ctx: []"
                        ),
                    ),
                ),
            ),
            Section(
                "Why this matters",
                min_depth=2,
                body=(
                    Prose(
                        "Pressing TAB imports none of painted's renderer and runs none "
                        "of your fetch — completion answers from the parser's "
                        "declarations alone. So completion is instant no matter how "
                        "expensive your program is to run, and typing TAB can never "
                        "trigger the work your command would do. That guarantee is "
                        "structural, not a promise: the completion path physically "
                        "cannot reach the rendering code."
                    ),
                ),
            ),
            Section(
                "Design note",
                tag="rationale",
                body=(
                    Prose(
                        "Completion is the third reflection of one argparse parser. A "
                        "single walk over the parser's actions (walk_args → ArgSpec) "
                        "feeds both projectors: help renders each spec to a Def, "
                        "completion renders it to a Candidate. There is no second source "
                        "of truth to drift — the flag you see under -h is the flag that "
                        "completes."
                    ),
                    Prose(
                        "The honesty rule governs every candidate: it exists only "
                        "because the parser, or a declared .completer, produced it. "
                        "painted under-lists rather than suggest a flag the parser would "
                        "reject. A candidate you can't act on is worse than one that's "
                        "missing."
                    ),
                    Prose(
                        "The render-free guarantee is enforced by construction. The "
                        "producer, the transport, and the walk import only stdlib and "
                        "each other; an AppCommand is read by attribute, never "
                        "constructed. Pressing TAB cannot pull core.block or core.doc — "
                        "the no-renderer-on-TAB property is a structural fact the module "
                        "boundaries keep true."
                    ),
                    Prose(
                        "Placement in the ecosystem is deliberate and honest. The "
                        ".completer attribute is the argcomplete convention, so you "
                        "attach a completer the same way — though painted calls it with "
                        "a single CompletionContext, so the function body differs. What "
                        "painted adds is the render-free promise and zsh descriptions "
                        "sourced from the same help text — distinct value, not a "
                        "reimplementation. Full design: docs/COMPLETION_DESIGN.md."
                    ),
                    Figure(
                        _reflections_diagram(),
                        caption=(
                            "One walk, three reflections: build_parser → walk_args → "
                            "ArgSpec, projected to parse, help, and completion."
                        ),
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
    "completion": DocEntry(
        "completion",
        "Shell completion: TAB completes commands, flags, choices, and dynamic values",
        completion_doc,
    ),
}
