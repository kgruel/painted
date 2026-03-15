#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR"

cd "$REPO_ROOT"

REPEATS="${REPEATS:-7}"
LOG_JSONL="${LOG_JSONL:-1}"
METRIC_TAG="${METRIC_TAG:-manual}"

REPO_ROOT="$REPO_ROOT" \
SCRIPT_DIR="$SCRIPT_DIR" \
REPEATS="$REPEATS" \
LOG_JSONL="$LOG_JSONL" \
METRIC_TAG="$METRIC_TAG" \
uv run python - <<'PY'
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import textwrap
from pathlib import Path
from time import perf_counter

repo_root = Path(os.environ["REPO_ROOT"])
script_dir = Path(os.environ["SCRIPT_DIR"])
repeats = int(os.environ["REPEATS"])
log_jsonl = os.environ["LOG_JSONL"] not in {"0", "false", "False"}
metric_tag = os.environ["METRIC_TAG"]

env = os.environ.copy()
py_path = str(repo_root / "src")
if env.get("PYTHONPATH"):
    env["PYTHONPATH"] = py_path + os.pathsep + env["PYTHONPATH"]
else:
    env["PYTHONPATH"] = py_path
env["PYTHONHASHSEED"] = "0"


def _scenario_code(payload: str) -> str:
    return textwrap.dedent(
        f"""
        from __future__ import annotations

        import json
        import sys
        import tracemalloc
        from time import perf_counter

        tracemalloc.start()
        t0 = perf_counter()
        {textwrap.indent(payload, "        ").lstrip()}
        t1 = perf_counter()

        modules = sorted(
            name for name in sys.modules if name == "painted" or name.startswith("painted.")
        )
        _, peak = tracemalloc.get_traced_memory()

        print(
            json.dumps(
                {{
                    "child_ms": (t1 - t0) * 1000.0,
                    "painted_module_count": len(modules),
                    "painted_modules": modules,
                    "peak_kib": peak / 1024.0,
                }}
            )
        )
        """
    )


SCENARIOS: list[tuple[str, str]] = [
    ("noop_process", "pass"),
    ("core_import", "import painted.core"),
    ("top_block_import", "from painted import Block, Style"),
    ("show_import", "from painted import show"),
    ("run_cli_import", "from painted import run_cli"),
    (
        "first_show",
        """
import io

from painted import Format, show

show({"service": "api", "status": "ok"}, format=Format.PLAIN, file=io.StringIO())
        """.strip(),
    ),
    (
        "first_help",
        """
import contextlib
import io

from painted import Block, Style, run_cli

buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    run_cli(
        ["--help"],
        render=lambda ctx, data: Block.text("ok", Style()),
        fetch=lambda: "data",
    )
        """.strip(),
    ),
]


def run_scenario(name: str, payload: str) -> dict[str, object]:
    child_samples: list[float] = []
    wall_samples: list[float] = []
    peak_samples: list[float] = []
    module_counts: list[int] = []
    module_list: list[str] = []

    code = _scenario_code(payload)

    for _ in range(repeats):
        t0 = perf_counter()
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        t1 = perf_counter()
        result = json.loads(proc.stdout.strip())

        child_samples.append(result["child_ms"])
        wall_samples.append((t1 - t0) * 1000.0)
        peak_samples.append(result["peak_kib"])
        module_counts.append(result["painted_module_count"])
        module_list = result["painted_modules"]

    return {
        "scenario": name,
        "child_ms": statistics.median(child_samples),
        "wall_ms": statistics.median(wall_samples),
        "peak_kib": statistics.median(peak_samples),
        "painted_modules": statistics.median(module_counts),
        "module_names": module_list,
        "samples": repeats,
    }


rows = [run_scenario(name, payload) for name, payload in SCENARIOS]
by_name = {row["scenario"]: row for row in rows}

for row in rows:
    name = row["scenario"]
    print(
        "SCENARIO"
        f" {name}"
        f" child_ms={row['child_ms']:.3f}"
        f" wall_ms={row['wall_ms']:.3f}"
        f" modules={int(row['painted_modules'])}"
        f" peak_kib={row['peak_kib']:.1f}"
    )

metric_order = [
    "noop_process",
    "core_import",
    "top_block_import",
    "show_import",
    "run_cli_import",
    "first_show",
    "first_help",
]

for name in metric_order:
    row = by_name[name]
    print(f"METRIC {name}_ms={row['child_ms']:.6f}")
    print(f"METRIC {name}_wall_ms={row['wall_ms']:.6f}")
    print(f"METRIC {name}_modules={int(row['painted_modules'])}")
    print(f"METRIC {name}_peak_kib={row['peak_kib']:.6f}")

if log_jsonl:
    try:
        rev = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
        )
    except subprocess.CalledProcessError:
        rev = "unknown"

    log_record = {
        "tag": metric_tag,
        "git_rev": rev,
        "repeats": repeats,
        "results": rows,
    }
    log_path = script_dir / "autoresearch.jsonl"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(log_record, sort_keys=True))
        fh.write("\n")

    print(f"LOG {log_path}")
PY
