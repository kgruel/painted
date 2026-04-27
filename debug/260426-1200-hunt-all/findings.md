# Debug Findings — painted autonomous scan

**Session:** 260426-1200-hunt-all  
**Scope:** src/painted/**/*.py  
**Iterations:** 15  

---

## [MEDIUM] Bug 1: `build_fidelity` callback silently skipped on empty-args fast path

- **Location:** `src/painted/cli/runner.py:87-101`
- **Hypothesis:** When `CliRunner.run()` takes the fast path for empty args, `build_fidelity` is never called.
- **Evidence:**
  ```python
  if not args and self.add_args is None:
      # Fast path — build_fidelity NOT called here
      fidelity = Fidelity(depth=int(zoom))
  else:
      ...
      if self.build_fidelity is not None:
          fidelity = self.build_fidelity(parsed, fidelity)
  ```
- **Reproduction:** Invoke a `CliRunner` with `build_fidelity` set (e.g. to inject visible tags) and call `.run([])` (no args, no `add_args`). The callback is silently skipped.
- **Impact:** Any app that uses `build_fidelity` to always inject `visible` tags (e.g. toggle a gutter layer) will have inconsistent fidelity: correct when args are passed, broken when invoked with no args.
- **Root cause:** The fast path was optimised to skip parsing, but `build_fidelity` is a transform hook that should fire regardless of whether args were parsed.
- **Suggested fix:** After the `if/else` block, apply `build_fidelity` unconditionally (constructing a default `Namespace` for the fast-path call, or refactoring the fast path to always go through parsing when `build_fidelity` is set):
  ```python
  if not args and self.add_args is None and self.build_fidelity is None:
      ...  # fast path only if no hook
  ```

---

## [MEDIUM] Bug 2: `payload_lens` result silently ignored at FULL zoom in `record_line()`

- **Location:** `src/painted/views/record.py:222-325`
- **Hypothesis:** `record_line()` calls `payload_lens` at the top of the function but only uses the result at SUMMARY and DETAILED zoom; at FULL zoom the variable `content` is computed but never referenced.
- **Evidence:**
  ```python
  # Content from lens or default  (line 222)
  if payload_lens:
      content = payload_lens(kind, payload, zoom)  # called for ALL zooms
  ...
  # FULL zoom path (line 301) — never uses `content`:
  for k, v in payload.items():
      ...
  ```
- **Reproduction:** Pass a `payload_lens` to `record_line()` at `Zoom.FULL`. The lens is called but its output is discarded; raw payload dict is rendered instead.
- **Impact:** FULL-zoom consumers that expect their lens to control rendering see raw fields. Particularly broken for lenses that sanitise or remap keys.
- **Root cause:** FULL zoom path was written to iterate payload fields directly and the `content` integration was never added.
- **Suggested fix:** In the FULL zoom path, use `content` for the header/summary line, and only fall through to raw-field iteration when `content` is a plain string or when no lens is provided.

---

## [MEDIUM] Bug 3: `len()` used instead of `display_width()` for string truncation in `record.py`

- **Location:** `src/painted/views/record.py:256-257, 278-280, 292, 294-295, 440-441`
- **Hypothesis:** Five truncation sites compare string lengths against column budgets using `len()` instead of `display_width()`, causing CJK/emoji content to overflow or be mistruncated.
- **Evidence (representative):**
  ```python
  # line 256 — SUMMARY zoom content truncation
  if len(content_str) > content_width:          # WRONG: len vs columns
      content_str = content_str[: content_width - 1] + "…"  # WRONG: char slice
  
  # line 278 — DETAILED zoom primary line
  if len(primary) > content_width:              # WRONG
      primary = primary[: content_width - 1] + "…"          # WRONG
  
  # line 294 — DETAILED secondary field
  if len(field_text) > width:                   # WRONG
      field_text = field_text[: width - 1] + "…"            # WRONG
  
  # line 440 — apply_attention() collapse summary
  if len(summary) > width - 10:                 # WRONG
      summary = summary[: width - 11] + "…"                  # WRONG
  ```
- **Reproduction:** Pass a `record_line()` call with a CJK or emoji payload value that is ≤ `content_width` in character count but > `content_width` in display columns. The block will visually overflow.
- **Impact:** Visual column overflow for any non-ASCII wide-char content in records. Affects all apps (hlab, strange-loops) that render `loops read` output.
- **Root cause:** These were written with ASCII-only strings in mind. `_text_width.py` provides `display_width()` and `truncate_ellipsis()` exactly for this purpose.
- **Suggested fix:** Replace all five sites with `display_width()` for the check and `truncate_ellipsis()` or `truncate()` from `_text_width` for the cut:
  ```python
  from ..core._text_width import display_width, truncate_ellipsis
  
  if display_width(content_str) > content_width:
      content_str = truncate_ellipsis(content_str, content_width)
  ```

---

## [LOW] Bug 4: `len()` used for label-column width in `chart.py` `_chart_bars_themed()`

- **Location:** `src/painted/views/lens/chart.py:157-158`
- **Evidence:**
  ```python
  max_label = max(len(lbl) for lbl in labels)   # WRONG: char count ≠ display cols
  label_col = min(max_label + 1, width // 3)
  ```
- **Impact:** CJK dict keys produce a label column that is too narrow; labels overflow into the bar area.
- **Suggested fix:** `max(display_width(lbl) for lbl in labels)`

---

## [LOW] Bug 5: Duplicate `from __future__ import annotations` in `shape.py`

- **Location:** `src/painted/views/lens/shape.py:3-5`
- **Evidence:**
  ```python
  from __future__ import annotations
  
  from __future__ import annotations   # duplicate
  ```
- **Impact:** No functional impact (Python silently ignores duplicate `__future__` imports), but signals a bad merge/edit.
- **Suggested fix:** Remove the second import.

---

## [LOW] Bug 6: Dead code in `_cells_from_text()` — wide-char inner pop/break never executes

- **Location:** `src/painted/core/block.py:441-443`
- **Evidence:** The outer guard `if max_width is not None and used + w > max_width: break` (line 434) already ensures `used + w <= max_width`. Inside `if w == 2:`, the check `if max_width is not None and used + 2 > max_width:` uses the same `used` (not yet incremented) and is therefore always `False`. The `cells.pop(); break` can never execute.
- **Impact:** No functional impact — dead code only.
- **Suggested fix:** Remove lines 441–443.

---

## [LOW] Bug 7: Dead code in `pad()` — final `if ids_rows is None:` branch is unreachable

- **Location:** `src/painted/core/compose.py:234-235`
- **Evidence:** `ids_rows` is initialised as either `None` or `[]` at line 195. The fast path at line 197 (`if ids_rows is None: return ...`) already returns for the `None` case. The check at line 234 therefore always evaluates `False`; the `Block(rows, new_width, id=block.id)` return is unreachable.
- **Impact:** No functional impact — dead code only.
- **Suggested fix:** Remove lines 234-235; the final line becomes unconditionally `return Block(rows, new_width, ids=ids_rows)`.
