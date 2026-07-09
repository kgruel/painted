"""Help as a doc-IR document.

Help *is* a document — a title, a description, a definition list of the command's
own args, and the framework's option groups. So it is built as a ``Doc`` node tree
(``core/doc.py``) and rendered through ``doc_lens``, the same projector the
``painted docs`` command uses. There is no bespoke help renderer: the four help
tiers (compact names → expanded columns → +detail) fall out of the doc-IR
disclosure tier ``eff = depth - min_depth`` (see the doc lens module docstring).

What this dissolves, relative to the old hand-rolled renderer:

* ``HelpData`` / ``HelpGroup`` / ``HelpFlag`` → ``Doc`` / ``Section`` / ``Def``.
* ``help_args_to_flags`` (which dropped ``short`` and jammed ``default`` into a
  string) → ``_args_to_defs``, which keeps the whole term intact.
* the ``min_zoom`` single-int shadow of three-axis ``Fidelity`` → ``min_depth`` +
  the cascade (a group consumes its ``min_depth`` and passes the rest down).
* the ``use_ansi`` bool jammed into the render signature → a Format concern; the
  writer strips styles for plain output, so the doc is always built styled.

``HelpArg`` (the authoring DTO for pre-parsed command args) and ``scan_help_args``
(the quick arg pre-scan) survive — they are inputs to help, not the renderer.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..core.zoom import Zoom
from ..core.doc import Def, Defs, Doc, Node, Prose, Section
from .types import Format, Tag, depth_alias_help

if TYPE_CHECKING:
    from .prompts import Prompt


@dataclass(frozen=True)
class HelpArg:
    """Describes a command argument for help rendering.

    For commands that pre-parse their own args before calling run_cli,
    use this to describe those args so they appear in --help output.
    """

    name: str  # "--since" or "vertex"
    description: str = ""
    default: str | None = None
    positional: bool = False


# =============================================================================
# Arg → Def adapters (term kept intact — no lossy downcast)
# =============================================================================


def _arg_def(arg: HelpArg) -> Def:
    """A pre-parsed command arg as a Def. ``default`` becomes a summary suffix."""
    summary = arg.description
    if arg.default is not None:
        suffix = f"(default: {arg.default})"
        summary = f"{summary} {suffix}" if summary else suffix
    return Def(term=arg.name, summary=summary)


def _add_args_defs(add_args_fn: Callable[[argparse.ArgumentParser], None]) -> list[Def]:
    """Introspect an add_args callback into Defs via the shared parser walk —
    the help projection of ArgSpec (completion projects the same walk to
    Candidates). Each option's full term ("-s, --since") is kept intact."""
    from ._argwalk import walk_args

    parser = argparse.ArgumentParser(add_help=False)
    add_args_fn(parser)
    return [Def(term=spec.term, summary=spec.help) for spec in walk_args(parser)]


def _prompts_defs(prompts: Sequence[Prompt[Any]]) -> list[Def]:
    """Declared prompts as Defs — the help projection of the same ArgSpec walk
    completion projects to Candidates (the one-walk principle, extended to the
    fourth reflection, docs/PROMPTS_DESIGN.md §12 step 4). Mirrors
    ``_add_args_defs`` exactly: register the real flag(s) on a throwaway
    parser via ``Prompt.add_to_parser`` — the same call ``build_parser`` makes
    for the live parser — then walk it, so a prompt's help text (and HARD's
    two-row asymmetry: a value-carrying yes, a bare no) is read off the one
    place it's authored, never re-described here."""
    from ._argwalk import walk_args

    parser = argparse.ArgumentParser(add_help=False)
    for prompt in prompts:
        prompt.add_to_parser(parser)
    return [Def(term=spec.term, summary=spec.help) for spec in walk_args(parser)]


def command_defs(
    help_args: Sequence[HelpArg] | None,
    add_args_fn: Callable[[argparse.ArgumentParser], None] | None,
) -> tuple[Def, ...]:
    """The command's own args as Defs, from declared HelpArgs and/or add_args.

    Public so the sibling app_runner can build subcommand help from the same
    adapter (run_cli and run_app share one HelpArg → Def path)."""
    defs: list[Def] = []
    if help_args is not None:
        defs.extend(_arg_def(a) for a in help_args)
    if add_args_fn is not None:
        defs.extend(_add_args_defs(add_args_fn))
    return tuple(defs)


