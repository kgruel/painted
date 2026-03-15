# Frame Rendering Optimization — 2026-03-14

## Result

**3.74ms → 0.98ms per frame (73.8% faster)**

92 experiments, 42 kept. Full 225×60 multi-panel dashboard with streaming logs,
rendered through the complete Block → Buffer → diff pipeline.

## The Workload

Nine scenarios per suite pass covering three dashboard types at two screen sizes:
- **Responsive dashboard**: CI/CD pipeline with stages, jobs, deploys, alerts
- **Focus panels**: three-column layout with cursor navigation and search
- **Log dashboard**: responsive dashboard + bordered streaming log panel

Each scenario rendered as static (zero-diff), sparse-update, and heavy-churn variants
to stress both render and diff paths honestly.

## Key Wins (in order of impact)

| Change | frame_ms | Δ | Why it worked |
|--------|----------|---|---------------|
| Buffer-specific paint fast path | 2.19 | baseline | Row slice-copy instead of per-cell put |
| `slots=True` on Cell/Style | 2.59 | -0.25 | Faster construction, comparison, attribute access |
| Cell cache + `map().__getitem__` | 1.94 | -0.65 | 8× faster ASCII cell list building |
| Compose cell caching | 1.33 | -0.61 | Cached cells = identical objects → diff nearly free |
| `Block._create` bypass | 1.25 | -0.08 | Skip validation + freeze for internal callers |
| `Style.merge` cache | 1.19 | -0.06 | Avoid redundant Style construction |
| `display_width` / `char_width` caches | 1.14 | -0.05 | Eliminate repeated wcwidth calls |
| try/except cache priming | 1.05 | -0.09 | Skip per-char dict checks on hot path |
| Inlined cache in non-ASCII path | 0.98 | -0.07 | Eliminate function call overhead |

## The Cascade Effect

The most interesting finding: **one optimization unlocked the next**.

Cell caching was designed to speed up rendering by avoiding Cell construction.
But because cached cells are the *same Python object*, `Buffer.diff` got 5× faster
for free — identity comparison (`is not`) short-circuits before field comparison.

This wasn't planned. The diff went from 1.07ms to 0.13ms as a *side effect* of
render optimization.

## What Didn't Work

- Tuple-of-tuples fast return in freeze helpers (overhead of the check > savings)
- ASCII title fast path in border (neutral — titles are short)
- `Block.empty` with shared tuple rows (called too infrequently)
- zip-based cell scanning in diff (slower than indexed access)
- Extending caching to `_char_wrap` (called too infrequently to matter)

## Files

- `autoresearch.jsonl` — full experiment log (92 runs with metrics)
- `autoresearch.md` — experiment configuration and constraints
- `autoresearch.ideas.md` — remaining optimization paths (diminishing returns)
- `autoresearch.sh` — benchmark harness
- `autoresearch.checks.sh` — correctness gate (arch + lint + 1,260 unit tests)
