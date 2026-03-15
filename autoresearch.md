# Autoresearch: painted first_show cold-start latency

## Objective
Optimize `first_show_ms`: the first real `show({...}, format='plain')` call in a fresh interpreter.

The benchmark remains multi-scenario to prevent overfitting: we keep import-only and other first-use paths (`core_import`, `show_import`, `run_cli_import`, `first_help`) visible while optimizing first-show latency.

## Metrics
- **Primary**: `first_show_ms` (ms, lower is better)
- **Secondary**: `noop_process_ms`, `core_import_ms`, `top_block_import_ms`, `show_import_ms`, `run_cli_import_ms`, `first_help_ms`, `*_wall_ms`, `*_modules`, `*_peak_kib`

## How to Run
`./autoresearch.sh` — emits `METRIC name=value` lines.

## Files in Scope
- `src/painted/display.py` — `show()` first-use path
- `src/painted/__init__.py` — root lazy surface
- `src/painted/views/` — first lens import path if benchmark-backed
- `src/painted/cli/` — context-detect overhead if benchmark-backed
- `autoresearch.sh`, `autoresearch.md`, `autoresearch.ideas.md`

## Off Limits
- Benchmark dishonesty (shortcuts that avoid real first-show behavior)
- Behavior/API changes for `show()`
- New dependencies

## Constraints
- Fresh child process per sample (already enforced by harness)
- Keep all scenarios in scorecard to avoid overfitting
- Do not cheat on benchmark semantics
- Preserve architecture boundaries

## What's Been Tried
- Previous session heavily reduced import cost via lazy root/core exports.
- New target: first-use show path, likely dominated by display + lens import/render pipeline.
