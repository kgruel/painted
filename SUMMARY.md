# Import Surface Benchmark — 2026-03-15

## Status

Planned. Harness and correctness gate are in place; no benchmark result is
blessed yet.

## Question

How cheap are painted's most common entrypoints in a fresh interpreter now
that the package has real runtime layer boundaries and lazy top-level exports?

## Proposed Score

- **Primary:** `core_import_ms` — median child-process import time for
  `import painted.core`

## Secondary Scores

- `noop_process_ms` — subprocess baseline with no painted import
- `top_block_import_ms` — `from painted import Block, Style`
- `show_import_ms` — `from painted import show`
- `run_cli_import_ms` — `from painted import run_cli`
- `first_show_ms` — first plain `show({...})` call
- `first_help_ms` — first `run_cli(['--help'], ...)` call
- `*_wall_ms` — whole subprocess wall time, including interpreter startup
- `*_modules` — count of loaded `painted*` modules
- `*_peak_kib` — peak traced allocations during the scenario

## Why This Experiment

The frame-diff benchmark answers the steady-state rendering question.
This one answers the cold-start question for script users:

- does `painted.core` stay isolated?
- how much does the root facade cost?
- which first-use paths still pull in more than they need?

## Files

- `autoresearch.md` — experiment definition and constraints
- `autoresearch.sh` — benchmark harness
- `autoresearch.checks.sh` — correctness gate
- `autoresearch.ideas.md` — likely follow-on optimization paths
- `autoresearch.jsonl` — created on first run with aggregate results
