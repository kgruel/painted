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

from painted import CliContext, Zoom, Style, Block, join_horizontal, join_vertical, border, pad, truncate, Align, Wrap, ROUNDED
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
    alerts=tuple(replace(alert, message=alert.message + " — mitigation in progress") for alert in RESP_BASE.alerts),
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
    services_cursor=Cursor(index=4, count=len(SERVICES), mode=CursorMode.WRAP),
    search=SEARCH(query="rollback prod api", selected=2),
    last_command="rollback payments --env prod --force",
    last_event="capture search",
)

LOG_LINES_BASE = tuple(
    f"10:{10 + (i // 6):02d}:{(i * 7) % 60:02d}Z  svc=payments-api level={'WARN' if i % 9 == 0 else 'INFO'}  event={i:03d}  message=stream heartbeat seq={1000+i}"
    for i in range(28)
)
LOG_LINES_STREAM = LOG_LINES_BASE[1:] + (
    "10:15:31Z  svc=payments-api level=INFO  event=999  message=stream append ack=canary rollout healthy",
)
LOG_LINES_BURST = tuple(
    f"10:{20 + (i // 6):02d}:{(i * 11) % 60:02d}Z  svc={'worker' if i % 2 else 'payments-api'} level={'ERROR' if i % 5 == 0 else 'WARN'}  event={400+i:03d}  message=burst traffic window={i} status=retrying"
    for i in range(28)
)


def build_ctx(width: int, height: int) -> CliContext:
    return CliContext(
        zoom=Zoom.FULL,
        mode=OutputMode.STATIC,
        use_ansi=False,
        is_tty=False,
        width=width,
        height=height,
    )


def render_responsive(data, *, width: int, height: int) -> Block:
    return responsive.render_dashboard(build_ctx(width, height), data)


