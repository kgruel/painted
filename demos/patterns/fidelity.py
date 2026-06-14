#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Fidelity spectrum — the whole disclosure ladder, one render fn.

Disk usage rendered at every zoom level through run_cli. The flags drive the
output — the code doesn't switch on modes. Each line below climbs a rung of
the disclosure grammar (docs/FIDELITY_DESIGN.md); every rung is additive.

    uv run demos/patterns/fidelity.py -q        # rung 1: depth — one line
    uv run demos/patterns/fidelity.py           # rung 1: depth — directory list
    uv run demos/patterns/fidelity.py -v        # rung 1: depth — styled bars
    uv run demos/patterns/fidelity.py -vv       # rung 1: depth — full detail
    uv run demos/patterns/fidelity.py --timestamp        # rung 2: a named facet, any depth
    uv run demos/patterns/fidelity.py --brief            # depth alias: == -q (depth 0)
    uv run demos/patterns/fidelity.py --full             # depth alias: == -vv (depth 3)
    uv run demos/patterns/fidelity.py -vv --max-lines 3  # rung 3: density budget
    FIDELITY_DEPTH=full uv run demos/patterns/fidelity.py  # escape hatch: env baseline

`--brief`/`--full` are depth_aliases — named spellings of the same depth axis,
not new facets. `FIDELITY_DEPTH` is the build_fidelity escape hatch: residue
the declarative grammar can't express (see _env_baseline below).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from painted import (
    Block,
    Fidelity,
    Style,
    CliContext,
    Tag,
    Zoom,
    border,
    join_vertical,
    join_horizontal,
    pad,
    truncate,
    ROUNDED,
    run_cli,
)
from painted.cli import implied_visible


# --- Data model ---


def _human_size(n: int) -> str:
    """Format byte count as human-readable string."""
    size: float = n
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}P"


@dataclass(frozen=True)
class DirEntry:
    """A directory or file with its size."""

    name: str
    size_bytes: int
    is_dir: bool = True
    children: tuple["DirEntry", ...] = ()

    @property
    def size_human(self) -> str:
        return _human_size(self.size_bytes)


@dataclass(frozen=True)
class DiskData:
    """Disk usage summary."""

    mount: str
    total_bytes: int
    used_bytes: int
    entries: tuple[DirEntry, ...]
    timestamp: str = ""

    @property
    def free_bytes(self) -> int:
        return self.total_bytes - self.used_bytes

    @property
    def used_percent(self) -> float:
        return (self.used_bytes / self.total_bytes) * 100 if self.total_bytes > 0 else 0

    @property
    def total_human(self) -> str:
        return _human_size(self.total_bytes)

    @property
    def used_human(self) -> str:
        return _human_size(self.used_bytes)

    @property
    def free_human(self) -> str:
        return _human_size(self.free_bytes)


# --- Sample data ---

SAMPLE_DISK = DiskData(
    mount="/home",
    total_bytes=200 * 1024**3,
    used_bytes=134 * 1024**3,
    entries=(
        DirEntry(
            "projects",
            45 * 1024**3,
            children=(
                DirEntry(
                    "prism",
                    12 * 1024**3,
                    children=(
                        DirEntry("libs", 3 * 1024**3),
                        DirEntry("experiments", 2 * 1024**3),
                        DirEntry(".venv", 5 * 1024**3),
                        DirEntry("node_modules", 2 * 1024**3),
                    ),
                ),
                DirEntry("website", 8 * 1024**3),
                DirEntry("ml-research", 15 * 1024**3),
                DirEntry("archive", 10 * 1024**3),
            ),
        ),
        DirEntry(
            "downloads",
            28 * 1024**3,
            children=(
                DirEntry("installers", 12 * 1024**3),
                DirEntry("datasets", 10 * 1024**3),
                DirEntry("misc", 6 * 1024**3),
            ),
        ),
        DirEntry(
            ".cache",
            22 * 1024**3,
            children=(
                DirEntry("pip", 8 * 1024**3),
                DirEntry("huggingface", 10 * 1024**3),
                DirEntry("uv", 4 * 1024**3),
            ),
        ),
        DirEntry("documents", 18 * 1024**3),
        DirEntry("pictures", 12 * 1024**3),
        DirEntry(".local", 9 * 1024**3),
    ),
    # Fixed so harness captures (tools/capture.py, panel specimens) are
    # deterministic; the real _fetch() path stamps now().
    timestamp="2026-06-11T09:30:00",
)


