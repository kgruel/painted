# Eliminated Hypotheses — painted full scan (2026-04-26)

All of these were tested and disproven. Recording them prevents re-investigating the same areas.

| # | Area | What was suspected | Why it's safe |
|---|------|--------------------|---------------|
| 1 | tui/layer.py:79 | `layers[-1]` unchecked | `if not layers:` guard at line 76 |
| 2 | focus.py:57 | `ring_prev` off-by-one | Python `(-1) % n = n-1` wraps correctly |
| 3 | compose.py:43 | Empty-block negative width | `if not blocks: return Block.empty(0,0)` guard |
| 4 | compose.py:338 | `border` loses `block.id` | Propagated via `id=block.id` (no-ids path) and `inner_ids` expansion (ids path) |
| 5 | _sparkline_core.py:72 | Division by zero on flat data | `span = hi - lo if hi > lo else 1.0` fallback |
| 6 | cursor.py | `next()` on count=0 creates invalid state | `__post_init__` normalizes every `replace()` |
| 7 | block.py `_word_wrap` | Long word infinite loop | `consumed == 0` escape drops unencodable chars |
| 8 | compose.py `truncate` | ids out-of-bounds on wide-char padding | Cell count == display width for wide-char pairs |
| 9 | list_view.py:98 | Empty list crash | Guard returns `Block.empty(1, visible_height)` |
| 10 | text_input.py | Cursor off-by-one on wide chars | Cursor is char-index throughout; display_width used for visual pos only |
| 11 | runner.py:87 | Empty-args fast path skips handlers | Handlers are dispatch targets, not mode selectors; fast path is correct |
| 12 | html.py:72 | Wide-char placeholder rendered as extra space | `iter_row_spans` yields 2-cell wide spans; only `cells[0]` rendered |
| 13 | shape_lens dispatch | Mixed dict crashes or mis-routes | One-pass dispatch handles all combos; correctly falls through |
| 14 | detect_context | AUTO→STATIC in pipe missed | `not is_tty → STATIC` covers both pipe and non-tty cases |
| 15 | surface.py resize | SIGWINCH race condition | asyncio's signal handler fires between iterations; safe single-threaded |
| 16 | profile.py DFS | Cycle crash | `visited` set prevents re-entry |
| 17 | data_explorer.py | Cursor beyond nodes crashes | `cursor.with_count(len(nodes))` clamps via `__post_init__` |
| 18 | inplace.py | Double show_cursor on finalize + exit | `_active = False` in finalize prevents re-execution in `__exit__` |
| 19 | chart.py `_chart_bars_themed` | Division by zero | `span = hi - lo if hi > lo else 1.0` fallback |
| 20 | span.py wcswidth | `-1` return crash | Fallback to `len()` is safe in practice (ANSI not in Span.text) |
