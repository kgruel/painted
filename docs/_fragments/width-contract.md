<!-- region:summary -->
width is a two-part contract: *width-aware* — wcwidth counts display columns, so a block's display width is not `len()`; and *honors-width* — a passed `width` is *exact*, clipping or padding by default (pass `wrap=Wrap.CHAR`/`Wrap.WORD` to reflow), omitted for natural sizing.
<!-- /region -->

<!-- region:full -->
width is a two-part contract, and the two guarantees are distinct and easy to conflate.

**Width-aware**: wcwidth measures display columns, so a block's display width is not `len()` — wide characters such as CJK and many emoji count as two columns (and some marks, like combining accents and variation selectors, as zero), and that column count is what the width math uses.

**Honors width**: a passed `width` is *exact* — `block.width == width`. Shorter content is padded, too-wide content is clipped by default (it never overflows horizontally); pass `wrap=Wrap.CHAR`/`Wrap.WORD` to reflow into more rows instead. Omit `width` and the block sizes to its content (natural). Exactness is what lets composition carve up a width budget and trust the pieces tile with no gap or overflow, at any terminal size. `fit_to_width(block, width)` is the block-level realization: truncate if wide, pad if narrow, identity if exact — horizontal-only, so it clips rather than reflows.
<!-- /region -->