# --- Zoom 0: one-line summary ---


def render_minimal(data: DiskData, width: int) -> Block:
    result = Block.text(
        f"{data.used_percent:.0f}% used ({data.used_human}/{data.total_human})",
        Style(),
    )
    return truncate(result, width)


# --- Zoom 1: directory list ---


def render_standard(data: DiskData, width: int) -> Block:
    rows: list[Block] = [
        Block.text(f"Disk usage: {data.mount}", Style(bold=True)),
        Block.text(
            f"  {data.used_human} / {data.total_human} ({data.used_percent:.1f}% used)",
            Style(),
        ),
        Block.text("", Style()),
        Block.text("Top directories:", Style()),
    ]

    sorted_entries = sorted(data.entries, key=lambda e: e.size_bytes, reverse=True)
    for entry in sorted_entries[:8]:
        pct = (entry.size_bytes / data.used_bytes) * 100 if data.used_bytes > 0 else 0
        rows.append(
            Block.text(
                f"  {entry.size_human:>6}  {pct:4.1f}%  {entry.name}",
                Style(),
            )
        )

    rows.append(Block.text("", Style()))
    rows.append(Block.text(f"Free: {data.free_human}", Style()))
    return truncate(join_vertical(*rows), width)


# --- Zoom 2: styled bars ---


def _usage_bar(data: DiskData, bar_width: int) -> Block:
    """Overall disk usage bar."""
    filled = int(data.used_percent / 100 * bar_width)

    if data.used_percent > 90:
        bar_style = Style(fg="red", bold=True)
    elif data.used_percent > 75:
        bar_style = Style(fg="yellow")
    else:
        bar_style = Style(fg="green")

    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
    return join_horizontal(
        Block.text(f"{data.used_percent:5.1f}% ", bar_style),
        Block.text(bar, bar_style),
        Block.text(f" {data.used_human}/{data.total_human}", Style(dim=True)),
    )


def _dir_row(entry: DirEntry, parent_bytes: int, bar_width: int, indent: int = 0) -> Block:
    """Single directory row with size bar."""
    pct = (entry.size_bytes / parent_bytes) * 100 if parent_bytes > 0 else 0

    size_block = Block.text(entry.size_human.rjust(6), Style(bold=True if indent == 0 else False))

    filled = int(pct / 100 * bar_width)
    bar_style = Style(fg="yellow") if pct > 20 else Style(fg="cyan")
    bar = "\u2593" * filled + "\u2591" * (bar_width - filled)

    name_prefix = "  " + "  " * indent
    name_style = Style() if indent == 0 else Style(dim=True)

    return join_horizontal(
        size_block,
        Block.text(" ", Style()),
        Block.text(bar, bar_style),
        Block.text(" ", Style()),
        Block.text(f"{pct:5.1f}%", Style(dim=True)),
        Block.text(f"{name_prefix}{entry.name}", name_style),
    )


