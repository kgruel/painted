# painted — follow-up items

Observations from the core extraction (2026-03-14). Each is independent.

---

## 1. Remove unnecessary print_block monkeypatching in tests

`print_block` already does late binding: `stream=None` → `sys.stdout` at call time. The test helpers that monkeypatch it to force stdout are solving a problem that doesn't exist.

**Files:**
- `tests/unit/test_fidelity.py` — `_patch_print_block_to_current_stdout` (2 copies, used by ~8 tests)
- `tests/unit/test_fidelity_extended.py` — same pattern (~5 tests)
- `tools/capture.py` — `_patch_painted_output_to_sys_stdout`

**Fix:** Replace monkeypatching with `contextlib.redirect_stdout` or just pass `stream=sys.stdout` explicitly. The `_patch_*` helpers can be deleted entirely.

---

## 2. Move `show()` out of `__init__.py`

`__init__.py` is 234 lines and defines `show()` inline — a 40-line function with lazy imports. It should live in its own module (e.g. `painted/display.py` or similar) and be re-exported from `__init__`.

**Why:** `__init__.py` should be imports and `__all__`, not business logic. The `show()` function has its own concerns (format detection, scalar passthrough, lens dispatch).

---

## 3. Group CLI framework modules into `painted/cli/`

The root still has 14 public modules. Several are clearly CLI framework concerns:

- `fidelity.py` — zoom/mode/format parsing, context detection, `run_cli`
- `app_runner.py` — multi-command routing via `run_app`
- `inplace.py` — `InPlaceRenderer` for live updates
- `palette.py` — aesthetic palettes (used by CLI rendering)
- `icon_set.py` — glyph sets with ASCII fallback

**Candidates for `cli/`:** `fidelity.py`, `app_runner.py`, `inplace.py`
**Candidates for `style/` or staying put:** `palette.py`, `icon_set.py` (used by both CLI and TUI)

This is a judgment call on where palette/icons belong. They're aesthetic concerns used everywhere, so they might stay at the root or get their own namespace.

---

## 4. Clarify shared state primitives

These modules sit at the root and are used by both CLI and TUI:
- `cursor.py` — `Cursor`, `CursorMode`
- `focus.py` — `Focus`
- `viewport.py` — `Viewport`
- `search.py` — `Search`

They're small, frozen dataclasses with no dependencies beyond each other. They could stay at the root (they're genuinely shared) or move into `core/` if they're considered fundamental enough.

---

## 5. Interactive primitives belong together

These are TUI-adjacent and could move into `tui/`:
- `keyboard.py` — key input handling
- `layer.py` — layer stack (already imported only by `tui/`)
- `region.py` — buffer sub-regions
- `app.py` — TUI app lifecycle

`layer.py`, `region.py`, and `app.py` are only imported by TUI code. `keyboard.py` is imported by `app.py`.

---

## 6. `_components/` could be `views/components/` or `components/`

`_components/` is private but provides the public component API (`spinner`, `list_view`, `table`, etc.) re-exported through `views/`. Consider whether the underscore prefix is still warranted now that there's a clear `core/` vs framework split.

---

## 7. Test `from painted import X` still works

After the core extraction, the top-level `from painted import Block, Style, run_cli` still works via `__init__.py` re-exports. But there are no tests asserting this. A simple smoke test would catch regressions:

```python
def test_top_level_imports():
    from painted import Block, Style, Cell, join_horizontal, border, run_cli, show
```

---

## 8. `big_text.py` is uncategorised

`big_text.py` (figlet-style large text rendering) depends only on core. It could live in `core/` or `views/`. Currently orphaned at the root.
