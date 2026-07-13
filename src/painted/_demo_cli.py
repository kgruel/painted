"""Demo discovery and listing for the painted CLI."""

from __future__ import annotations

import importlib.util
import sys

from painted import (
    Block,
    Fidelity,
    Style,
    Zoom,
    border,
    current_palette,
    join_horizontal,
    join_vertical,
    pad,
    print_block,
    run_cli,
    truncate,
)

# Discovery lives in the render-free _demo_discovery module so the demos
# completer can list names without pulling the renderer (no-renderer-on-TAB).
# Re-exported here so existing importers (__main__, tests) are unaffected.
from painted._demo_discovery import (
    _GROUPS,
    DemoEntry,
    _find_demos_root,
    _parse_demo,
    discover_demos,
)

__all__ = [
    "DemoEntry",
    "discover_demos",
    "_find_demos_root",
    "_parse_demo",
    "_GROUPS",
    "list_demos",
    "run_demo",
    "render_demo_list",
]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_PLAIN = Style()
_DIM = Style(dim=True)
_BOLD = Style(bold=True)


# The four tiers form a deliberate progression: each rung adds one concept over
# the one below. The blurb names what you learn at that rung.
_GROUP_BLURB = {
    "primitives": "the atoms — Cell, Span, Block, compose",
    "patterns": "data → Block: pure render functions",
    "apps": "interactive Surface apps — keyboard + state",
    "examples": "complete miniature applications",
    "showcase": "full-screen, animated — painted showing off",
}

# The showcase tier is the spectacle finale: a heavier rail and a star marker
# set it apart by treatment, not just hue, regardless of the active palette.
_SHOWCASE = "showcase"


def _tier_style(palette, group: str, index: int) -> Style:
    """Categorical color for a tier.

    The series ramp (4 entries) colors the four structural tiers. Showcase is the
    odd one out — it borrows ``accent`` so it never collides with a ramp slot
    (and is further set apart by a heavier rail + star marker when rendered).
    """
    if group == _SHOWCASE:
        return palette.accent
    ramp = palette.series or (palette.accent,)
    return ramp[index % len(ramp)]


def _demo_header(palette) -> Block:
    """A bordered title that orients a fresh user toward tour and the run command."""
    accent = palette.accent.merge(_BOLD)
    body = join_vertical(
        Block.text("a progression from atoms to apps", palette.muted),
        Block.text("", _PLAIN),
        join_horizontal(
            Block.text("start here  ", palette.muted),
            Block.text("painted tour", accent),
            Block.text("     run one  ", palette.muted),
            Block.text("painted demos <name>", accent),
        ),
    )
    return border(
        pad(body, left=1, right=1),
        title="painted",
        title_style=accent,
        style=palette.muted,
    )