def render_styled(data: DiskData, width: int) -> Block:
    """Zoom 2: styled bars, top-level directories only."""
    # Shared bar width for consistent alignment
    bar_width = min(30, width - 30)

    usage = _usage_bar(data, bar_width)
    sorted_entries = sorted(data.entries, key=lambda e: e.size_bytes, reverse=True)
    rows = [_dir_row(e, data.used_bytes, bar_width) for e in sorted_entries]
    dir_table = join_vertical(*rows)

    # Pad narrower block so both boxes match width
    content_width = max(usage.width, dir_table.width)
    usage_padded = pad(usage, right=content_width - usage.width)
    dir_padded = pad(dir_table, right=content_width - dir_table.width)

    free_style = Style(fg="green" if data.used_percent < 75 else "yellow", bold=True)
    blocks = [
        border(usage_padded, title=f"Disk: {data.mount}", chars=ROUNDED),
        Block.text("", Style()),
        border(dir_padded, title="By Directory", chars=ROUNDED),
        Block.text("", Style()),
        Block.text(f"  Free: {data.free_human}  ", free_style),
    ]
    return join_vertical(*blocks)


# --- Zoom 3: full detail with children ---


def render_full(data: DiskData, width: int) -> Block:
    """Zoom 3: styled bars with subdirectories expanded."""
    bar_width = min(30, width - 30)

    usage = _usage_bar(data, bar_width)
    sorted_entries = sorted(data.entries, key=lambda e: e.size_bytes, reverse=True)

    rows: list[Block] = []
    for entry in sorted_entries:
        rows.append(_dir_row(entry, data.used_bytes, bar_width))
        if entry.children:
            sorted_children = sorted(entry.children, key=lambda e: e.size_bytes, reverse=True)
            for child in sorted_children:
                rows.append(_dir_row(child, entry.size_bytes, bar_width, indent=1))

    dir_table = join_vertical(*rows)

    content_width = max(usage.width, dir_table.width)
    usage_padded = pad(usage, right=content_width - usage.width)
    dir_padded = pad(dir_table, right=content_width - dir_table.width)

    free_style = Style(fg="green" if data.used_percent < 75 else "yellow", bold=True)
    blocks = [
        border(usage_padded, title=f"Disk: {data.mount}", chars=ROUNDED),
        Block.text("", Style()),
        border(dir_padded, title="By Directory", chars=ROUNDED),
        Block.text("", Style()),
        Block.text(f"  Free: {data.free_human}  ", free_style),
    ]
    return join_vertical(*blocks)


# --- run_cli integration ---


def _fetch() -> DiskData:
    """Real disk stats for home directory, sample subdirectories."""
    home = Path.home()
    try:
        usage = shutil.disk_usage(home)
    except OSError:
        return SAMPLE_DISK
    return DiskData(
        mount=str(home),
        total_bytes=usage.total,
        used_bytes=usage.used,
        entries=SAMPLE_DISK.entries,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )


# Module-level so harnesses that build Fidelity directly (tools/capture.py)
# can resolve the same implications the CLI compiles.
_TAGS = [Tag("timestamp", "Show the measurement timestamp", implied_at=2)]

# The depth axis answers to two named spellings as well as -q/-v/-vv. Pure
# spelling, so --brief compiles to the same Fidelity as -q (depth 0) and --full
# to the same as -vv (depth 3) — including --full inheriting the timestamp facet
# (implied_at=2 trips at depth 3). Matches the site walkthrough's exemplar.
_DEPTH_ALIASES = {"brief": 0, "full": 3}

# Named depths the FIDELITY_DEPTH env var accepts — the env speaks the user's
# vocabulary, not raw ints, so the baseline is set the same way --full would be.
_ENV_DEPTHS = {z.name.lower(): int(z) for z in Zoom}


