# Autoresearch: painted import-surface cold-start cost

## Objective
Optimize cold-start cost for common painted entrypoints in a fresh interpreter, without changing behavior or removing functionality. The workload measures process-isolated import and first-use scenarios so wins are real for script users and CLI callers.

## Metrics
- **Primary**: `core_import_ms` (ms, lower is better)
- **Secondary**: `noop_process_ms`, `top_block_import_ms`, `show_import_ms`, `run_cli_import_ms`, `first_show_ms`, `first_help_ms`, `*_wall_ms`, `*_modules`, `*_peak_kib`

## How to Run
`./autoresearch.sh` — emits `METRIC name=value` lines.

## Files in Scope
- `src/painted/__init__.py` — root export and lazy import surface
- `src/painted/core/__init__.py` — renderer-only import surface
- `src/painted/display.py` — first-use `show()` path
- `src/painted/cli/` — first-use `run_cli()` path
- `autoresearch.sh` — benchmark harness
- `autoresearch.checks.sh` — correctness gate
- `autoresearch.md` — session context and experiment history
- `autoresearch.ideas.md` — deferred ideas backlog

## Off Limits
- Benchmark dishonesty (mocking away real imports/paths, skipping real code paths)
- Changes that only optimize this harness while hurting general behavior
- Adding new runtime dependencies

## Constraints
- Do not overfit to a single scenario; keep all scenarios in the scorecard.
- Do not cheat on benchmarks; measure in fresh child processes.
- Preserve public API and behavior.
- Keep architecture boundaries intact.
- Validate correctness with targeted API-focused tests as changes land.

## What's Been Tried
- Initial setup: established isolated child-process cold-start harness with import/first-use scenarios and secondary visibility metrics.
