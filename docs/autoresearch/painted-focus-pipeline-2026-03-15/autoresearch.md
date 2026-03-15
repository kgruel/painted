# Autoresearch: painted focus-path pipeline

## Objective
Optimize the focus demo end-to-end path as the new primary target. This isolates the dominant hotspot seen in the prior real-world suite (`focus_ms`) while still exercising realistic run_cli + TestSurface behavior across multiple zoom levels.

## Metrics
- **Primary**: `focus_ms` (ms, lower is better)
- **Secondary**: `focus_minimal_ms`, `focus_summary_ms`, `focus_full_ms`, `cold_focus_ms`, `cold_import_ms`

## How to Run
`./docs/autoresearch/painted-focus-pipeline-2026-03-15/autoresearch.sh`

## Files in Scope
- `demos/patterns/focus.py` — primary workload logic
- `src/painted/tui/testing.py` — TestSurface harness internals
- `src/painted/core/buffer.py` — clone/diff path used by harness
- `src/painted/cli/runner.py` — run_cli overhead
- `src/painted/cli/context.py` — context detection overhead
- `docs/autoresearch/painted-focus-pipeline-2026-03-15/autoresearch.sh`
- `docs/autoresearch/painted-focus-pipeline-2026-03-15/autoresearch.checks.sh`
- `docs/autoresearch/painted-focus-pipeline-2026-03-15/autoresearch.md`
- `docs/autoresearch/painted-focus-pipeline-2026-03-15/autoresearch.ideas.md`

## Off Limits
- Public API changes
- New dependencies
- Benchmark shortcuts that bypass real focus demo behavior

## Constraints
- Preserve behavior and output semantics
- `./dev check` must pass for kept results
- Keep benchmark deterministic (fixed dimensions, deterministic scenario input)

## What's Been Tried
- New target created from retrospective: prior full-suite work plateaued at `pipeline_ms=6.919` and identified focus path as dominant remaining cost.
- Baseline established at `focus_ms=16.177`.
- Kept: cached palette/style refs in emission block rendering (summary/detailed/full), bringing `focus_ms` to `16.124`.
- Kept: reused shared `STYLE_DIM` constant broadly in focus rendering paths (details, frame snapshots, summary/detailed/full sections), reducing style object churn and improving to `focus_ms=15.648`.