def _env_baseline(parsed: argparse.Namespace, fidelity: Fidelity) -> Fidelity:
    """build_fidelity escape hatch: an env-var-derived default depth.

    The escape hatch sits *below* the declarative ladder (tags/aliases/budgets),
    not as a rung on it — it's where residue lands that the grammar can't say.

    WHY this is genuine residue — not expressible by the declarative grammar:
    Tags, depth_aliases, and budgets all compile from explicit *command-line
    flags*. The grammar has no vocabulary for "read an environment variable and
    use it as the baseline when the user passed no depth flag" — that needs a
    procedure (look up the env, decide whether a flag already won, translate a
    name to a depth) the declarations can't carry. build_fidelity is exactly
    that seam: it runs last, after tag compilation, and can do arbitrary work.

    The honesty rule still holds: an explicit -q/-v/-vv/--brief/--full always
    wins, because we only adopt the env baseline when no depth flag was passed.
    Inert by default: unset env returns the fidelity untouched, so deterministic
    captures (panels, sentinels) — which set nothing — never see it move.
    """
    raw = os.environ.get("FIDELITY_DEPTH")
    if raw is None:
        return fidelity
    depth = _ENV_DEPTHS.get(raw.strip().lower())
    if depth is None:
        return fidelity  # an unrecognized name is ignored, not an error
    # A flag the user typed beats the env. "No depth flag" = none of the depth
    # spellings is set in the parsed namespace (the alias dests included). An
    # alias name maps to its argparse dest the way the compiler does (kebab →
    # snake), so a future multi-word alias like "deep-dive" is read from its real
    # `deep_dive` attr, not the hyphenated name that could never be an attribute.
    flagged = (
        getattr(parsed, "quiet", False)
        or getattr(parsed, "verbose", 0)
        or any(getattr(parsed, name.replace("-", "_"), False) for name in _DEPTH_ALIASES)
    )
    if flagged:
        return fidelity
    # Re-resolve through the depth: the timestamp facet's implied_at must trip
    # off the env-chosen depth too, so the baseline behaves like a real depth.
    # implied_visible is the same resolver the CLI compiler uses, so an env
    # baseline of `full` carries the timestamp exactly like -vv does.
    visible = fidelity.visible | implied_visible(_TAGS, depth)
    return replace(fidelity, depth=depth, visible=visible)


def _budgeted(data: DiskData, ctx: CliContext) -> DiskData:
    # Density budgets (rung 3): lines caps items per collection, chars caps
    # string values. Applied to the data once, so every depth renderer honors
    # them without knowing they exist.
    fid = ctx.fidelity
    if not (fid.has_line_limit or fid.has_char_limit):
        return data

    def cut(name: str) -> str:
        if fid.has_char_limit and len(name) > fid.chars:
            return name[: max(fid.chars - 1, 1)] + "…"
        return name

    def cap(entries: tuple[DirEntry, ...]) -> tuple[DirEntry, ...]:
        ranked = sorted(entries, key=lambda e: e.size_bytes, reverse=True)
        if fid.has_line_limit:
            ranked = ranked[: fid.lines]
        return tuple(replace(e, name=cut(e.name), children=cap(e.children)) for e in ranked)

    return replace(data, mount=cut(data.mount), entries=cap(data.entries))


def _render(ctx: CliContext, data: DiskData) -> Block:
    # Depth picks the renderer (anonymous detail); the timestamp is a named
    # facet riding fidelity.visible — --timestamp at any depth, implied at -v.
    data = _budgeted(data, ctx)
    if ctx.zoom >= Zoom.FULL:
        block = render_full(data, ctx.width)
    elif ctx.zoom >= Zoom.DETAILED:
        block = render_styled(data, ctx.width)
    elif ctx.zoom >= Zoom.SUMMARY:
        block = render_standard(data, ctx.width)
    else:
        block = render_minimal(data, ctx.width)
    if ctx.fidelity.shows("timestamp") and data.timestamp:
        stamp = truncate(Block.text(f"  {data.timestamp}", Style(dim=True)), ctx.width)
        block = join_vertical(block, stamp)
    return block


def main() -> int:
    return run_cli(
        sys.argv[1:],
        render=_render,
        fetch=_fetch,
        description=__doc__,
        prog="fidelity.py",
        tags=_TAGS,
        depth_aliases=_DEPTH_ALIASES,
        budgets=True,
        build_fidelity=_env_baseline,
    )


if __name__ == "__main__":
    sys.exit(main())
