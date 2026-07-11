"""Authored doc-IR pages: the node trees behind ``painted docs`` and the site.

Content lives here — a neutral module — rather than in the CLI dispatch
(``_docs_cli.py``) because TWO consumers read the same trees: the terminal front
door (``painted docs <name>`` via ``doc_lens``) and the publisher
(``painted/publish.py`` via ``to_html``). That shared readership is the doc-IR
thesis (``docs/DOC_IR_DESIGN.md``): one tree, projected per medium, so the docs
cannot drift from the code. A page is authored as code on purpose — its
``Figure`` nodes embed live-rendered Blocks from the real API (doc == demo).

Private module: the pages are painted's own documentation content, not API —
the vocabulary they are written in is public (``core.__all__``, 0.10), the
authored registry is not.
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
                        "complete_via / .completer",
                        "Attach a callable that completes values the parser can't enumerate.",
                        "complete_via(action, fn) is the typed front door; it sets the "
                        "argcomplete-compatible action.completer, which the producer "
                        "invokes with a CompletionContext.",
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
                            "from painted.cli import Candidate, CompletionContext, complete_via\n"
                            "\n"
                            "def complete_branch(ctx: CompletionContext) -> list[Candidate]:\n"
                            "    # ctx.prefix is the partial token; ctx.args is what's already typed.\n"
                            "    return [Candidate(name, subject) for name, subject in recent_branches()]\n"
                            "\n"
                            "def add_args(parser):\n"
                            '    complete_via(parser.add_argument("branch", help="..."), complete_branch)'
                        ),
                    ),
                    Prose(
                        "complete_via attaches the completer in one line and returns the "
                        "argument; it's the typed front door for the argcomplete-style "
                        "action.completer attribute, which still works if you prefer it. "
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
                            '    complete_via(parser.add_argument("--message", help="..."), lambda ctx: [])'
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


def _traceback_gallery() -> Block:
    """A genuine Figure: a real exception rendered by render_traceback.

    The exception is raised and captured inside this function, so every frame is
    in this module — the basenames and line numbers render deterministically,
    and the figure is a real projection of the same renderer install() and
    PaintedHandler mount. SUMMARY zoom shows the frame stack and the chain
    connective without pulling machine-specific source context. Imports are local
    to keep this module off the traceback renderer at import time."""
    from painted import Zoom
    from painted.views import render_traceback

    try:
        try:
            config = {"port": "eight"}
            int(config["port"])
        except ValueError as cause:
            raise RuntimeError("could not start server") from cause
    except RuntimeError as exc:
        return render_traceback(exc, Zoom.SUMMARY, 64)


def diagnostics_doc() -> Doc:
    return Doc(
        title="Diagnostics",
        body=(
            Prose(
                "painted renders the two diagnostic surfaces every program already "
                "produces — log records and uncaught tracebacks — as structured "
                "Blocks disclosed by zoom, not format strings. A log level is a "
                "declared severity; a traceback is a record tree, and capturing it "
                "is the declaration. Both render through the same core the rest of "
                "painted uses, so a diagnostic looks like the rest of your output."
            ),
            Defs(
                (
                    Def(
                        "painted.install()",
                        "Route uncaught exceptions through render_traceback instead of "
                        "the default text hook.",
                        "Sets sys.excepthook; threads=True also sets "
                        "threading.excepthook. KeyboardInterrupt passes through "
                        "untouched.",
                    ),
                    Def(
                        "PaintedHandler(stream=sys.stderr, *, zoom=…)",
                        "A logging.Handler that renders each record to a Block — "
                        "timestamp, severity-styled level, logger, message, extra "
                        "fields, and any exc_info traceback.",
                        "A renderer, not a formatter: setFormatter still shapes the "
                        "message STRING, but the structure stays painted's. Palette and "
                        "color depth are snapshotted at construction so worker-thread "
                        "logs render identically.",
                    ),
                    Def(
                        "render_traceback(exc, zoom, width, *, suppress=(), redact=…)",
                        "An exception (live or a captured TracebackException) as a Block: "
                        "frames on a gutter rail, chains and groups as a tree.",
                        "The gutter encodes one dimension — frame origin (app vs "
                        "suppressed/library). suppress folds matching frames; redact "
                        "masks sensitive local names at FULL zoom.",
                    ),
                )
            ),
            Section(
                "Install",
                body=(
                    Prose(
                        "Two independent opt-ins. Add PaintedHandler to a logger to "
                        "render its records; call install() to catch what escapes. "
                        "Neither is on by default — painted renders diagnostics only "
                        "when you declare it should."
                    ),
                    Code(
                        text=(
                            "import logging, painted\n"
                            "\n"
                            "logging.getLogger().addHandler(painted.PaintedHandler())\n"
                            "painted.install()          # uncaught tracebacks render too"
                        ),
                    ),
                ),
            ),
            Section(
                "Log levels are declared severities",
                body=(
                    Prose(
                        "A record's levelno resolves to the Severity of the greatest "
                        "threshold floor it clears, and Severity drives the palette role "
                        "the row is styled in. The default mapping mutes DEBUG onto INFO "
                        "(the journalctl principle — routine noise stays quiet) and folds "
                        "CRITICAL onto ERROR (the palette's loudest role). Pass your own "
                        "thresholds to change where the lines fall — a custom mapping "
                        "changes the output, or it wouldn't be worth declaring."
                    ),
                    Code(
                        text=(
                            "from painted import PaintedHandler\n"
                            "from painted.views import Severity\n"
                            "\n"
                            "handler = PaintedHandler(thresholds={\n"
                            "    logging.INFO: Severity.INFO,\n"
                            "    logging.WARNING: Severity.WARNING,\n"
                            "    logging.ERROR: Severity.ERROR,\n"
                            "})"
                        ),
                    ),
                ),
            ),
            Section(
                "Tracebacks are record trees",
                body=(
                    Prose(
                        "render_traceback captures a live exception (or renders a "
                        "TracebackException you already captured) and projects it at a "
                        "zoom level: MINIMAL is type + message + the innermost frame on "
                        "one line; SUMMARY adds the frame stack with chains summarized; "
                        "DETAILED adds source with a caret; FULL adds wider source, "
                        "redacted locals, and fully expanded groups. suppress folds the "
                        "frames you didn't write to a single muted line."
                    ),
                    Figure(
                        _traceback_gallery(),
                        caption=(
                            "Live render_traceback output at SUMMARY: a RuntimeError "
                            "caused by a ValueError, the chain connective between them."
                        ),
                    ),
                ),
            ),
            Section(
                "Why this matters",
                min_depth=2,
                body=(
                    Prose(
                        "The default traceback is a wall of text you scan by eye; a log "
                        "line is a format string you re-invent per project. painted "
                        "renders both from the structure already in the data — the "
                        "frame tree, the level, the extra fields — so severity reads at "
                        "a glance, the failing line carries a caret, and a worker "
                        "thread's log looks like the main thread's. Nothing is invented; "
                        "the rendering derives from what was declared."
                    ),
                ),
            ),
            Section(
                "Design note",
                tag="rationale",
                body=(
                    Prose(
                        "The delivery glue lives at the package root, not in painted.cli. "
                        "A log handler and an excepthook are not argv-driven, and the CLI "
                        "layer holds a frozen tripwire — nothing in cli/ may import the "
                        "renderer. Root modules may (the precedent is inplace.py), so "
                        "diagnostics mounts render_traceback there without touching the "
                        "CLI seam. Full design: docs/DIAGNOSTICS_DESIGN.md."
                    ),
                    Prose(
                        "The three surfaces share one substrate. render_traceback's "
                        "locals route through the same shape_lens the inferring path uses "
                        "— hardened here to be cycle-safe and schema-aware, so a cyclic local can't "
                        "crash the error renderer. PaintedHandler composes "
                        "render_traceback for exc_info rather than re-deriving frame "
                        "structure. One hardening, two deliverers."
                    ),
                ),
            ),
        ),
    )


def _prompt_record_gallery() -> Block:
    """A genuine Figure: real record lines from the real declared-rung resolver.

    Runs ``PromptSession.ask()`` against declared prompts with stdin not a
    TTY — the flag/default resolution path every non-interactive run takes —
    and captures exactly what the resolver writes to stderr. No fabricated
    text: this is DECLARED-rung output, byte for byte. Imports are local to
    keep this module off the prompt resolver at import time."""
    import contextlib
    import io

    from painted.cli import Confirm, Select
    from painted.cli.prompts import PromptSession

    prompts = [
        Confirm("force", "Force overwrite?", default=False),
        Select("scope", "Which store?", values=("local", "config", "all"), default="local"),
    ]
    session = PromptSession(prompts, {}, stdin_tty=False, stderr_tty=False)
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        session.ask("force")
        session.ask("scope")
    lines = [line for line in captured.getvalue().splitlines() if line]
    return join_vertical(*(Block.text(line, Style()) for line in lines))


def _prompt_refusal_gallery() -> Block:
    """A genuine Figure: the real ``ContractError`` text a script sees with no
    flag and no default at a non-TTY — the diagram's third column, an honest
    refusal that names the flag because the flag provably exists."""
    from painted.cli import Confirm
    from painted.cli.prompts import PromptSession

    session = PromptSession(
        [Confirm("overwrite", "Overwrite existing files?")], {}, stdin_tty=False
    )
    try:
        session.ask("overwrite")
        message = ""
    except Exception as exc:
        message = str(exc)
    return Block.text(message, Style(fg="red"))


def prompts_doc() -> Doc:
    return Doc(
        title="Inline prompts",
        body=(
            Prose(
                "A prompt is an input, and painted's CLI grammar already has an "
                "input channel: declared flags. --force and 'Are you sure? "
                "[y/N]' are the same declaration at different fidelities — one "
                "resolves from argv, one resolves interactively at a TTY. A "
                "declared prompt is the parser's fourth reflection, after "
                "parse, help, and completion: one declaration generates a "
                "flag, a rendered question, an honest refusal, and completion "
                "of its answer values."
            ),
            Defs(
                (
                    Def(
                        "Confirm(name, question, default=, danger=)",
                        "A yes/no question — the two-element domain.",
                        "Generates --name/--no-name; danger=HARD swaps the "
                        "pair for a value-carrying --name <challenge> and a "
                        "bare --no-name.",
                    ),
                    Def(
                        "Select(name, question, values=|vocabulary=, default=)",
                        "A choice over an enumerable domain.",
                        "values= is an open tuple; vocabulary= is a declared "
                        "Vocabulary whose members are the legal values — the "
                        "mark channel styles them wherever the answer renders.",
                    ),
                    Def(
                        "Input(name, question, parse=, completer=, default=)",
                        "A free-text question over an open domain.",
                        "parse raises to reject; its return value becomes the "
                        "answer. completer= rides the third reflection; "
                        "without one the flag falls back to file/dir "
                        "completion.",
                    ),
                    Def(
                        "ctx.ask(name_or_prompt)",
                        "The single door an answer comes through — memoized, "
                        "fires at most once per run.",
                        "A Tag's answer lives in ctx.args; a Prompt's answer "
                        "lives behind ctx.ask — never both, so nothing "
                        "silently bypasses the resolution ladder.",
                    ),
                    Def(
                        "--no-input",
                        "One framework flag: every prompt resolves as if "
                        "stdin were not a terminal.",
                        "CI scripts declare their nature instead of relying on TTY detection.",
                    ),
                )
            ),
            Section(
                "What you get for free",
                body=(
                    Prose(
                        "Declare a prompt beside your tags and it generates "
                        "its own flag, its own -h entry, and completion of "
                        "its answer values — with zero prompt-specific code "
                        "in any of the three. At a TTY, the same declaration "
                        "renders and reads an answer; everywhere else, it "
                        "resolves from the flag or the declared default and "
                        "leaves one line of proof."
                    ),
                    Figure(
                        _prompt_record_gallery(),
                        caption=(
                            "Real record lines from a non-interactive run: a "
                            "declared default resolving for Confirm and "
                            "Select, each marked (default) — the transcript's "
                            "proof that nobody was asked."
                        ),
                    ),
                ),
            ),
            Section(
                "The resolution ladder",
                body=(
                    Prose(
                        "Every prompt resolves the same four-step ladder, "
                        "declared or asked at runtime: the argv flag first "
                        "(it's already visible in the invocation), then an "
                        "interactive prompt at a TTY, then the declared "
                        "default, then an honest refusal. A script without a "
                        "flag or a default never hangs and never invents an "
                        "answer — it gets a ContractError naming the exact "
                        "flag that would resolve it."
                    ),
                    Figure(
                        _prompt_refusal_gallery(),
                        caption=(
                            "The real refusal text: no flag, no default, "
                            "stdin not a terminal — the error names the flag, "
                            "because the flag provably exists."
                        ),
                    ),
                ),
            ),
            Section(
                "Danger tiers",
                body=(
                    Defs(
                        (
                            Def(
                                "Danger.NONE",
                                "y/N — Enter accepts the default.",
                                "The only tier that may carry default=.",
                            ),
                            Def(
                                "Danger.SOFT",
                                "y/N — no Enter-default, an explicit key.",
                                '"Did you mean to proceed?" — accidental Enter, muscle memory.',
                            ),
                            Def(
                                "Danger.HARD",
                                "Type the declared challenge= to proceed.",
                                '"Do you know what you\'re aiming at?" — '
                                "Confirm-only; anything but an exact match "
                                "resolves False, fail-closed.",
                            ),
                        )
                    ),
                ),
            ),
            Section(
                "Why this matters",
                min_depth=2,
                body=(
                    Prose(
                        "The prompt UI draws on stderr, never stdout, so "
                        "`tool --json | jq` stays parseable even when the "
                        "tool asked a question mid-run. And a prompt never "
                        "forces an environment rewrite: it renders at "
                        "whatever rung the terminal supports — a raw-mode "
                        "cursor at a real TTY, a cooked-mode y/n on a dumb "
                        "terminal or screen reader, or no interaction at all "
                        "in a script — and every rung answers the same "
                        "question the same way."
                    ),
                ),
            ),
            Section(
                "Design note",
                tag="rationale",
                body=(
                    Prose(
                        "clig.dev names 'conversation as the norm' as a tenet "
                        "no standalone prompt library can fully honor, "
                        "because an honest refusal must name the flag that "
                        "answers the question — and the flag lives in the "
                        "application's parser. painted is a prompt library "
                        "and a CLI framework in one package, so it holds both "
                        "ends."
                    ),
                    Prose(
                        "default= fires on absence of a terminal, not on EOF "
                        "— a deliberate break from the ecosystem, where 'the "
                        "value on bare Enter' and 'the value when nobody "
                        "answers' are conflated. EOF (Ctrl-D) and Ctrl-C take "
                        "the identical abort path at every rung: never an "
                        "answer, never a silent fall-through to the default."
                    ),
                    Prose("Full design: docs/PROMPTS_DESIGN.md."),
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
    "diagnostics": DocEntry(
        "diagnostics",
        "Diagnostics: log records and tracebacks rendered as structured Blocks",
        diagnostics_doc,
    ),
    "prompts": DocEntry(
        "prompts",
        "Inline prompts: declared questions that generate a flag, a render, and completion",
        prompts_doc,
    ),
}
