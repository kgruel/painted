# Learn Summary — 2026-04-26 17:00

## Config
- Mode: update
- Scope: everything
- Depth: standard

## Baseline → Final State

| Metric | Before | After |
|--------|--------|-------|
| Docs | 9 files, 2243 LOC | 9 files, 2119 LOC |
| Staleness | ~42 days | 0 days |
| Validation | n/a | 100% |
| Learn score | n/a | 100 |

## Docs Updated

| File | Change | Key updates |
|------|--------|-------------|
| ARCHITECTURE.md | +52 lines | Added full Module Map table with core/, cli/, views/, tui/ layout; all new modules (html.py, big_text.py, data_explorer.py, sparkline.py, zoom.py, viewport.py, mouse.py) |
| PRIMITIVES.md | +61 lines | Added sparkline, data_explorer, render_big sections; added join_responsive/vslice to composition table; fixed all API signatures |
| DATA_PATTERNS.md | +22 lines | Fixed _components/ → views/components/; added sparkline and data_explorer to component list; fixed ListState field names |
| MODE_RESOLUTION.md | +11 lines | Added cli/types.py module reference; added Fidelity/CliContext explanation |
| ZOOM_PATTERNS.md | restructured | Fixed stale _lens.py paths → views/lens/; removed non-existent Lens dataclass; added Fidelity as richer alternative |
| DEMO_PATTERNS.md | restructured | Updated import tiers for new module paths; updated demo directory structure to reflect actual layout |
| PROFILING.md | minor | Updated module import paths to views/profile.py |
| VIEWPORT_DESIGN.md | minor | Changed "planned" to "implemented at src/painted/viewport.py" |
| MOUSE.md | -307 net | Condensed from research proposal to implementation reference; replaced open questions with actual module locations |

## Validation

4 accuracy issues found and fixed in PRIMITIVES.md during validation:
1. `sparkline_with_range` — `low`/`high` → `min_val`/`max_val`
2. `ProgressState` — removed non-existent `total` field; corrected to `ProgressState(value=0.42)` (0.0–1.0 float)
3. `join_responsive` — fixed signature from `(wide, narrow, threshold)` to `(*blocks, available_width, gap=)`
4. `ListState`/`TableState` — updated to reflect actual `cursor` + `viewport` fields (not direct index/offset fields)

## Learn Score: 100/100

validation_score=100%, docs_coverage=100%, size_compliance=100%

## Recommended next steps

- Run `./dev check` to confirm docs don't break any architecture invariants
- The CLAUDE.md module map (at src/painted/CLAUDE.md level 1) still describes the old flat layout — that's a separate update
