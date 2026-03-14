# Autoresearch: painted frame diff renderer

## Objective
Optimize end-to-end frame rendering performance for painted's cell-buffer renderer. The workload should reflect realistic library usage across multiple UI shapes: render representative dashboards/panels into Blocks, paint into Buffers, and diff frames under static, sparse-update, and churned-update scenarios. Also include a lower-level Buffer.diff companion benchmark so renderer wins do not come from shifting cost between layers.

## Metrics
- **Primary**: `frame_ms` (ms, lower is better)
- **Secondary**: `responsive_frame_ms`, `focus_frame_ms`, `diff_only_ms`, `render_ms`, `paint_ms`, `diff_ms`, `diff_cells_static`, `diff_cells_sparse`, `diff_cells_churn`, `focus_diff_cells_sparse`, `focus_diff_cells_churn`

## How to Run
`./autoresearch.sh` — outputs `METRIC frame_ms=<number>` and secondary metric lines.

## Files in Scope
- `src/painted/buffer.py` — buffer writes, diffing, line hashing
- `src/painted/block.py` — block paint internals if they matter end-to-end
- `src/painted/compose.py` — composition overhead if benchmark-backed
- `demos/patterns/responsive.py` — dashboard/render workload
- `demos/patterns/focus.py` — alternate panel-heavy workload
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
- Do not overfit to one scenario: both UI workloads and the diff-only companion stay in the benchmark
- Keep benchmark honest: real Block render -> Buffer paint -> Buffer diff pipeline

## What's Been Tried
- Initial responsive-only benchmark quickly found large wins in `Block.paint()` and `Buffer.diff()`.
- Best responsive-only run reached ~2.06ms/frame from a 3.74ms baseline by:
  - adding a Buffer-specific slice-copy fast path in `Block.paint()`
  - streamlining `Buffer.diff()`
  - short-circuiting equal buffers in `Buffer.diff()`
- Next step: broaden the benchmark to prevent overfitting by adding:
  - a second end-to-end workload based on `demos/patterns/focus.py`
  - a lower-level `Buffer.diff()` microbenchmark with static/sparse/dense cases
- Multi-workload benchmark is now in place.
- Benchmark honesty fix: the first diff-only `static` case accidentally had one changed cell due to stride generation; corrected so the static companion case is truly zero-diff before continuing optimization.
- Architectural guardrails matter: direct access to `Block._rows` from `compose.py` was rejected by checks, so optimizations should stay inside owning modules or public APIs.