# =============================================================================
# Framework option sections (shared by run_cli and run_app)
# =============================================================================


def _flag(short: str | None, long: str | None, summary: str, detail: str | None = None) -> Def:
    term = ", ".join(p for p in (short, long) if p)
    return Def(term=term, summary=summary, detail=detail)


def _group(
    heading: str, hint: str, detail: str | None, flags: tuple[Def, ...], depth: int
) -> Section:
    """A framework option group. ``detail`` is a Prose revealed at the group's
    own tier 2 (``min_depth=2`` relative to the cascaded body depth)."""
    body: list[Node] = []
    if detail:
        body.append(Prose(detail, min_depth=2))
    body.append(Defs(flags))
    return Section(heading, body=tuple(body), hint=hint, min_depth=depth)


def _tag_def(tag: Tag) -> Def:
    detail = None
    if tag.implied_at is not None:
        detail = f"Implied at depth {tag.implied_at}+."
    return Def(term=f"--{tag.name}", summary=tag.help, detail=detail)


def framework_sections(
    depth: int,
    *,
    has_live: bool = False,
    has_interactive: bool = False,
    include_options: bool = True,
    tags: Sequence[Tag] | None = None,
    depth_aliases: Mapping[str, int] | None = None,
    budgets: bool = False,
    prompts: Sequence[Prompt[Any]] | None = None,
) -> list[Node]:
    """The Layers / Prompts / Zoom / Mode / Format / Density / Help groups.
    Layers, Prompts, and Density appear only when declared — the help surface
    mirrors the flag surface.

    ``depth`` gates the universal grammar (Zoom/Mode/Format/Density/Help) —
    flags with the same meaning on every tool, safe to render terse when
    command args lead. Layers and Prompts are app-declared *content*
    (vocabulary and questions, respectively, not grammar): both lead the
    groups and stay at MINIMAL, fully rendered at default ``--help``
    regardless of ``depth`` — the same treatment, for the same reason
    (docs/PROMPTS_DESIGN.md §12 step 4 mirrors §1's Tag precedent).

    ``include_options=False`` keeps only Layers/Prompts (when declared) and
    Help — subcommand help, where zoom/mode/format belong to the handler but
    declared facets and questions are the command's own.
    """
    sections: list[Node] = []
    # Layers leads: app-declared vocabulary is command content, not grammar —
    # it never steps back with the universal groups.
    if tags:
        sections.append(
            _group(
                "Layers",
                "(named facets)",
                "Toggleable layers of this view, independent of depth.",
                tuple(_tag_def(t) for t in tags),
                Zoom.MINIMAL,
            )
        )
    if prompts:
        sections.append(
            _group(
                "Prompts",
                "(interactive questions)",
                "Answered at a TTY; these flags resolve them non-interactively "
                "(for scripts, CI, and --no-input).",
                tuple(_prompts_defs(prompts)),
                Zoom.MINIMAL,
            )
        )
    if include_options:
        zoom_flags: list[Def] = [
            _flag("-q", "--quiet", "Minimal output", "Also implies --static (no animation)."),
            _flag("-v", "--verbose", "Detailed (-v) or full (-vv)"),
        ]
        for alias_name, alias_depth in (depth_aliases or {}).items():
            zoom_flags.append(_flag(None, f"--{alias_name}", depth_alias_help(alias_depth)))
        sections.append(
            _group(
                "Zoom",
                "(what to show)",
                "Controls how much detail is rendered. Stackable: -v for detailed, -vv for full.",
                tuple(zoom_flags),
                depth,
            )
        )
    if include_options:
        if has_live or has_interactive:
            mode_flags: list[Def] = []
            if has_interactive:
                mode_flags.append(_flag("-i", "--interactive", "Interactive TUI"))
            mode_flags.append(_flag(None, "--static", "Static output, no animation"))
            if has_live:
                mode_flags.append(_flag(None, "--live", "Live output with in-place updates"))
            sections.append(
                _group(
                    "Mode",
                    "(how to deliver)",
                    "Delivery mechanism. AUTO selects LIVE for TTY, STATIC for pipes.",
                    tuple(mode_flags),
                    depth,
                )
            )
        sections.append(
            _group(
                "Format",
                "(serialization)",
                "Output serialization. ANSI is default for TTY, PLAIN for pipes.",
                (
                    _flag(None, "--json", "JSON output", "Implies --static."),
                    _flag(
                        None, "--plain", "Plain text, no ANSI codes", "Implies --static when piped."
                    ),
                ),
                depth,
            )
        )
        if budgets:
            sections.append(
                _group(
                    "Density",
                    "(how much per item)",
                    "Budgets applied per value or collection. 0 means unlimited.",
                    (
                        _flag(None, "--max-chars", "Max display width for string values"),
                        _flag(None, "--max-lines", "Max items to show for collections"),
                    ),
                    depth,
                )
            )
    sections.append(
        _group(
            "Help",
            "",
            None,
            (_flag("-h", "--help", "Show this help", "Add -v for more detail."),),
            depth,
        )
    )
    return sections


