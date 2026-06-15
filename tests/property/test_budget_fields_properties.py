"""Property tier — budget_fields allocation laws.

budget_fields fits ordered fields into a width budget (shrink-then-drop). The
laws that must hold for any input: the result never overruns the budget in
display columns, the dropped count is a non-negative conservation residue, a
zero-drop result is exactly the full join, and dropped is monotone-decreasing
in the budget (more room never shows less).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from painted.core._text_width import display_width
from painted.core.compose import budget_fields

# Single-line printable fields: ASCII plus a few wide (CJK) and zero-width
# (combining) codepoints, so the laws are exercised against wcwidth, not len().
# No control characters — a newline would make a "field" multi-line, outside the
# single-row contract budget_fields assumes.
_FIELD_CHARS = "abcXYZ 0._-中日本語 á"  # includes a combining-friendly accented char
field_st = st.text(alphabet=_FIELD_CHARS, max_size=20)
fields_st = st.lists(field_st, max_size=8)
SEP = " · "


@given(fields=fields_st, width=st.integers(min_value=0, max_value=200))
def test_text_never_exceeds_width(fields, width):
    # The honors-width half of painted's contract: the rendered slot fits the
    # budget exactly in DISPLAY columns (separators included, wcwidth-measured).
    fit = budget_fields(fields, width)
    assert display_width(fit.text) <= width


@given(fields=fields_st, width=st.integers(min_value=0, max_value=200))
def test_dropped_is_non_negative(fields, width):
    assert budget_fields(fields, width).dropped >= 0


@given(fields=fields_st, width=st.integers(min_value=0, max_value=200))
def test_zero_dropped_is_the_full_join(fields, width):
    # dropped == 0 means nothing was shed, so the text is exactly every
    # non-empty field joined by the separator — no truncation, no drops.
    fit = budget_fields(fields, width)
    nonempty = [f for f in fields if display_width(f) > 0]
    if fit.dropped == 0:
        assert fit.text == SEP.join(nonempty)


@given(fields=fields_st, width=st.integers(min_value=0, max_value=200))
def test_full_content_fitting_means_zero_dropped(fields, width):
    # The converse: when the whole join fits the budget, nothing is dropped.
    nonempty = [f for f in fields if display_width(f) > 0]
    if display_width(SEP.join(nonempty)) <= width:
        assert budget_fields(fields, width).dropped == 0


@given(
    fields=fields_st,
    a=st.integers(min_value=0, max_value=200),
    b=st.integers(min_value=0, max_value=200),
)
def test_dropped_is_monotone_in_width(fields, a, b):
    # More budget never shows less: dropped is non-increasing as width grows.
    lo, hi = sorted((a, b))
    assert budget_fields(fields, hi).dropped <= budget_fields(fields, lo).dropped
