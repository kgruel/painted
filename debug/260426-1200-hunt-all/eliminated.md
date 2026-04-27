# Eliminated Hypotheses

## H-E1: IndexError in `truncate()` when block row shorter than prefix_budget
- **Hypothesis:** `while used < prefix_budget: src_ids[used]` could index out of bounds if the block row has fewer cells than prefix_budget.
- **Disproved:** Blocks are always padded to `block.width` during construction. Since `prefix_budget = target_width - ellipsis_width < block.width` (truncate only runs when `block.width > target_width`), `used < prefix_budget < block.width = len(src_ids)`. No out-of-bounds possible.

## H-E2: Off-by-one in `border()` title placement overwriting top_right corner
- **Hypothesis:** Title rendering loop might write past the last horizontal cell into the top_right corner.
- **Disproved:** Loop checks `if pos > block.width: break` and `if w == 2 and pos + 1 > block.width: break`. The trailing space check `if pos <= block.width:` prevents writing past index `block.width` (the last horizontal cell). top_right is always at `block.width + 1`.

## H-E3: Infinite loop in `_word_wrap` when all chars unrepresentable at given width
- **Hypothesis:** If a word contains only wide chars and `width == 1`, `consumed` is always 0, causing an infinite `while word and ...` loop.
- **Disproved:** When `consumed == 0`, the code advances `word = word[1:]`. Each iteration removes one character. When `word` becomes empty, `bool(word)` is `False` and the loop exits. Characters are silently dropped, which is the documented fallback for unrepresentable widths.

## H-E4: `Surface._flush()` scroll optimization accessing out-of-bounds line hash
- **Hypothesis:** `old_full[y + n]` in `_try_flush_scroll_optimized()` could be out of bounds.
- **Disproved:** For `n > 0`, `y ∈ [overlap_start, overlap_end] = [top, bottom - n]` so `y + n ≤ bottom < height`. For `n < 0`, `y ∈ [overlap_start, overlap_end] = [top + abs_n, bottom]` so `y + n = y - abs_n ≥ top ≥ 0`. Both bounds hold.

## H-E5: `pad()` losing `block.id` when `block._ids is not None`
- **Hypothesis:** In the `ids_rows is not None` path, `pad()` returns `Block(rows, new_width, ids=ids_rows)` without passing `id=block.id`, losing the block-level id.
- **Investigated and Ruled Out:** This is intentional. When `_ids` is present, per-cell ids are authoritative. `block.id` is a shortcut for "all cells share this id" and is only meaningful when `_ids is None`. Pattern is consistent throughout compose.py (join_horizontal, join_vertical also don't propagate `id` in the ids path).

## H-E6: `TextInputState.cursor` advancing by wrong amount for wide chars in `insert()`
- **Hypothesis:** `cursor += len(ch)` advances by character count; for wide chars the cursor might misalign.
- **Disproved:** `cursor` is a character index (code point index) into `self.text`, not a display column. All cursor arithmetic operates consistently in code-point space. `_ensure_visible()` converts to display columns only for scroll arithmetic.
