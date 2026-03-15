# Autoresearch Retrospective — first_show cold-start (2026-03-15)

## Goal
Optimize `first_show_ms` for `show({...}, format='plain')` in fresh interpreter processes, without overfitting and without benchmark shortcuts.

## Result
- Baseline: `92.217 ms`
- Best: `48.138 ms`
- Improvement: **-47.8%**

## What Worked

### 1) Lazy package surfaces (highest leverage)
- `painted.views` moved to lazy exports via `__getattr__`
- `painted.views.lens` moved to lazy exports via `__getattr__`

This removed large eager import side effects from the first-show path.

### 2) show() cold-path tightening
- Deferred imports in `display.py` to runtime call sites
- Avoided importing `Block` for common builtin payloads before passthrough check
- Simplified icon scope usage for default shape-lens plain path

## What Didn’t Move the Needle
- Small format/context micro-optimizations
- Some shape-lens dispatch micro-refactors
- Several no-code control reruns highlighted variance but not durable gains

## Most Surprising Insight
Import topology dominated first-use latency more than local function-level tuning.
Reducing loaded modules on first-show (from ~43 down to ~15) tracked the strongest wins.

## Benchmark Discipline
- Fresh subprocess per sample
- Full multi-scenario scorecard retained (imports + first-help + wall/module/peak metrics)
- No benchmark-only behavior shortcuts
- Targeted unit tests run for kept changes

## Recommendation
Treat this target as largely complete for now. Merge and move focus to the next highest-value startup/first-use path (likely `first_help_ms` or `run_cli_import_ms`) or to a steady-state latency objective.
