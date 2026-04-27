# Debug Summary — painted full scan (2026-04-26)

## Session Stats
- **Files investigated:** 38 / 57 (67%)
- **Iterations:** 33
- **Hypotheses tested:** 22 (3 confirmed, 18 disproven, 1 inconclusive)
- **Techniques used:** direct inspection, pattern search, minimal reproduction, differential analysis

## Bug Inventory

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 1 | `flame_lens` block width overflow |
| LOW | 6 | Wide-char padding, dead code, doc mismatches |

## Priority Fixes

### 1. MEDIUM — `flame_lens` width overflow (fix first)
**File:** `views/lens/flame.py:196-208`  
When there are more flame segments than available columns, `_flame_render_row` returns a block up to N× wider than requested. This affects any UI that places a flame chart in a constrained layout. The 10-segment / width-3 case renders a block of width=9.

Fix: add `seg_w = max(0, min(seg_w, width - used_width))` clamping in `_flame_render_row`, matching the existing pattern in `_flame_render_levels:236`.

### 2. LOW — `display.py` plain mode shows Unicode sparkline chars
**File:** `display.py:102`  
`show(data)` in piped/plain mode emits Unicode block chars for sparklines. Fix: apply `use_icons(ASCII_ICONS)` unconditionally when `not use_ansi`, removing the `lens is not None` condition.

### 3. LOW — Wide-char padding inconsistencies (chart + flame)
**Files:** `views/lens/chart.py:182,200`, `views/lens/flame.py:203,254,357`  
All use `.ljust()`, `.center()`, or `[:n]` string ops by character count after display-width-aware truncation. For CJK/emoji labels, columns misalign. Low impact for current usage but consistent with the fix series in the recent commit (214185a).

### 4. LOW — `record.py:294` missed display_width fix
**File:** `views/record.py:294`  
`len(sv) > 40` threshold check is the same class as the 5 sites fixed in commit 214185a. Should be `display_width(sv) > 40`.

## Areas Verified Clean
- Core block/cell/span rendering pipeline
- compose.py join/pad/border/truncate
- CLI framework (runner, fidelity, detect_context)
- Cursor, Viewport, Focus, Search primitives
- TUI: Surface, Layer stack, keyboard input, resize
- Components: list_view, text_input, table, spinner, progress
- Lenses: tree, chart (stats/sparkline paths), shape dispatch
- InPlaceRenderer, Buffer/BufferView, Writer
- Profile bridge, data_explorer
