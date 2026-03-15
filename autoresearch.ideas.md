# Autoresearch Ideas — painted frame diff renderer

## Remaining optimization paths (diminishing returns territory)

- **_word_wrap optimization**: 1,600 calls at 12ms/200 renders. Could cache word-wrapped results for repeated text+width combinations.
- **Style.merge caching**: 11,600 calls at 9ms/200. Could memoize merged styles since both inputs are frozen/hashable. But these are in demo code, not library code.
- **Buffer.diff with memoryview**: Use a memoryview or array for cells instead of list, enabling faster bulk comparison. Would require significant refactoring.
- **Reduce object.__setattr__ in _create**: The 6 setattr calls per Block could potentially be reduced by using a C extension or ctypes, but that violates the "no new dependencies" constraint.
- **Pre-allocate CellWrite list**: In diff, pre-sizing the writes list based on expected change count could reduce list growth overhead.
