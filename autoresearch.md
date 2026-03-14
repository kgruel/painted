# Autoresearch: painted frame diff renderer

## Objective
Optimize end-to-end frame rendering performance for painted's cell-buffer renderer. The workload should reflect realistic library usage across multiple UI shapes and screen sizes: render representative dashboards into Blocks, including a full-screen variant with an extra streaming log panel, paint into Buffers, and diff frames under static, sparse-update, and churned-update scenarios. Also include a lower-level Buffer.diff companion benchmark so renderer wins do not come from shifting cost between layers.

## Metrics
- **Primary**: `frame_ms` (ms, lower is better) — the top-level 225x60 suite
- **Secondary**: `frame_ms_small`, `responsive_large_ms`, `responsive_small_ms`, `focus_large_ms`, `focus_small_ms`, `log_dashboard_large_ms`, `log_dashboard_small_ms`, `diff_only_ms`, `render_ms`, `paint_ms`, `diff_ms`

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
- Do not overfit to one scenario: both screen sizes, the log-panel workload, and the diff-only companion stay in the benchmark
- Keep benchmark honest: real Block render -> Buffer paint -> Buffer diff pipeline

## What's Been Tried
- Initial responsive-only benchmark quickly found large wins in `Block.paint()` and `Buffer.diff()`.
- Best responsive-only run reached ~2.06ms/frame from a 3.74ms baseline by:
  - adding a Buffer-specific slice-copy fast path in `Block.paint()`
  - streamlining `Buffer.diff()`
  - short-circuiting equal buffers in `Buffer.diff()`
- Multi-workload benchmark was added with responsive + focus + diff-only companion.
- Benchmark honesty fix: diff-only static companion case is now truly zero-diff.
- Some narrower `Block.text()`/compose micro-optimizations did not carry over to the broader benchmark.
- Next refinement: stress full-screen rendering more realistically by adding a larger dashboard variant with a streaming log panel and benchmarking both `140x40` and `225x60`, with the larger suite as the top-level score.
- Architectural guardrails matter: optimizations should stay inside owning modules or public APIs.