def render_demo_list(entries: list[DemoEntry], fidelity: Fidelity, width: int | None) -> Block:
    """Render the demo curriculum as a progression — painted rendering itself."""
    # Tour has its own command; it's the entry point, surfaced in the header.
    demos = [e for e in entries if e.group]
    # Two-sided clamp (RENDERER_CONTRACT_DESIGN §8): depth is an open int in
    # the spec, so an out-of-range value (e.g. a negative build_fidelity
    # hook) must still land in the MINIMAL branch, not fall through it.
    depth = min(max(fidelity.depth, 0), 3)

    if depth <= Zoom.MINIMAL:
        # One name per line, for scripting — every demo is runnable by name.
        names = "\n".join(e.name for e in demos)
        return Block.text(names, _PLAIN) if names else Block.empty(0, 0)

    palette = current_palette()
    muted = palette.muted

    groups: dict[str, list[DemoEntry]] = {}
    for e in demos:
        groups.setdefault(e.group, []).append(e)

    max_name = max((len(e.name) for e in demos), default=10)

    blocks: list[Block] = [_demo_header(palette)]

    for index, group in enumerate(_GROUPS):
        group_entries = groups.get(group, [])
        if not group_entries:
            continue

        tier = _tier_style(palette, group, index)
        blurb = _GROUP_BLURB.get(group, "")
        is_showcase = group == _SHOWCASE
        # Showcase gets a heavier rail and a star marker — distinct by treatment,
        # not just hue. Names are plain bold so the rail color carries the tier.
        rail = "┃ " if is_showcase else "│ "
        marker = "✦ " if is_showcase else ""

        blocks.append(Block.text("", _PLAIN))  # spacer between tiers
        # Tier header: numbered badge + name in the tier color + muted blurb.
        blocks.append(
            join_horizontal(
                Block.text(f"{index + 1} {marker}", tier.merge(_BOLD)),
                Block.text(group, tier.merge(_BOLD)),
                Block.text(f"   {blurb}", muted) if blurb else Block.empty(0, 1),
            )
        )
        # Each demo sits behind a continuous gutter rail colored by its tier —
        # the rail's one dimension is "which rung of the progression".
        for e in group_entries:
            row = join_horizontal(
                Block.text(rail, tier),
                Block.text(f"{e.name:<{max_name}}", _BOLD),
                Block.text(f"  {e.description}", _PLAIN),
            )
            blocks.append(row)

            # DETAILED+: show invocation examples under the same rail.
            if depth >= Zoom.DETAILED and e.invocations:
                for inv in e.invocations:
                    blocks.append(
                        join_horizontal(Block.text(rail, tier), Block.text(f"  {inv}", _DIM))
                    )

    # Progression footer: the ladder spelled out, each rung in its tier color.
    footer_parts: list[Block] = []
    for index, group in enumerate(_GROUPS):
        if index:
            footer_parts.append(Block.text(" → ", muted))
        footer_parts.append(Block.text(group, _tier_style(palette, group, index).merge(_BOLD)))
    blocks.append(Block.text("", _PLAIN))
    blocks.append(join_horizontal(*footer_parts))

    result = join_vertical(*blocks) if blocks else Block.empty(0, 0)
    return truncate(result, width) if width is not None else result


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def list_demos(args: list[str]) -> int:
    """List available demos via run_cli."""
    return run_cli(
        args,
        renderer=render_demo_list,
        fetch=discover_demos,
        description="List available painted demos",
        prog="painted demos",
    )


def run_demo(name: str, args: list[str]) -> int:
    """Run a demo by name, forwarding remaining args."""
    entries = discover_demos()
    match = next((e for e in entries if e.name == name), None)

    if match is None:
        # Suggest similar names (every tiered demo is runnable; tour is separate)
        all_names = [e.name for e in entries if e.group]
        suggestions = [n for n in all_names if name in n or n in name]
        msg = f"Unknown demo: {name}"
        if suggestions:
            msg += f"\n\nDid you mean: {', '.join(suggestions)}?"
        else:
            msg += f"\n\nAvailable: {', '.join(all_names)}"
        print_block(Block.text(msg, Style(fg="red")))
        return 1

    # Guard-only demos (primitives) have no main(); they run via their
    # `if __name__ == "__main__"` block. Loading them under that module name
    # fires the guard during exec. main()-based demos load under a private name
    # so their guard stays inert and we call main() ourselves below.
    mod_name = "__main__" if not match.has_main else f"demo_{match.name}"
    spec = importlib.util.spec_from_file_location(mod_name, match.path)
    if spec is None or spec.loader is None:
        print_block(Block.text(f"Cannot load: {match.path}", Style(fg="red")))
        return 1

    module = importlib.util.module_from_spec(spec)
    saved_argv = sys.argv[:]
    saved_mod = sys.modules.get(mod_name)
    try:
        sys.argv = [str(match.path)] + args
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        if not match.has_main:
            return 0
        main_fn = getattr(module, "main", None)
        if main_fn is None:
            print_block(Block.text(f"No main() in {match.path}", Style(fg="red")))
            return 1
        import asyncio
        import inspect

        if inspect.iscoroutinefunction(main_fn):
            result = asyncio.run(main_fn())
        else:
            result = main_fn()
        return result if isinstance(result, int) else 0
    finally:
        sys.argv = saved_argv
        if saved_mod is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = saved_mod
