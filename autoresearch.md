# Autoresearch: painted frame diff renderer

## Objective
Optimize end-to-end frame rendering performance for painted's cell-buffer renderer. The workload should reflect realistic library usage: render a responsive dashboard into Blocks, paint into Buffers, and diff frames under static, sparse-update, and churned-update scenarios.

## Metrics
- **Primary**: `frame_ms` (ms, lower is better)
- **Secondary**: `render_ms`, `paint_ms`, `diff_ms`, `diff_cells_static`, `diff_cells_sparse`, `diff_cells_churn`

## How to Run
`./autoresearch.sh` — outputs `METRIC frame_ms=<number>` and secondary metric lines.

## Files in Scope
- `src/painted/buffer.py` — buffer writes, diffing, line hashing
- `src/painted/block.py` — block paint internals if they matter end-to-end
- `src/painted/compose.py` — composition overhead if benchmark-backed
- `demos/patterns/responsive.py` — representative render workload; benchmark may import from here but should not distort demo behavior
- `autoresearch.sh` — benchmark harness
- `autoresearch.checks.sh` — correctness gate
- `autoresearch.md` — experiment notes and resume context
- `autoresearch.ideas.md` — deferred optimization ideas

## Off Limits
- Public API changes
- New runtime dependencies
- Benchmark-only shortcuts that bypass real rendering, painting, or diff semantics
- Terminal I/O timing as the primary metric

## Constraints
- Preserve existing behavior and correctness
- `./dev check` must pass for kept results
- Do not overfit to one scenario: static, sparse-delta, and churned frames all stay in the benchmark
- Keep benchmark honest: real Block render -> Buffer paint -> Buffer diff pipeline

## What's Been Tried
- Fresh benchmark target from `main`; baseline pending.
- Plan: reuse `demos/patterns/responsive.py` as a realistic render source, then measure three scenarios:
  - static frame vs identical previous frame
  - sparse update (small field changes)
  - churn update (many field/status/message changes)
- Expect likely hotspots in `Block.paint()`, `Buffer.put()/put_id()`, and `Buffer.diff()` before changing higher-level rendering code.
