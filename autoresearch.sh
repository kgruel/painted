#!/bin/bash
set -euo pipefail

uv run python - <<'PY'
from __future__ import annotations

import statistics
import subprocess
import textwrap
from pathlib import Path

ROOT = Path.cwd()
RUNS = 11

SCENARIOS: dict[str, str] = {
    "noop_process": "pass",
    "core_import": "import painted.core",
    "top_block_import": "from painted import Block, Style",
    "show_import": "from painted import show",
    "run_cli_import": "from painted import run_cli",
    "first_show": textwrap.dedent(
        """
        from painted import show
        show({"ok": True}, format="plain")
        """
    ),
    "first_help": textwrap.dedent(
        """
        from painted import Block, run_cli
        run_cli(["--help"], render=lambda ctx, state: Block.text("ok"), fetch=lambda: {})
        """
    ),
}

TEMPLATE = textwrap.dedent(
    """
    import importlib
    import json
    import time
    import tracemalloc

    tracemalloc.start()
    t0 = time.perf_counter()
    {snippet}
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    _, peak = tracemalloc.get_traced_memory()
    modules = sum(1 for name in list(importlib.sys.modules) if name == 'painted' or name.startswith('painted.'))
    print(json.dumps({{"elapsed_ms": elapsed_ms, "modules": modules, "peak_kib": peak / 1024.0}}))
    """
)


def run_once(snippet: str) -> tuple[float, float, int, float]:
    program = TEMPLATE.format(snippet=snippet)
    wall_start = __import__("time").perf_counter()
    proc = subprocess.run(
        ["uv", "run", "python", "-c", program],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    wall_ms = (__import__("time").perf_counter() - wall_start) * 1000.0
    import json

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    payload = json.loads(lines[-1])
    return payload["elapsed_ms"], wall_ms, payload["modules"], payload["peak_kib"]


results: dict[str, dict[str, float]] = {}

for name, snippet in SCENARIOS.items():
    elapsed_samples: list[float] = []
    wall_samples: list[float] = []
    modules_samples: list[int] = []
    peak_samples: list[float] = []

    for _ in range(RUNS):
        elapsed_ms, wall_ms, modules, peak_kib = run_once(snippet)
        elapsed_samples.append(elapsed_ms)
        wall_samples.append(wall_ms)
        modules_samples.append(modules)
        peak_samples.append(peak_kib)

    results[name] = {
        "ms": statistics.median(elapsed_samples),
        "wall_ms": statistics.median(wall_samples),
        "modules": float(statistics.median(modules_samples)),
        "peak_kib": statistics.median(peak_samples),
    }

print(f"METRIC core_import_ms={results['core_import']['ms']:.3f}")
for name in SCENARIOS:
    print(f"METRIC {name}_ms={results[name]['ms']:.3f}")
    print(f"METRIC {name}_wall_ms={results[name]['wall_ms']:.3f}")
    print(f"METRIC {name}_modules={results[name]['modules']:.0f}")
    print(f"METRIC {name}_peak_kib={results[name]['peak_kib']:.1f}")
PY
