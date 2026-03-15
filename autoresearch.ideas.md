# Autoresearch Ideas — painted frame diff renderer

## Summary of wins so far (3.66ms → 1.12ms, -69%)
- slots=True on Cell/Style/CellWrite dataclasses
- Cell cache (style→char→Cell) with map().__getitem__ for ASCII text
- _ascii_row_tuple: padded frozen tuple rows bypassing list intermediates
- Block._create: fast constructor bypassing validation + freeze
- Compose cell caching (_SPACE_CELL, _border_cell)
- Style.merge cache
- display_width + char_width caches
- Buffer.diff identity-based row scanning (is not)

## Remaining paths (deep diminishing returns)
- **_word_wrap optimization**: Could cache word-wrapped results for repeated text+width. ~4ms/200 renders.
- **Reduce Cell.__init__ overhead**: 59K remaining calls are from compose borders, truncate, and non-hot paths. Most are already cached; the remainder are one-off constructions.
- **Buffer internal representation**: Using array/bytes instead of list[Cell] could enable bulk comparison, but would require major refactoring and likely violate the "no public API changes" constraint.
- **Block.text dispatch optimization**: 12K calls with isascii+len checks could be slightly faster with match/case or precomputed dispatch, but gains would be ~1ms/200.
