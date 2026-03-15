# Autoresearch Ideas — painted frame diff renderer

## Summary of wins (3.66ms → 0.98ms, -73%)
- slots=True on Cell/Style/CellWrite dataclasses
- Cell cache (style→char→Cell) with map().__getitem__ for ASCII text  
- try/except cache priming (skip per-char checks on hot path)
- _ascii_row_tuple: padded frozen tuple rows bypassing list intermediates
- Block._create: fast constructor bypassing validation + freeze
- Compose cell caching (_SPACE_CELL, _border_cell)
- Style.merge cache, display_width cache, char_width cache
- Buffer.diff identity-based row scanning (is not)
- Inlined cell cache in _cells_from_text non-ASCII path
- Dedicated _space_cells cache for padding

## Remaining paths (very deep diminishing returns)
- **Reduce dict.get calls**: 162K dict.get + 102K __hash__ calls dominate. Strategies: reduce cache key complexity, use id()-based lookups where safe, or batch operations.
- **Reduce isascii calls**: 112K calls — some are redundant across call chain.  
- **Block._create overhead**: 15K calls × 6 setattr = 90K attribute sets. Could use __init__ bypass or tuple packing.
- **join_horizontal/vertical**: 15ms/200 renders. Could try flattening the block iteration or pre-computing row tuples.
