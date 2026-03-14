#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

uv run python -m py_compile src/painted/block.py src/painted/buffer.py src/painted/compose.py demos/patterns/responsive.py demos/patterns/focus.py

uv run python - <<'PY'
from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from painted import CliContext, Zoom, Style, Block, join_horizontal, join_vertical
from painted.buffer import Buffer
from painted.cursor import Cursor, CursorMode
from painted.fidelity import OutputMode
from painted.focus import Focus


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, Path(path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

responsive = load_module("responsive_bench", "demos/patterns/responsive.py")
focus_demo = load_module("focus_bench", "demos/patterns/focus.py")

WIDTH = 120
HEIGHT = 36
CTX = CliContext(
    zoom=Zoom.FULL,
    mode=OutputMode.STATIC,
    use_ansi=False,
    is_tty=False,
    width=WIDTH,
    height=HEIGHT,
)

RESP_BASE = responsive.SAMPLE
RESP_SPARSE = replace(
    RESP_BASE,
    run_id="run-59382",
    stages=tuple(
        replace(stage, duration_s=stage.duration_s + 1) if i == 2 else stage
        for i, stage in enumerate(RESP_BASE.stages)
    ),
    deploys=tuple(
        replace(dep, duration_s=dep.duration_s + 1) if i == 0 else dep
        for i, dep in enumerate(RESP_BASE.deploys)
    ),
)
RESP_CHURN = replace(
    RESP_BASE,
    branch="release/2026-03-hotfix",
    commit="9fd13ac",
    run_id="run-59399",
    stages=tuple(
        replace(
            stage,
            status=("failed" if stage.status == "running" else "running" if stage.status == "queued" else stage.status),
            owner="ops-bot" if i % 2 == 0 else stage.owner,
            jobs=tuple(
                replace(
                    job,
                    status=("failed" if job.status == "running" else "success" if job.status == "queued" else job.status),
                    duration_s=job.duration_s + 7 + j,
                    note=(job.note + " / escalated") if job.note else "manual intervention required",
                    logs=job.logs + (("human ack pending",) if job.logs else tuple()),
                )
                for j, job in enumerate(stage.jobs)
            ),
        )
        for i, stage in enumerate(RESP_BASE.stages)
    ),
    alerts=tuple(
        replace(alert, message=alert.message + " — mitigation in progress")
        for alert in RESP_BASE.alerts
    ),
)

SERVICES = focus_demo.SERVICES
SEARCH = focus_demo.Search
APP = focus_demo.AppState

FOCUS_BASE = APP(
    focus=Focus(id="services", captured=False),
    services_cursor=Cursor(index=1, count=len(SERVICES), mode=CursorMode.WRAP),
    search=SEARCH(query="deploy", selected=1),
    last_command="deploy payments --canary",
    last_event="focus services",
)
FOCUS_SPARSE = replace(
    FOCUS_BASE,
    services_cursor=Cursor(index=2, count=len(SERVICES), mode=CursorMode.WRAP),
    last_event="cursor+1",
)
FOCUS_CHURN = replace(
    FOCUS_BASE,
    focus=Focus(id="search", captured=True),
    services_cursor=Cursor(index=4, count=len(SERVICES)),
    search=SEARCH(query="rollback prod api", selected=2),
    last_command="rollback payments --env prod --force",
    last_event="capture search",
)


def render_responsive(data):
    return responsive.render_dashboard(CTX, data)


def render_focus(state):
    gap = 1
    w = WIDTH
    top_h = max(0, HEIGHT - 1)
    left_w = max(22, min(30, (w - gap * 2) // 3))
    mid_w = max(22, min(30, (w - gap * 2) // 3))
    right_w = max(0, w - left_w - mid_w - gap * 2)
    if right_w < 22 and w >= 70:
        bump = 22 - right_w
        left_w = max(22, left_w - bump // 2)
        mid_w = max(22, mid_w - bump + bump // 2)
        right_w = max(0, w - left_w - mid_w - gap * 2)

    services = focus_demo._services_panel(state, width=left_w, height=top_h)
    search = focus_demo._search_panel(state, width=mid_w, height=top_h)
    details = focus_demo._details_panel(state, width=right_w, height=top_h)
    top = join_horizontal(services, search, details, gap=gap)
    status = f"focus={state.focus.id}:{'CAPTURE' if state.focus.captured else 'NAV'}   event={state.last_event or '—'}   q=quit"
    status_line = Block.text(status, focus_demo.current_palette().muted, width=WIDTH)
    return join_vertical(top, status_line)


def frame_pass(render_fn, current_data, previous_data):
    t0 = perf_counter()
    current_block = render_fn(current_data)
    previous_block = render_fn(previous_data)
    t1 = perf_counter()
    current = Buffer(WIDTH, HEIGHT)
    previous = Buffer(WIDTH, HEIGHT)
    current_block.paint(current)
    previous_block.paint(previous)
    t2 = perf_counter()
    writes = current.diff(previous)
    t3 = perf_counter()
    return (t1 - t0), (t2 - t1), (t3 - t2), len(writes)


def make_diff_pair(change_stride: int | None) -> tuple[Buffer, Buffer]:
    a = Buffer(WIDTH, HEIGHT)
    b = Buffer(WIDTH, HEIGHT)
    base = Style(dim=True)
    hot = Style(fg="cyan", bold=True)
    fill = Block.text("x" * WIDTH, base, width=WIDTH)
    for y in range(HEIGHT):
        fill.paint(a, 0, y)
        fill.paint(b, 0, y)
    if change_stride is None:
        return a, b
    for idx in range(0, WIDTH * HEIGHT, change_stride):
        x = idx % WIDTH
        y = idx // WIDTH
        if y >= HEIGHT:
            break
        b.put(x, y, "#", hot)
    return a, b

STATIC_A, STATIC_B = make_diff_pair(None)
SPARSE_A, SPARSE_B = make_diff_pair(211)
DENSE_A, DENSE_B = make_diff_pair(3)


def diff_only_pass(left: Buffer, right: Buffer):
    t0 = perf_counter()
    writes = right.diff(left)
    t1 = perf_counter()
    return (t1 - t0), len(writes)


for _ in range(30):
    frame_pass(render_responsive, RESP_BASE, RESP_BASE)
    frame_pass(render_responsive, RESP_SPARSE, RESP_BASE)
    frame_pass(render_responsive, RESP_CHURN, RESP_BASE)
    frame_pass(render_focus, FOCUS_BASE, FOCUS_BASE)
    frame_pass(render_focus, FOCUS_SPARSE, FOCUS_BASE)
    frame_pass(render_focus, FOCUS_CHURN, FOCUS_BASE)
    diff_only_pass(STATIC_A, STATIC_B)
    diff_only_pass(SPARSE_A, SPARSE_B)
    diff_only_pass(DENSE_A, DENSE_B)

runs = 150
render_total = 0.0
paint_total = 0.0
diff_total = 0.0
responsive_total = 0.0
focus_total = 0.0
diff_only_total = 0.0
resp_static = resp_sparse = resp_churn = 0
focus_static = focus_sparse = focus_churn = 0
diff_static = diff_sparse = diff_dense = 0

start = perf_counter()
for _ in range(runs):
    for current, previous, bucket in (
        (RESP_BASE, RESP_BASE, "resp_static"),
        (RESP_SPARSE, RESP_BASE, "resp_sparse"),
        (RESP_CHURN, RESP_BASE, "resp_churn"),
    ):
        r, p, d, c = frame_pass(render_responsive, current, previous)
        render_total += r; paint_total += p; diff_total += d; responsive_total += r + p + d
        if bucket == "resp_static": resp_static += c
        elif bucket == "resp_sparse": resp_sparse += c
        else: resp_churn += c

    for current, previous, bucket in (
        (FOCUS_BASE, FOCUS_BASE, "focus_static"),
        (FOCUS_SPARSE, FOCUS_BASE, "focus_sparse"),
        (FOCUS_CHURN, FOCUS_BASE, "focus_churn"),
    ):
        r, p, d, c = frame_pass(render_focus, current, previous)
        render_total += r; paint_total += p; diff_total += d; focus_total += r + p + d
        if bucket == "focus_static": focus_static += c
        elif bucket == "focus_sparse": focus_sparse += c
        else: focus_churn += c

    for left, right, bucket in (
        (STATIC_A, STATIC_B, "diff_static"),
        (SPARSE_A, SPARSE_B, "diff_sparse"),
        (DENSE_A, DENSE_B, "diff_dense"),
    ):
        d, c = diff_only_pass(left, right)
        diff_only_total += d
        if bucket == "diff_static": diff_static += c
        elif bucket == "diff_sparse": diff_sparse += c
        else: diff_dense += c
end = perf_counter()

frame_count = runs * 6
frame_ms = ((end - start) * 1000.0) / (frame_count + runs * 3)
render_ms = (render_total * 1000.0) / frame_count
paint_ms = (paint_total * 1000.0) / frame_count
diff_ms = (diff_total * 1000.0) / frame_count
responsive_frame_ms = (responsive_total * 1000.0) / (runs * 3)
focus_frame_ms = (focus_total * 1000.0) / (runs * 3)
diff_only_ms = (diff_only_total * 1000.0) / (runs * 3)

print(f"METRIC frame_ms={frame_ms:.3f}")
print(f"METRIC responsive_frame_ms={responsive_frame_ms:.3f}")
print(f"METRIC focus_frame_ms={focus_frame_ms:.3f}")
print(f"METRIC diff_only_ms={diff_only_ms:.3f}")
print(f"METRIC render_ms={render_ms:.3f}")
print(f"METRIC paint_ms={paint_ms:.3f}")
print(f"METRIC diff_ms={diff_ms:.3f}")
print(f"METRIC diff_cells_static={resp_static / runs:.1f}")
print(f"METRIC diff_cells_sparse={resp_sparse / runs:.1f}")
print(f"METRIC diff_cells_churn={resp_churn / runs:.1f}")
print(f"METRIC focus_diff_cells_sparse={focus_sparse / runs:.1f}")
print(f"METRIC focus_diff_cells_churn={focus_churn / runs:.1f}")
print(f"METRIC diff_only_cells_static={diff_static / runs:.1f}")
print(f"METRIC diff_only_cells_sparse={diff_sparse / runs:.1f}")
print(f"METRIC diff_only_cells_dense={diff_dense / runs:.1f}")
PY
