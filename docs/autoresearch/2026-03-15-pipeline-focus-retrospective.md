# Autoresearch Retrospective — Pipeline + Focus (2026-03-15)

## Scope
Two consecutive optimization sessions were run:

1. **Experiment A**: `painted real-world pipeline profiling`
   - Primary metric: `pipeline_ms` (lower is better)
   - Workload: multi-demo end-to-end suite (`responsive`, `focus`, `profiler`, `live`) with warm and cold secondary metrics.

2. **Experiment B**: `painted focus-path pipeline`
   - Primary metric: `focus_ms` (lower is better)
   - Workload: focused `demos/patterns/focus.py` across minimal/summary/full zooms plus cold secondary metrics.

---

## Experiment A — Results

### Baseline and best
- Baseline: **`pipeline_ms=8.234`**
- Best code-backed: **`pipeline_ms=6.919`**
- Net improvement: **~15.9%**

### Highest-impact kept changes
- `src/painted/tui/testing.py`
  - Added `capture_writes` toggle and skipped `Buffer.diff()` when writes are not needed.
- `src/painted/tui/testing.py`
  - Optimized `buffer_to_lines()` to iterate contiguous `Buffer._cells` rows.
- `src/painted/core/buffer.py`
  - Optimized `Buffer.clone()` path:
    - bypassed init preallocation with `object.__new__`
    - later improved list duplication via `list.copy()`.
- `src/painted/cli/context.py`
  - Added env-size fast path and cached parsed `COLUMNS`/`LINES`.
- `src/painted/cli/runner.py`
  - Cached argparse parser across repeated `run()` calls.

### Benchmark design improvements (kept)
- Added cold metrics (`cold_start_ms`, `cold_import_ms`) as secondary.
- Separated warm and cold sampling loops to avoid perturbing the primary warm metric.

### What did *not* materially help
- Many small local micro-optimizations (style allocation tweaks, helper refactors, tiny branch cleanups, writer reset tweaks).
- Multiple promising-looking warm reruns were identified as **noise** via no-code variance checks and rejected.

---

## Experiment B — Results

### Baseline and best
- Baseline: **`focus_ms=16.177`**
- Best code-backed: **`focus_ms=15.771`**
- Net improvement: **~2.5%**

### Kept changes
- `demos/patterns/focus.py`
  - Emission rendering now passes cached palette-derived style refs into `_emission_block`.
- `demos/patterns/focus.py`
  - Reused shared `STYLE_DIM` in more hot rendering paths.
- `demos/patterns/focus.py`
  - Simplified `_key_frames()` index-selection logic (reduced per-call overhead in detailed/full paths).

### What did not help
- Broader style constant reuse (`STYLE_PLAIN`/`STYLE_BOLD`) regressed heavily in one run and was discarded.
- Further micro-refactors around check-block/style/icon plumbing and index dedup logic did not beat the best.

---

## Process quality assessment

### What went well
- Strong benchmark discipline:
  - deterministic workloads
  - explicit warm vs cold separation
  - no-code reruns to detect noise
  - strict keep/discard based on primary metric.
- Consistent rejection of non-code and noisy “wins”.
- Good target pivot: after pipeline plateau, focus-specific session was started.

### Plateau signal
Across both experiments, after major wins were captured, additional work entered the **long tail**:
- improvements became marginal and inconsistent,
- many optimizations shifted secondaries without improving the primary,
- measurement variance became a significant confounder.

---

## Recommended next steps

1. **Bank current wins** (merge kept commits to `main`).
2. If continuing optimization, start a **new target** with fresh primary metric:
   - either `cold_focus_ms` / `cold_import_ms` (startup path), or
   - a real app-level workload beyond demos.
3. Prefer structural changes over micro-edits in current focus path; most low-hanging fruit appears exhausted.
