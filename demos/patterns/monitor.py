#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Host monitor — one dataset across the fidelity spectrum.

A host's vitals (cpu/mem/disk/net) rendered at every zoom through run_cli.
The same data and the same render function; the flag picks the surface — the
code never switches on a mode. Bars are colored by *severity* through the
ambient Palette, so the look follows `use_palette()` (DEFAULT → named colors,
PAINTED → vivid hues, MONO → modifiers).

    uv run demos/patterns/monitor.py -q     # worst-first, one line
    uv run demos/patterns/monitor.py        # labeled severity bars
    uv run demos/patterns/monitor.py -vv    # bars + per-metric detail
"""

from __future__ import annotations

import sys

from painted import (
    Block,
    CliContext,
    Style,
    Zoom,
    join_horizontal,
    join_vertical,
    run_cli,
    truncate,
)
from painted.views import current_palette


# --- Data: a host's vitals, as percentages ---

SAMPLE: dict[str, int] = {"cpu": 67, "mem": 82, "disk": 45, "net": 23}

# A later tick — a few metrics drifted. Used to show --live as a *different*
# frame from the one-shot print (only the changed cells repaint).
SAMPLE_LIVE: dict[str, int] = {"cpu": 73, "mem": 78, "disk": 45, "net": 41}


def _severity(value: int) -> str:
    """Map a 0–100 metric to a semantic Palette role name."""
    if value >= 80:
        return "error"
    if value >= 65:
        return "warning"
    if value >= 40:
        return "success"
    return "accent"


def _role(name: str) -> Style:
    return getattr(current_palette(), name)


# --- Zoom 0: worst-first, one line ---


def render_minimal(data: dict[str, int], width: int) -> Block:
    worst = max(data, key=lambda k: data[k])
    line = join_horizontal(
        Block.text(f"{worst} {data[worst]}%", _role(_severity(data[worst])).merge(Style(bold=True))),
        Block.text("   ", Style()),
        Block.text(
            "  ".join(f"{k} {v}%" for k, v in data.items() if k != worst),
            Style(dim=True),
        ),
    )
    return truncate(line, width)


# --- Zoom 1: labeled severity bars ---


def _bar_row(label: str, value: int, label_w: int, bar_w: int) -> Block:
    filled = round(value / 100 * bar_w)
    return join_horizontal(
        Block.text(label.rjust(label_w) + " ", Style(dim=True)),
        Block.text("█" * filled, _role(_severity(value))),
        Block.text("░" * (bar_w - filled), Style(dim=True)),
        Block.text(f" {value:3d}%", Style(dim=True)),
    )


def render_standard(data: dict[str, int], width: int) -> Block:
    label_w = max(len(k) for k in data)
    bar_w = max(8, min(28, width - label_w - 8))
    return truncate(join_vertical(*(_bar_row(k, v, label_w, bar_w) for k, v in data.items())), width)


# --- Zoom 2+: bars + per-metric detail ---

_STATUS = {"error": "critical", "warning": "elevated", "success": "nominal", "accent": "idle"}


def render_verbose(data: dict[str, int], width: int) -> Block:
    label_w = max(len(k) for k in data)
    bar_w = max(8, min(28, width - label_w - 12))
    rows: list[Block] = [Block.text("host vitals", Style(bold=True)), Block.text("", Style())]
    for k, v in data.items():
        role = _severity(v)
        rows.append(_bar_row(k, v, label_w, bar_w))
        rows.append(
            join_horizontal(
                Block.text(" " * (label_w + 1), Style()),
                Block.text(_STATUS[role], _role(role)),
                Block.text("  ·  threshold 80%  ·  sampled 60s", Style(dim=True)),
            )
        )
    return truncate(join_vertical(*rows), width)


# --- run_cli integration ---


def _fetch() -> dict[str, int]:
    return dict(SAMPLE)


def _render(ctx: CliContext, data: dict[str, int]) -> Block:
    z = int(ctx.zoom)
    if z <= 0:
        return render_minimal(data, ctx.width)
    if z >= 2:
        return render_verbose(data, ctx.width)
    return render_standard(data, ctx.width)


def main() -> int:
    return run_cli(
        sys.argv[1:],
        render=_render,
        fetch=_fetch,
        description=__doc__,
        prog="monitor.py",
    )


if __name__ == "__main__":
    sys.exit(main())
