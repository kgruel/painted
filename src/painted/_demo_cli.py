"""Demo discovery and listing for the painted CLI."""

from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from painted import (
    Block,
    CliContext,
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

# ---------------------------------------------------------------------------
# DemoEntry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemoEntry:
    name: str  # "fidelity"
    group: str  # "patterns"
    path: Path  # absolute path to .py file
    description: str  # first line of docstring
    invocations: tuple[str, ...] = ()  # "uv run ..." lines from docstring
    has_main: bool = True  # False for primitives/apps


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_CACHE: list[DemoEntry] | None = None

_GROUPS = ("primitives", "patterns", "apps", "examples", "showcase")


def _find_demos_root() -> Path | None:
    """Locate the demos/ directory across dev checkout and installed wheel."""
    here = Path(__file__).resolve()
    candidates = (
        # Dev checkout: src/painted/_demo_cli.py -> src/painted -> src -> project root
        here.parent.parent.parent / "demos",
        # Installed wheel: demos/ is force-included under the package itself
        # (site-packages/painted/demos), so it sits beside this module.
        here.parent / "demos",
        # Last resort: running from a project root that has a demos/ tree
        Path.cwd() / "demos",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _parse_demo(path: Path, group: str) -> DemoEntry | None:
    """Extract demo metadata via ast without executing the file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return None

    docstring = ast.get_docstring(tree) or ""
    first_line = docstring.split("\n")[0].strip() if docstring else path.stem

    # Extract invocation lines: lines starting with whitespace + "uv run"
    invocations: list[str] = []
    for line in docstring.split("\n"):
        stripped = line.strip()
        if stripped.startswith("uv run"):
            invocations.append(stripped)

    # has_main: check for top-level def main or async def main
    has_main = any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        for node in ast.iter_child_nodes(tree)
    )

    return DemoEntry(
        name=path.stem,
        group=group,
        path=path.resolve(),
        description=first_line,
        invocations=tuple(invocations),
        has_main=has_main,
    )


def discover_demos() -> list[DemoEntry]:
    """Find all demos, sorted by group then name. Cached."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    root = _find_demos_root()
    if root is None:
        _CACHE = []
        return _CACHE

    entries: list[DemoEntry] = []
    for group in _GROUPS:
        group_dir = root / group
        if not group_dir.is_dir():
            continue
        for path in sorted(group_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            entry = _parse_demo(path, group)
            if entry is not None:
                entries.append(entry)

    # Also discover tour.py at demos root
    tour_path = root / "tour.py"
    if tour_path.exists():
        entry = _parse_demo(tour_path, "")
        if entry is not None:
            entries.append(entry)

    _CACHE = entries
    return _CACHE


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


def render_demo_list(ctx: CliContext, entries: list[DemoEntry]) -> Block:
    """Render the demo curriculum as a progression — painted rendering itself."""
    # Tour has its own command; it's the entry point, surfaced in the header.
    demos = [e for e in entries if e.group]

    if ctx.zoom == Zoom.MINIMAL:
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
            if ctx.zoom >= Zoom.DETAILED and e.invocations:
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
    return truncate(result, ctx.width)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def list_demos(args: list[str]) -> int:
    """List available demos via run_cli."""
    return run_cli(
        args,
        render=render_demo_list,
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
