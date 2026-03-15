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
import subprocess
import sys
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


def timed_cold_process(script: str, args: list[str]) -> float:
    env = os.environ.copy()
    env["COLUMNS"] = os.environ.get("COLUMNS", "140")
    env["LINES"] = os.environ.get("LINES", "40")
    t0 = perf_counter()
    proc = subprocess.run(
        [sys.executable, script, *args],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    elapsed = perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"cold process failed: script={script} args={args} code={proc.returncode} stderr={proc.stderr[-200:]}"
        )
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

cold_start_cases = [
    ("demos/patterns/responsive.py", ["-q", "--plain"]),
    ("demos/patterns/focus.py", ["-q", "--plain"]),
    ("demos/patterns/profiler.py", ["-q", "--plain"]),
    ("demos/patterns/live.py", ["--static", "-q", "--plain"]),
]


def run_warm_suite_once() -> dict[str, float]:
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


def run_cold_suite_once() -> dict[str, float]:
    cold_start = [timed_cold_process(script, args) for script, args in cold_start_cases]
    cold_import = timed_cold_process("-c", ["import painted"])  # full interpreter startup + painted import
    return {
        "cold_start_ms": mean(cold_start) * 1000.0,
        "cold_import_ms": cold_import * 1000.0,
    }


for _ in range(5):
    run_warm_suite_once()

warm_runs = 20
cold_runs = 5

warm_totals = {
    "pipeline_ms": 0.0,
    "responsive_ms": 0.0,
    "focus_ms": 0.0,
    "profiler_ms": 0.0,
    "live_static_ms": 0.0,
    "live_stream_ms": 0.0,
    "static_plain_ms": 0.0,
    "static_ansi_ms": 0.0,
}
cold_totals = {
    "cold_start_ms": 0.0,
    "cold_import_ms": 0.0,
}

for _ in range(warm_runs):
    sample = run_warm_suite_once()
    for k, v in sample.items():
        warm_totals[k] += v

for _ in range(cold_runs):
    sample = run_cold_suite_once()
    for k, v in sample.items():
        cold_totals[k] += v

for k, v in warm_totals.items():
    print(f"METRIC {k}={v / warm_runs:.3f}")
for k, v in cold_totals.items():
    print(f"METRIC {k}={v / cold_runs:.3f}")
PY
