# Debug Findings — painted full scan (2026-04-26)

## [MEDIUM] Bug 1: `flame_lens` — block width exceeds requested width when segments > available columns

**Location:** `src/painted/views/lens/flame.py:196-208` (`_flame_render_row`)

**Root cause:** `_flame_allocate_widths()` gives every non-last segment `max(1, ...)` width. When there are more non-last segments than available columns, their sum exceeds `width`, the last segment gets a negative allocation (skipped), and `join_horizontal` produces a block wider than requested.

**Reproduction:**
```python
# 5 segments, width=3 → block.width=4 (expected 3)
# 10 segments, width=3 → block.width=9 (expected 3)
from painted.views.lens.flame import _flame_render_row
block = _flame_render_row([('a',1),('b',1),('c',1),('d',1),('e',1)], 5.0, 3, ('red','green','blue'))
assert block.width == 3  # FAILS: block.width == 4
```

**Impact:** Any consumer of `flame_lens` with many segments in a narrow terminal gets a block wider than expected, causing layout overflow in `join_horizontal` / `join_vertical` callers.

**Suggested fix:** Add width clamping in `_flame_render_row` (same pattern as `_flame_render_levels:236`):
```python
used_width = 0
for (label, _v), seg_w in zip(segments, seg_widths):
    seg_w = max(0, min(seg_w, width - used_width))   # clamp
    used_width += seg_w
    if seg_w <= 0:
        continue
    ...
```

---

## [LOW] Bug 2: `display.py:102` — ASCII icon override missing for `show(data)` plain mode

**Location:** `src/painted/display.py:102`

**Root cause:** The condition `if not use_ansi and lens is not None:` skips the `use_icons(ASCII_ICONS)` override when using the default `shape_lens` (i.e., `lens=None`). Plain-mode `show(data)` with numeric data emits Unicode block chars (`▁▂▃▄▅▆▇█`) instead of ASCII (`_.-~^*#@`) for sparklines.

**Evidence:**
```python
show([1,2,3,4])   # plain/piped mode → outputs Unicode block sparkline chars
show([1,2,3,4], lens=shape_lens)  # correctly uses ASCII
```

**Suggested fix:** Change condition from `lens is not None` to just `True`:
```python
if not use_ansi:
    with use_icons(ASCII_ICONS):
        block = render_fn(data, zoom, width)
else:
    block = render_fn(data, zoom, width)
```

---

## [LOW] Bug 3: `record.py:294` — threshold check uses `len(sv)` not `display_width(sv)`

**Location:** `src/painted/views/record.py:294`

**Root cause:** `or len(sv) > 40` decides whether to show a field on its own continuation line. For CJK/emoji strings, `len(sv)` underestimates display width — a 4-char emoji string has `len=4` but display_width=8, so it stays inline when it should expand.

**Suggested fix:** `or display_width(sv) > 40`

---

## [LOW] Bug 4: `chart.py:182` — `.ljust(label_col)` uses character count not display width

**Location:** `src/painted/views/lens/chart.py:182`

**Root cause:** `_truncate_ellipsis(lbl, label_col - 1).ljust(label_col)` correctly truncates by display width, but then `.ljust(label_col)` pads by character count. A CJK label with display_width=4 and len=2 would be padded to 4 characters (6 display columns), misaligning bar and value columns.

**Suggested fix:** Use a display-width-aware pad function:
```python
truncated = _truncate_ellipsis(lbl, label_col - 1)
pad_needed = label_col - display_width(truncated)
lbl_text = truncated + " " * max(0, pad_needed)
```

---

## [LOW] Bug 5: `flame.py:203,254,357` — same class as Bug 4

**Location:** `src/painted/views/lens/flame.py:203,254,357`

- Line 203/254: `text.ljust(seg_w)` — char-count padding after display-width truncation
- Line 357: `label_text.center(cw)[:cw]` — char-count center + slice

Same fix pattern as Bug 4.

---

## [LOW] Bug 6: `_timer.py:45` — dead conditional expression

**Location:** `src/painted/painted/_timer.py:45`

**Root cause:** `self._log: list[FrameRecord] = [] if profile else []` — both branches create `[]`. The `if profile` condition is dead code. Should likely be `[] if profile else None` (with corresponding None-guards), but the `_profile` flag prevents appending when `profile=False`, so this is a cosmetic issue with no functional impact.

---

## [LOW] Bug 7: `tree.py:174,199` — cell slice may split wide-char pair

**Location:** `src/painted/views/lens/tree.py:174,199`

**Root cause:** `content_block.row(0)[:content_width]` slices by cell count. A wide char (2 cells: char + placeholder) at position `content_width - 1` would have the char cell included but the placeholder dropped, causing visual corruption.

**Impact:** Only the `node_renderer` custom callback path. Default string rendering is unaffected.
