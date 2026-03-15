# Autoresearch: painted real-world pipeline profiling

## Objective
Optimize end-to-end performance of painted's real-world CLI/TUI pipeline, not just low-level block/buffer internals. The workload measures representative demo apps through the full run_cli stack (arg parsing, context detection, fetch/render, static/live dispatch), plus a TestSurface-based app profile path. This gives a practical profile of user-facing costs in production-like usage.

## Metrics
- **Primary**: `pipeline_ms` (ms, lower is better) — average per-scenario time across the warm full suite
- **Secondary**: `responsive_ms`, `focus_ms`, `profiler_ms`, `live_static_ms`, `live_stream_ms`, `static_plain_ms`, `static_ansi_ms`, `cold_start_ms`, `cold_import_ms`

## How to Run
`./docs/autoresearch/painted-realworld-pipeline-2026-03-15/autoresearch.sh` — outputs `METRIC name=number` lines.

## Files in Scope
- `src/painted/cli/runner.py` — run_cli dispatch and error/render flow
- `src/painted/cli/context.py` — mode/context detection
- `src/painted/inplace.py` — live-mode frame replacement path
- `src/painted/core/writer.py` — static output write path
- `src/painted/core/block.py` — rendering data structures and paint behavior
- `src/painted/core/compose.py` — composition/layout overhead
- `demos/patterns/responsive.py` — realistic dashboard workload
- `demos/patterns/focus.py` — TestSurface-driven interaction workload
- `demos/patterns/profiler.py` — profile extraction + flame rendering workload
- `demos/patterns/live.py` — static + stream run_cli workload
- `docs/autoresearch/painted-realworld-pipeline-2026-03-15/autoresearch.sh` — benchmark harness
- `docs/autoresearch/painted-realworld-pipeline-2026-03-15/autoresearch.checks.sh` — correctness gate
- `docs/autoresearch/painted-realworld-pipeline-2026-03-15/autoresearch.md` — notes and resume context
- `docs/autoresearch/painted-realworld-pipeline-2026-03-15/autoresearch.ideas.md` — deferred ideas

## Off Limits
- Public API changes
- New runtime dependencies
- Benchmark-only shortcuts that bypass run_cli dispatch/render semantics
- Measuring real terminal I/O latency as primary score

## Constraints
- Preserve existing behavior and semantics
- `./dev check` must pass for kept results
- Keep workload representative: include multiple demos and both static + stream paths
- Keep benchmark deterministic (fixed terminal dimensions, deterministic sample data)

## What's Been Tried
- Initial session setup and baseline established at `pipeline_ms=8.234`.
- First failed attempt: passed `--static` to runners that did not expose mode flags (because benchmark used bare `CliRunner` without stream/interactive handlers); fixed by relying on AUTO static resolution in non-TTY context.
- Kept optimization: cache `argparse.ArgumentParser` inside `CliRunner` across repeated `run()` calls. New score: `pipeline_ms=8.221` (~0.16% better).
