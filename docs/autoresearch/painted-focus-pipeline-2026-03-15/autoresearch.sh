#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

uv run python -m py_compile \
  demos/patterns/focus.py \
  src/painted/tui/testing.py \
  src/painted/core/buffer.py \
  src/painted/cli/runner.py \
  src/painted/cli/context.py

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
from demos.patterns import focus

os.environ.setdefault("COLUMNS", "140")
os.environ.setdefault("LINES", "40")

runner = CliRunner(
    render=focus._render,
    fetch=focus._fetch,
    description=getattr(focus, "__doc__", None),
    prog="focus.py",
)

cases = {
    "focus_minimal_ms": ["-q", "--plain"],
    "focus_summary_ms": [],
    "focus_full_ms": ["-vv"],
}

def timed_run(args: list[str]) -> float:
    sink = io.StringIO()
    t0 = perf_counter()
    with redirect_stdout(sink):
        code = runner.run(args)
    dt = perf_counter() - t0
    if code != 0:
        raise RuntimeError(f"focus runner failed: args={args} code={code}")
    return dt

def timed_cold_focus() -> float:
    env = os.environ.copy()
    env["COLUMNS"] = os.environ.get("COLUMNS", "140")
    env["LINES"] = os.environ.get("LINES", "40")
    t0 = perf_counter()
    proc = subprocess.run(
        [sys.executable, "demos/patterns/focus.py", "-q", "--plain"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        check=False,
    )
    dt = perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-200:])
    return dt

def timed_cold_import() -> float:
    t0 = perf_counter()
    proc = subprocess.run(
        [sys.executable, "-c", "import painted"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    dt = perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-200:])
    return dt

for _ in range(8):
    for args in cases.values():
        timed_run(args)

warm_runs = 30
cold_runs = 6

totals = {k: 0.0 for k in cases}
focus_total = 0.0
for _ in range(warm_runs):
    vals = {k: timed_run(args) for k, args in cases.items()}
    for k, v in vals.items():
        totals[k] += v
    focus_total += mean(vals.values())

cold_focus_total = 0.0
cold_import_total = 0.0
for _ in range(cold_runs):
    cold_focus_total += timed_cold_focus()
    cold_import_total += timed_cold_import()

print(f"METRIC focus_ms={(focus_total / warm_runs) * 1000.0:.3f}")
for k, v in totals.items():
    print(f"METRIC {k}={(v / warm_runs) * 1000.0:.3f}")
print(f"METRIC cold_focus_ms={(cold_focus_total / cold_runs) * 1000.0:.3f}")
print(f"METRIC cold_import_ms={(cold_import_total / cold_runs) * 1000.0:.3f}")
PY