def render_focus(state, *, width: int, height: int) -> Block:
    gap = 1
    top_h = max(0, height - 1)
    left_w = max(22, min(30, (width - gap * 2) // 3))
    mid_w = max(22, min(30, (width - gap * 2) // 3))
    right_w = max(0, width - left_w - mid_w - gap * 2)
    if right_w < 22 and width >= 70:
        bump = 22 - right_w
        left_w = max(22, left_w - bump // 2)
        mid_w = max(22, mid_w - bump + bump // 2)
        right_w = max(0, width - left_w - mid_w - gap * 2)

    services = focus_demo._services_panel(state, width=left_w, height=top_h)
    search = focus_demo._search_panel(state, width=mid_w, height=top_h)
    details = focus_demo._details_panel(state, width=right_w, height=top_h)
    top = join_horizontal(services, search, details, gap=gap)
    status = f"focus={state.focus.id}:{'CAPTURE' if state.focus.captured else 'NAV'}   event={state.last_event or '—'}   q=quit"
    status_line = Block.text(status, focus_demo.current_palette().muted, width=width)
    return join_vertical(top, status_line)


def render_log_dashboard(data, logs: tuple[str, ...], *, width: int, height: int) -> Block:
    ctx = build_ctx(width, height)
    dashboard = responsive.render_dashboard(ctx, data)
    bordered = width >= 100
    outer_width = max(30, min(72, width // 3))
    inner_width = max(1, outer_width - 2) if bordered else outer_width
    log_rows = [
        Block.text(line, Style(dim=True), width=inner_width, wrap=Wrap.ELLIPSIS)
        for line in logs[: max(1, height - 6)]
    ]
    log_body = join_vertical(*log_rows, gap=0) if log_rows else Block.empty(inner_width, 0)
    if bordered:
        log_panel = border(
            pad(truncate(log_body, inner_width), left=1, right=1),
            chars=ROUNDED,
            style=Style(dim=True),
            title="Live Logs",
            title_style=responsive.current_palette().accent.merge(Style(bold=True)),
        )
    else:
        header = Block.text("  Live Logs", Style(dim=True), width=outer_width, wrap=Wrap.ELLIPSIS)
        log_panel = join_vertical(header, truncate(log_body, outer_width), gap=0)

    combined = join_horizontal(dashboard, log_panel, gap=2, align=Align.START)
    return truncate(combined, width)


def frame_pass(render_fn, current_data, previous_data, *, width: int, height: int):
    t0 = perf_counter()
    current_block = render_fn(current_data, width=width, height=height)
    previous_block = render_fn(previous_data, width=width, height=height)
    t1 = perf_counter()
    current = Buffer(width, height)
    previous = Buffer(width, height)
    current_block.paint(current)
    previous_block.paint(previous)
    t2 = perf_counter()
    writes = current.diff(previous)
    t3 = perf_counter()
    return (t1 - t0), (t2 - t1), (t3 - t2), len(writes)


def render_log_frame(payload, *, width: int, height: int):
    data, logs = payload
    return render_log_dashboard(data, logs, width=width, height=height)


def make_diff_pair(width: int, height: int, change_stride: int | None) -> tuple[Buffer, Buffer]:
    a = Buffer(width, height)
    b = Buffer(width, height)
    base = Style(dim=True)
    hot = Style(fg="cyan", bold=True)
    fill = Block.text("x" * width, base, width=width)
    for y in range(height):
        fill.paint(a, 0, y)
        fill.paint(b, 0, y)
    if change_stride is None:
        return a, b
    for idx in range(0, width * height, change_stride):
        x = idx % width
        y = idx // width
        if y >= height:
            break
        b.put(x, y, "#", hot)
    return a, b

LARGE = (225, 60)
SMALL = (140, 40)
DIFF_W, DIFF_H = LARGE
STATIC_A, STATIC_B = make_diff_pair(DIFF_W, DIFF_H, None)
SPARSE_A, SPARSE_B = make_diff_pair(DIFF_W, DIFF_H, 521)
DENSE_A, DENSE_B = make_diff_pair(DIFF_W, DIFF_H, 3)


def diff_only_pass(left: Buffer, right: Buffer):
    t0 = perf_counter()
    writes = right.diff(left)
    t1 = perf_counter()
    return (t1 - t0), len(writes)


def suite_pass(width: int, height: int):
    totals = {"render": 0.0, "paint": 0.0, "diff": 0.0}
    counts = {}

    scenarios = [
        ("responsive", render_responsive, RESP_BASE, RESP_BASE, "resp_static"),
        ("responsive", render_responsive, RESP_SPARSE, RESP_BASE, "resp_sparse"),
        ("responsive", render_responsive, RESP_CHURN, RESP_BASE, "resp_churn"),
        ("focus", render_focus, FOCUS_BASE, FOCUS_BASE, "focus_static"),
        ("focus", render_focus, FOCUS_SPARSE, FOCUS_BASE, "focus_sparse"),
        ("focus", render_focus, FOCUS_CHURN, FOCUS_BASE, "focus_churn"),
        ("log", render_log_frame, (RESP_BASE, LOG_LINES_BASE), (RESP_BASE, LOG_LINES_BASE), "log_static"),
        ("log", render_log_frame, (RESP_BASE, LOG_LINES_STREAM), (RESP_BASE, LOG_LINES_BASE), "log_stream"),
        ("log", render_log_frame, (RESP_CHURN, LOG_LINES_BURST), (RESP_BASE, LOG_LINES_BASE), "log_burst"),
    ]

    start = perf_counter()
    for kind, render_fn, current, previous, bucket in scenarios:
        r, p, d, c = frame_pass(render_fn, current, previous, width=width, height=height)
        totals["render"] += r
        totals["paint"] += p
        totals["diff"] += d
        counts[bucket] = c
        totals.setdefault(kind, 0.0)
        totals[kind] += r + p + d
    elapsed = perf_counter() - start
    totals["elapsed"] = elapsed
    totals["counts"] = counts
    return totals


for _ in range(20):
    suite_pass(*LARGE)
    suite_pass(*SMALL)
    diff_only_pass(STATIC_A, STATIC_B)
    diff_only_pass(SPARSE_A, SPARSE_B)
    diff_only_pass(DENSE_A, DENSE_B)

runs = 80
large_elapsed = small_elapsed = 0.0
large_render = small_render = 0.0
large_paint = small_paint = 0.0
large_diff = small_diff = 0.0
large_resp = small_resp = 0.0
large_focus = small_focus = 0.0
large_log = small_log = 0.0
diff_only_total = 0.0

for _ in range(runs):
    large = suite_pass(*LARGE)
    small = suite_pass(*SMALL)
    large_elapsed += large["elapsed"]
    small_elapsed += small["elapsed"]
    large_render += large["render"]
    small_render += small["render"]
    large_paint += large["paint"]
    small_paint += small["paint"]
    large_diff += large["diff"]
    small_diff += small["diff"]
    large_resp += large["responsive"]
    small_resp += small["responsive"]
    large_focus += large["focus"]
    small_focus += small["focus"]
    large_log += large["log"]
    small_log += small["log"]

    for left, right in ((STATIC_A, STATIC_B), (SPARSE_A, SPARSE_B), (DENSE_A, DENSE_B)):
        d, _ = diff_only_pass(left, right)
        diff_only_total += d

large_frame_count = runs * 9
small_frame_count = runs * 9
frame_ms = (large_elapsed * 1000.0) / large_frame_count
frame_ms_small = (small_elapsed * 1000.0) / small_frame_count
render_ms = ((large_render + small_render) * 1000.0) / (large_frame_count + small_frame_count)
paint_ms = ((large_paint + small_paint) * 1000.0) / (large_frame_count + small_frame_count)
diff_ms = ((large_diff + small_diff) * 1000.0) / (large_frame_count + small_frame_count)
responsive_large_ms = (large_resp * 1000.0) / (runs * 3)
responsive_small_ms = (small_resp * 1000.0) / (runs * 3)
focus_large_ms = (large_focus * 1000.0) / (runs * 3)
focus_small_ms = (small_focus * 1000.0) / (runs * 3)
log_dashboard_large_ms = (large_log * 1000.0) / (runs * 3)
log_dashboard_small_ms = (small_log * 1000.0) / (runs * 3)
diff_only_ms = (diff_only_total * 1000.0) / (runs * 3)

print(f"METRIC frame_ms={frame_ms:.3f}")
print(f"METRIC frame_ms_small={frame_ms_small:.3f}")
print(f"METRIC responsive_large_ms={responsive_large_ms:.3f}")
print(f"METRIC responsive_small_ms={responsive_small_ms:.3f}")
print(f"METRIC focus_large_ms={focus_large_ms:.3f}")
print(f"METRIC focus_small_ms={focus_small_ms:.3f}")
print(f"METRIC log_dashboard_large_ms={log_dashboard_large_ms:.3f}")
print(f"METRIC log_dashboard_small_ms={log_dashboard_small_ms:.3f}")
print(f"METRIC diff_only_ms={diff_only_ms:.3f}")
print(f"METRIC render_ms={render_ms:.3f}")
print(f"METRIC paint_ms={paint_ms:.3f}")
print(f"METRIC diff_ms={diff_ms:.3f}")
PY