# =============================================================================
# Doc construction
# =============================================================================


def _header(prog: str | None, description: str | None) -> tuple[str | None, list[Node]]:
    """A doc title (prog) and an optional leading description Prose."""
    body: list[Node] = []
    if description:
        first_line = description.strip().split("\n")[0].strip()
        if first_line:
            body.append(Prose(first_line))
    return prog, body


def help_doc(runner) -> Doc:  # runner: CliRunner (avoid import cycle)
    """Build the help document for a ``run_cli`` tool.

    The command's own args (if any) are the primary content and stay expanded;
    the framework groups subordinate to ``min_depth=SUMMARY`` so they collapse to
    a terse line at the default view while the command args lead.
    """
    from .types import OutputMode

    cmd_defs = command_defs(runner.help_args, runner.add_args)
    # When the command has its own args, the framework options step back one tier.
    framework_depth = Zoom.SUMMARY if cmd_defs else Zoom.MINIMAL

    title, body = _header(runner.prog, runner.description)
    if cmd_defs:
        body.append(Defs(cmd_defs))

    has_live = runner.fetch_stream is not None
    # Mirrors _get_parser: -i also exists when surface delivery converges it
    # onto the live path — the help surface must match the flag surface.
    has_interactive = (
        runner.handlers is not None and OutputMode.INTERACTIVE in runner.handlers
    ) or (runner.live_delivery == "surface" and runner.fetch_stream is not None)
    body.extend(
        framework_sections(
            framework_depth,
            has_live=has_live,
            has_interactive=has_interactive,
            tags=runner.tags,
            depth_aliases=runner.depth_aliases,
            budgets=runner.budgets,
            prompts=runner.prompts,
        )
    )
    return Doc(title=title, body=tuple(body))


# =============================================================================
# Help arg pre-scan (zoom + format, before the real parse)
# =============================================================================


def scan_help_args(
    args: list[str],
    depth_aliases: Mapping[str, int] | None = None,
) -> tuple[Zoom, Format]:
    """Quick-scan args for zoom and format when --help is present.

    ``depth_aliases`` keeps the help path honest to "an alias is pure
    spelling": ``-h --full`` renders help at the same tier ``-h -vv`` would.
    """
    zoom = Zoom.SUMMARY
    fmt = Format.AUTO
    alias_flags = {f"--{name}": depth for name, depth in (depth_aliases or {}).items()}

    v_count = 0
    for arg in args:
        if arg == "-h" or arg == "--help":
            continue
        if arg == "-q" or arg == "--quiet":
            zoom = Zoom.MINIMAL
        elif arg in alias_flags:
            # Intentional lossy clamp: alias depths are open ints in the spec,
            # but the help path renders at a Zoom rung, so >3 reads as FULL.
            zoom = Zoom(min(max(alias_flags[arg], 0), 3))
        elif arg.startswith("-v"):
            # Count v's: -v, -vv, -vvv
            if arg.startswith("--verbose"):
                v_count += 1
            else:
                v_count += len(arg) - 1  # strip the dash
        elif arg == "--json":
            fmt = Format.JSON
        elif arg == "--plain":
            fmt = Format.PLAIN

    if zoom == Zoom.SUMMARY and v_count > 0:
        zoom = Zoom.FULL if v_count >= 2 else Zoom.DETAILED

    return zoom, fmt
