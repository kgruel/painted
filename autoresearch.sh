#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

uv run python -m py_compile src/painted/block.py src/painted/buffer.py src/painted/compose.py demos/patterns/responsive.py

uv run python - <<'PY'
from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from painted import CliContext, Zoom
from painted.buffer import Buffer
from painted.fidelity import OutputMode

spec = importlib.util.spec_from_file_location(
    "responsive_bench", Path("demos/patterns/responsive.py")
)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

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
BASE = mod.SAMPLE

SPARSE = replace(
    BASE,
    run_id="run-59382",
    stages=tuple(
        replace(stage, duration_s=stage.duration_s + 1) if i == 2 else stage
        for i, stage in enumerate(BASE.stages)
    ),
    deploys=tuple(
        replace(dep, duration_s=dep.duration_s + 1) if i == 0 else dep
        for i, dep in enumerate(BASE.deploys)
    ),
)

CHURN = replace(
    BASE,
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
        for i, stage in enumerate(BASE.stages)
    ),
    alerts=tuple(
        replace(alert, message=alert.message + " — mitigation in progress")
        for alert in BASE.alerts
    ),
)


def render(data):
    return mod.render_dashboard(CTX, data)


def paint_and_diff(current_data, previous_data):
    t0 = perf_counter()
    current_block = render(current_data)
    previous_block = render(previous_data)
    t1 = perf_counter()

    current = Buffer(WIDTH, HEIGHT)
    previous = Buffer(WIDTH, HEIGHT)
    current_block.paint(current)
    previous_block.paint(previous)
    t2 = perf_counter()

    writes = current.diff(previous)
    t3 = perf_counter()
    return (t1 - t0), (t2 - t1), (t3 - t2), len(writes)


for _ in range(50):
    paint_and_diff(BASE, BASE)
    paint_and_diff(SPARSE, BASE)
    paint_and_diff(CHURN, BASE)

runs = 250
render_total = 0.0
paint_total = 0.0
diff_total = 0.0
static_cells = 0
sparse_cells = 0
churn_cells = 0

start = perf_counter()
for _ in range(runs):
    r, p, d, c = paint_and_diff(BASE, BASE)
    render_total += r
    paint_total += p
    diff_total += d
    static_cells += c

    r, p, d, c = paint_and_diff(SPARSE, BASE)
    render_total += r
    paint_total += p
    diff_total += d
    sparse_cells += c

    r, p, d, c = paint_and_diff(CHURN, BASE)
    render_total += r
    paint_total += p
    diff_total += d
    churn_cells += c
end = perf_counter()

total_frames = runs * 3
frame_ms = ((end - start) * 1000.0) / total_frames
render_ms = (render_total * 1000.0) / total_frames
paint_ms = (paint_total * 1000.0) / total_frames
diff_ms = (diff_total * 1000.0) / total_frames

print(f"METRIC frame_ms={frame_ms:.3f}")
print(f"METRIC render_ms={render_ms:.3f}")
print(f"METRIC paint_ms={paint_ms:.3f}")
print(f"METRIC diff_ms={diff_ms:.3f}")
print(f"METRIC diff_cells_static={static_cells / runs:.1f}")
print(f"METRIC diff_cells_sparse={sparse_cells / runs:.1f}")
print(f"METRIC diff_cells_churn={churn_cells / runs:.1f}")
PY
