# Autoresearch: painted import surface and cold-start cost

## Objective

Measure the cold-start cost of painted's public entrypoints in fresh Python
interpreters. The goal is not just "make imports smaller", but to preserve the
new architectural boundary story in runtime terms:

- `import painted.core` should stay self-contained
- top-level eager primitives should remain cheap
- higher-layer entrypoints should only pay for the layer they expose
- first-use paths (`show`, `run_cli --help`) should be measurable and defendable

This complements the frame-diff benchmark. That experiment measures hot-path
render throughput; this one measures first-touch latency and import surface area.

## Metrics

- **Primary:** `core_import_ms` (ms, lower is better)
- **Secondary:**
  - `noop_process_ms`
  - `top_block_import_ms`
  - `show_import_ms`
  - `run_cli_import_ms`
  - `first_show_ms`
  - `first_help_ms`
  - matching `*_wall_ms` metrics
  - matching `*_modules` metrics
  - matching `*_peak_kib` metrics

`*_ms` is the median child-process scenario time. `*_wall_ms` includes the full
subprocess wall time so startup overhead stays visible.

## How to Run

`./autoresearch.sh`

Useful knobs:

- `REPEATS=11 ./autoresearch.sh` — increase sample count
- `LOG_JSONL=0 ./autoresearch.sh` — skip appending to `autoresearch.jsonl`
- `METRIC_TAG=branch-name ./autoresearch.sh` — annotate the log entry

## Scenarios

Each scenario runs in a fresh child Python process:

- `noop_process` — baseline subprocess with no painted import
- `core_import` — `import painted.core`
- `top_block_import` — `from painted import Block, Style`
- `show_import` — `from painted import show`
- `run_cli_import` — `from painted import run_cli`
- `first_show` — first `show({...}, format=Format.PLAIN)` call
- `first_help` — first `run_cli(['--help'], ...)` call

## Files in Scope

- `src/painted/__init__.py`
- `src/painted/core/__init__.py`
- `src/painted/core/zoom.py`
- `src/painted/display.py`
- `src/painted/cli/__init__.py`
- `src/painted/cli/runner.py`
- `src/painted/cli/help.py`
- `src/painted/views/__init__.py`
- `autoresearch.sh`
- `autoresearch.checks.sh`
- `autoresearch.md`
- `autoresearch.ideas.md`
- `SUMMARY.md`

## Off Limits

- Public API removals just to reduce import cost
- Benchmark-only shortcuts that bypass real entrypoints
- Reusing a warmed interpreter between scenarios
- Hiding architectural regressions behind cache-heavy parent-process setups

## Constraints

- Preserve current runtime behavior
- Keep `painted.core` isolated from `cli/`, `views/`, and `tui/`
- `./dev check` must pass for kept results
- Measure real child-process imports, not just in-process warm access
- Keep the benchmark honest: interpreter-cold, process-isolated scenarios

## Notes

- This benchmark is cold at the interpreter level, not at the OS page-cache
  level. Repeated runs still benefit from filesystem cache.
- Module-count and peak-allocation metrics are side signals. The decision
  metric is still latency.
