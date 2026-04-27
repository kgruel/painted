# Debug Summary — painted autonomous scan

**Date:** 2026-04-26  
**Scope:** `src/painted/**/*.py` (~40 modules)  
**Iterations:** 15  
**All checks (arch/lint/type/test/golden) passed before and after scan.**

---

## Results

| Severity | Count | Bugs |
|----------|-------|------|
| MEDIUM   | 3     | build_fidelity fast-path skip, payload_lens FULL-zoom ignore, len() truncation |
| LOW      | 4     | chart.py label width, duplicate import, 2× dead code |
| **Total confirmed** | **7** | |

Hypotheses tested: 15 (7 confirmed, 8 disproven/eliminated)  
Files investigated: ~22 of ~40 in scope

---

## Priority Fix Order

### 1. [MEDIUM] `build_fidelity` skipped — `cli/runner.py:87`

Narrowest fix: add `self.build_fidelity is None` to the fast-path condition so tools using `build_fidelity` always go through the full parse+transform path.

```python
# Before
if not args and self.add_args is None:

# After
if not args and self.add_args is None and self.build_fidelity is None:
```

### 2. [MEDIUM] `payload_lens` ignored at FULL zoom — `views/record.py:301`

The FULL zoom path iterates raw `payload.items()` and never references `content`. Either use `content` as a rendered summary line (like DETAILED does) or document that FULL always shows raw fields and skip calling `payload_lens` at FULL zoom.

### 3. [MEDIUM] `len()` vs `display_width()` truncation — `views/record.py:256,278,294,440`

Five sites. Pattern fix:
```python
# Before
if len(content_str) > content_width:
    content_str = content_str[: content_width - 1] + "…"

# After
from ..core._text_width import display_width, truncate_ellipsis
if display_width(content_str) > content_width:
    content_str = truncate_ellipsis(content_str, content_width)
```
Apply to all five sites in `record_line()` and `apply_attention()`.

### 4. [LOW] `len()` for label width — `views/lens/chart.py:157`
```python
# Before
max_label = max(len(lbl) for lbl in labels)
# After
max_label = max(display_width(lbl) for lbl in labels)
```

### 5. [LOW] Duplicate import — `views/lens/shape.py:5`
Remove line 5 (`from __future__ import annotations`).

### 6–7. [LOW] Dead code — `core/block.py:441-443`, `core/compose.py:234-235`
Safe to remove; no functional change.

---

## Patterns to watch

- **`len()` vs `display_width()`** is the most prevalent anti-pattern. It only causes visible bugs for non-ASCII wide chars (CJK, emoji), which is easy to miss in testing. A grep for `len(` in view-layer code is a useful future audit step.
- **Conditional hooks** (like `build_fidelity`) must be applied in ALL code paths, not just the slow/parsed path. Fast paths that skip the middleware are a recurring trap.
