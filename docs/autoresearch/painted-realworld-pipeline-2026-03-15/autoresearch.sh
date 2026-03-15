#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

uv run python -m py_compile \
  src/painted/cli/runner.py \
  src/painted/cli/context.py \
  src/painted/inplace.py \
  demos/patterns/responsive.py \
  demos/patterns/focus.py \
  demos/patterns/profiler.py \
  demos/patterns/live.py

uv run python - <<'PY'
from __future__ import annotations

import io
import os
from contextlib import redirect_stdout
from statistics import mean
from time import perf_counter

from painted.cli.runner import CliRunner

from demos.patterns import responsive, focus, profiler, live


os.environ.setdefault("COLUMNS", "140")
os.environ.setdefault("LINES", "40")


def make_runner(mod, *, stream: bool = False) -> CliRunner:
    return CliRunner(
        render=mod._render,
        fetch=mod._fetch,
        fetch_stream=(mod._fetch_stream if stream else None),
        description=getattr(mod, "__doc__", None),
        prog=f"{mod.__name__.split('.')[-1]}.py",
    )


def timed_run(runner: CliRunner, args: list[str]) -> float:
    sink = io.StringIO()
    t0 = perf_counter()
    with redirect_stdout(sink):
        code = runner.run(args)
    elapsed = perf_counter() - t0
    if code != 0:
        raise RuntimeError(f"runner failed: args={args} code={code}")
    return elapsed


# speed up live stream demo deterministically (no wall sleeps)
live.OUTCOMES = {k: (0.0, s, d) for k, (_, s, d) in live.OUTCOMES.items()}

responsive_runner = make_runner(responsive)
focus_runner = make_runner(focus)
profiler_runner = make_runner(profiler)
live_static_runner = make_runner(live)
live_stream_runner = make_runner(live, stream=True)

responsive_cases = [
    ["-q", "--plain"],
    ["-v"],
    ["-vv"],
]
focus_cases = [
    ["-q", "--plain"],
    [],
    ["-vv"],
]
profiler_cases = [
    ["-q", "--plain"],
    ["-v"],
    ["-vv"],
]
live_static_cases = [
    ["-q", "--plain"],
    ["-v"],
]
live_stream_cases = [
    ["--live", "-q", "--plain"],
]


def run_suite_once() -> dict[str, float]:
    responsive_t = [timed_run(responsive_runner, c) for c in responsive_cases]
    focus_t = [timed_run(focus_runner, c) for c in focus_cases]
    profiler_t = [timed_run(profiler_runner, c) for c in profiler_cases]
    live_static_t = [timed_run(live_static_runner, c) for c in live_static_cases]
    live_stream_t = [timed_run(live_stream_runner, c) for c in live_stream_cases]

    static_plain = [
        responsive_t[0],
        focus_t[0],
        profiler_t[0],
        live_static_t[0],
        live_stream_t[0],
    ]
    static_ansi = [
        responsive_t[1], responsive_t[2],
        focus_t[1], focus_t[2],
        profiler_t[1], profiler_t[2],
        live_static_t[1],
    ]

    all_scenarios = responsive_t + focus_t + profiler_t + live_static_t + live_stream_t

    return {
        "pipeline_ms": mean(all_scenarios) * 1000.0,
        "responsive_ms": mean(responsive_t) * 1000.0,
        "focus_ms": mean(focus_t) * 1000.0,
        "profiler_ms": mean(profiler_t) * 1000.0,
        "live_static_ms": mean(live_static_t) * 1000.0,
        "live_stream_ms": mean(live_stream_t) * 1000.0,
        "static_plain_ms": mean(static_plain) * 1000.0,
        "static_ansi_ms": mean(static_ansi) * 1000.0,
    }


for _ in range(5):
    run_suite_once()

runs = 20
totals = {
    "pipeline_ms": 0.0,
    "responsive_ms": 0.0,
    "focus_ms": 0.0,
    "profiler_ms": 0.0,
    "live_static_ms": 0.0,
    "live_stream_ms": 0.0,
    "static_plain_ms": 0.0,
    "static_ansi_ms": 0.0,
}

for _ in range(runs):
    sample = run_suite_once()
    for k, v in sample.items():
        totals[k] += v

for k, v in totals.items():
    print(f"METRIC {k}={v / runs:.3f}")
PY
