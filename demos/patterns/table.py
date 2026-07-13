#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["painted"]
# ///
"""Table construction — one table, grown from a fixed grid to a responsive layout.

A column's width is a track-sizing function: a fixed ``int``, ``AUTO`` (hug
content), or ``Fill`` (take a share of the leftover budget), with optional
``min_width``/``max_width`` clamps. The same `table()` call climbs a ladder —
fixed → AUTO → Fill → responsive — and each rung only *adds* to the column
vocabulary; none rewrites the rung below. The payoff is a width-driven table
that drops low-priority columns and lets a Fill column absorb the slack.

    uv run demos/patterns/table.py -q     # the punchline: fixed breaks, responsive adapts
    uv run demos/patterns/table.py        # the full fixed → AUTO → Fill → responsive ladder
    uv run demos/patterns/table.py -vv    # + width ladder, clamps, weights, wide chars

Interactive — press ←/→ to resize and watch columns drop and the Fill reflow:

    uv run demos/patterns/table.py -i
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from dataclasses import dataclass

from painted import (
    ROUNDED,
    Align,
    Block,
    CliContext,
    Fidelity,
    Line,
    OutputMode,
    Style,
    border,
    join_horizontal,
    join_vertical,
    print_block,
    run_cli,
)
from painted.tui import Surface
from painted.views import AUTO, Column, Fill, TableState, current_palette, table


# =============================================================================
# Sample data — a service inventory with a story (one failure, one blocked job)
# =============================================================================


@dataclass(frozen=True)
class Service:
    name: str
    status: str
    kind: str
    size: str
    notes: str


SAMPLE: list[Service] = [
    Service("api-gateway", "success", "service", "12.4 MB", "2 of 3 replicas ready"),
    Service("auth", "success", "service", "8.1 MB", "healthy"),
    Service("worker-scheduler", "running", "daemon", "30.0 MB", "queue depth 142, backpressure on"),
    Service("payments-api", "failed", "service", "18.7 MB", "rollout timed out: ImagePullBackOff"),
    Service("cache", "degraded", "store", "256 KB", "evicting cold keys; hit rate 71%"),
    Service("cron-billing", "queued", "job", "—", "blocked on payments-api deploy"),
]


def _status_icon(status: str) -> str:
    return {"success": "✓", "running": "●", "failed": "✕", "degraded": "▲", "queued": "…"}.get(
        status, "?"
    )


def _status_style(status: str) -> Style:
    p = current_palette()
    return {
        "success": p.success.merge(Style(bold=True)),
        "running": p.accent.merge(Style(bold=True)),
        "failed": p.error.merge(Style(bold=True)),
        "degraded": p.warning.merge(Style(bold=True)),
        "queued": p.muted,
    }.get(status, Style())


# =============================================================================
# The adaptive table — columns by priority, a Fill that absorbs the slack
# =============================================================================


@dataclass(frozen=True)
class ColSpec:
    key: str
    header: str
    field: Callable[[Service], str]
    track: object  # int | AUTO | Fill
    align: Align
    appears_at: int  # include this column only when the budget is at least this wide


# Priority order: status and name are always present; kind, size, then notes are
# added as the budget grows — and dropped, widest-first, as it shrinks. `name`
# and `notes` are Fill columns (weights 1:2), so the survivors split the slack.
_COLUMNS: list[ColSpec] = [
    ColSpec("status", "", lambda s: _status_icon(s.status), 1, Align.START, 0),
    ColSpec("name", "name", lambda s: s.name, Fill(weight=1), Align.START, 0),
    ColSpec("kind", "kind", lambda s: s.kind, AUTO, Align.START, 30),
    ColSpec("size", "size", lambda s: s.size, AUTO, Align.END, 44),
    ColSpec("notes", "notes", lambda s: s.notes, Fill(weight=2), Align.START, 62),
]


def _active(width: int) -> list[ColSpec]:
    return [c for c in _COLUMNS if width >= c.appears_at]


def _cell_style(key: str, status: str) -> Style:
    if key == "status":
        return _status_style(status)
    if key == "name" and status in ("failed", "degraded", "running"):
        return _status_style(status)
    if key == "notes":
        return Style(dim=True)
    return Style()


def render_adaptive(data: list[Service], width: int) -> Block:
    """The responsive table: pick columns by priority for `width`, then resolve."""
    active = _active(width)
    columns = [Column(Line.plain(c.header), width=c.track, align=c.align) for c in active]
    rows = [[Line.plain(c.field(s), _cell_style(c.key, s.status)) for c in active] for s in data]
    state = TableState().with_count(len(rows)).with_visible(len(rows))
    return table(
        state, columns, rows, visible_height=len(rows), width=width, selected_style=Style()
    )


# =============================================================================
# Construction helpers (the demo's own layer is the table API)
# =============================================================================


def _col(
    header: str, track, *, align: Align = Align.START, min_width=None, max_width=None
) -> Column:
    return Column(
        Line.plain(header), width=track, align=align, min_width=min_width, max_width=max_width
    )


def _grid(columns: list[Column], rows: list[list[str]], *, width: int | None = None) -> Block:
    lines = [[Line.plain(cell) for cell in row] for row in rows]
    state = TableState().with_count(len(lines)).with_visible(len(lines))
    return table(
        state, columns, lines, visible_height=len(lines), width=width, selected_style=Style()
    )


_FIELD: dict[str, Callable[[Service], str]] = {
    "name": lambda s: s.name,
    "kind": lambda s: s.kind,
    "size": lambda s: s.size,
    "notes": lambda s: s.notes,
}


def _rows_for(data: list[Service], keys: tuple[str, ...]) -> list[list[str]]:
    return [[_FIELD[k](s) for k in keys] for s in data]


def _label(text: str) -> Block:
    return Block.text(text, Style(bold=True))


def _caption(text: str) -> Block:
    return Block.text(text, Style(dim=True))


def _spacer() -> Block:
    return Block.text("", Style())


def _section(title: str, caption: str, *bodies: Block) -> Block:
    return join_vertical(_label(title), _caption(caption), _spacer(), *bodies)


# =============================================================================
# The ladder — one table, four rungs, each only adding vocabulary
# =============================================================================

_VOCAB = ("name", "kind", "size", "notes")


def _rung_fixed(data: list[Service], width: int) -> Block:
    # Fixed total is 18+8+7+24 + 3 separators = 60; at a narrow budget it clips.
    cols = [_col("name", 18), _col("kind", 8), _col("size", 7, align=Align.END), _col("notes", 24)]
    return _section(
        "0 · fixed widths",
        f"every column a hard int (total 60) — at width {width} the table is clipped, notes lost",
        _grid(cols, _rows_for(data, _VOCAB), width=width),
    )


def _rung_auto(data: list[Service]) -> Block:
    cols = [
        _col("name", AUTO),
        _col("kind", AUTO),
        _col("size", AUTO, align=Align.END),
        _col("notes", AUTO),
    ]
    return _section(
        "1 · AUTO",
        "each column hugs its content — nothing clipped, but notes makes the whole table wide",
        _grid(cols, _rows_for(data, _VOCAB)),
    )


def _rung_fill(data: list[Service], width: int) -> Block:
    cols = [
        _col("name", AUTO),
        _col("kind", AUTO),
        _col("size", AUTO, align=Align.END),
        _col("notes", Fill()),
    ]
    return _section(
        "2 · Fill",
        f"notes = Fill() takes exactly the leftover — the table fits the {width}-col budget",
        _grid(cols, _rows_for(data, _VOCAB), width=width),
    )


def _rung_responsive(data: list[Service], wide: int, narrow: int) -> Block:
    return _section(
        "3 · responsive",
        "add priority: drop low-value columns first; name (Fill) holds the line as it narrows",
        _caption(f"width = {wide}    columns: {' '.join(c.key for c in _active(wide))}"),
        render_adaptive(data, wide),
        _spacer(),
        _caption(f"width = {narrow}    columns: {' '.join(c.key for c in _active(narrow))}"),
        render_adaptive(data, narrow),
    )


# =============================================================================
# Reference aspects (deep zoom) — clamps, weights, wide characters
# =============================================================================


def _ref_clamps(data: list[Service]) -> Block:
    cols = [_col("name", AUTO, max_width=8), _col("notes", Fill(), min_width=14)]
    return _section(
        "clamps — min_width / max_width",
        "name = AUTO capped at max_width=8 (truncates)   notes = Fill() floored at min_width=14",
        _grid(cols, _rows_for(data, ("name", "notes")), width=40),
    )


def _ref_weights() -> Block:
    cols = [_col("Fill(weight=1)", Fill(weight=1)), _col("Fill(weight=2)", Fill(weight=2))]
    return _section(
        "weights — Fill columns divide the slack",
        "two Fill columns split the leftover 1 : 2",
        _grid(cols, [["one share", "two shares"]], width=48),
    )


def _ref_wcwidth() -> Block:
    cols = [_col("name", AUTO), _col("status", AUTO, align=Align.END)]
    rows = [["api-gateway", "ok"], ["日本語サービス", "ok"], ["café-utils", "ok"], ["cache", "ok"]]
    return _section(
        "width-aware — display columns, not len()",
        "the CJK row is 7 codepoints but 14 columns wide; the status column still aligns",
        _grid(cols, rows),
    )


# =============================================================================
# run_cli integration — one dataset, zoom selects how much of the ladder
# =============================================================================


def _fetch() -> list[Service]:
    return SAMPLE


#  The demo's own domain size: the "current viewport" the width ladder
# demonstrates against when no width is offered (a pipe's natural sizing) —
# not a resurrected terminal-fallback guess. The ladder's other rungs (48,
# 36, 24) are fixed demonstration points regardless of the offered width.
_NATURAL_BUDGET = 64


def _render(data: list[Service], fidelity: Fidelity, width: int | None) -> Block:
    z = fidelity.depth
    budget = _NATURAL_BUDGET if width is None else min(64, max(24, width))
    narrow = 34

    blocks: list[Block] = []

    if z <= 0:
        # The punchline: the same data, fixed (clipped) vs responsive (adapts).
        blocks = [
            _section(
                "fixed widths break; responsive adapts",
                f"both at width {narrow} — fixed clips its right columns, responsive drops + sheds",
                _caption("fixed"),
                _grid(
                    [
                        _col("name", 18),
                        _col("kind", 8),
                        _col("size", 7, align=Align.END),
                        _col("notes", 24),
                    ],
                    _rows_for(data, _VOCAB),
                    width=narrow,
                ),
                _spacer(),
                _caption("responsive"),
                render_adaptive(data, narrow),
            )
        ]
    else:
        sections = [
            _rung_fixed(data, narrow),
            _rung_auto(data),
            _rung_fill(data, budget),
            _rung_responsive(data, budget, narrow),
        ]
        if z >= 2:
            sections.append(
                _section(
                    "the width ladder",
                    "the responsive table across a range of budgets — watch columns drop, then name shed",
                    *_width_ladder(data, (budget, 48, 36, 24)),
                )
            )
        if z >= 3:
            sections += [_ref_clamps(data), _ref_weights(), _ref_wcwidth()]
        blocks = _interleave(sections)

    return join_vertical(*blocks)


def _width_ladder(data: list[Service], widths: tuple[int, ...]) -> list[Block]:
    out: list[Block] = []
    for i, w in enumerate(widths):
        if i:
            out.append(_spacer())
        out.append(_caption(f"width = {w:>3}    columns: {' '.join(c.key for c in _active(w))}"))
        out.append(render_adaptive(data, w))
    return out


def _interleave(sections: list[Block]) -> list[Block]:
    out: list[Block] = []
    for i, s in enumerate(sections):
        if i:
            out += [_spacer(), _spacer()]
        out.append(s)
    return out


# =============================================================================
# Interactive surface — press ←/→ to resize and watch the table reflow
# =============================================================================

_MIN_W = 16


class TableSurface(Surface):
    """Resize the budget with ←/→ and watch columns drop and the Fill reflow."""

    def __init__(self, data: list[Service]):
        super().__init__()
        self._data = data
        self._term_w = 80
        self._term_h = 24
        self._sim_w = 56

    def layout(self, width: int, height: int) -> None:
        self._term_w = width
        self._term_h = height
        self._sim_w = max(_MIN_W, min(self._sim_w, width - 4))

    def _ruler(self) -> Block:
        bar_len = 36
        ref = max(self._sim_w, self._term_w - 4, 1)
        filled = max(0, min(bar_len, round(self._sim_w / ref * bar_len)))
        return join_horizontal(
            Block.text(f"  width {self._sim_w:>3}  ", Style(bold=True)),
            Block.text("█" * filled, current_palette().accent),
            Block.text("░" * (bar_len - filled), Style(dim=True)),
            Block.text(f"  {len(_active(self._sim_w))} cols", Style(dim=True)),
        )

    def render(self) -> None:
        if self._buf is None:
            return
        self._buf.fill(0, 0, self._term_w, self._term_h, " ", Style())
        active = "  ".join(c.key for c in _active(self._sim_w))
        body = join_vertical(
            Block.text(
                " table widths — resize live ", current_palette().accent.merge(Style(bold=True))
            ),
            _spacer(),
            self._ruler(),
            Block.text(f"  columns: {active}", Style(dim=True)),
            _spacer(),
            border(
                render_adaptive(self._data, self._sim_w),
                chars=ROUNDED,
                style=Style(dim=True),
                title="services",
                title_style=current_palette().accent,
            ),
            _spacer(),
            Block.text("  ←/→ resize    q quit", Style(dim=True)),
        )
        body.paint(self._buf, 0, 0)

    def on_key(self, key: str) -> None:
        if key == "q":
            self.quit()
        elif key in ("left", "-", "h"):
            self._sim_w = max(_MIN_W, self._sim_w - 2)
            self.mark_dirty()
        elif key in ("right", "+", "l"):
            self._sim_w = min(self._term_w - 4, self._sim_w + 2)
            self.mark_dirty()


def _handle_interactive(ctx: CliContext) -> int:
    data = SAMPLE
    if not ctx.is_tty:
        print_block(_render(data, ctx.fidelity, None), use_ansi=ctx.use_ansi)
        return 0
    asyncio.run(TableSurface(data).run())
    return 0


def main() -> int:
    return run_cli(
        sys.argv[1:],
        renderer=_render,
        fetch=_fetch,
        handlers={OutputMode.INTERACTIVE: _handle_interactive},
        description=__doc__,
        prog="table.py",
    )


if __name__ == "__main__":
    sys.exit(main())
