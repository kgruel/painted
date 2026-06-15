"""Unit tests for budget_fields — the shrink-then-drop field allocator.

budget_fields fits ordered labelled fields into a width budget with
first-field-wins priority: shrink each to fit, drop the tail once a field
can't clear ``min_field``. Distinct from resolve_column_widths (which keeps
every column and distributes slack proportionally) — see test_column_widths.py.
The badge ([+Nc]) and empty-field fallback are the caller's; this owns only
the allocation. Imported from the public surface to exercise the export.
"""

from painted import BudgetFit, budget_fields


class TestBasics:
    def test_all_fit_joins_with_sep(self):
        fit = budget_fields(["alpha", "beta"], 80)
        assert fit.text == "alpha · beta"
        assert fit.dropped == 0

    def test_returns_budgetfit_namedtuple(self):
        fit = budget_fields(["x"], 80)
        assert isinstance(fit, BudgetFit)
        # Unpackable and attribute-accessible — a transparent tuple.
        text, dropped = fit
        assert text == fit.text and dropped == fit.dropped

    def test_single_field(self):
        assert budget_fields(["only"], 80) == BudgetFit("only", 0)

    def test_empty_input(self):
        assert budget_fields([], 80) == BudgetFit("", 0)

    def test_custom_separator(self):
        fit = budget_fields(["a", "b"], 80, sep=", ")
        assert fit.text == "a, b"


class TestEmptyFields:
    def test_empty_strings_skipped(self):
        # Empty fields contribute nothing — not a kept part, no separator.
        fit = budget_fields(["", "value", ""], 80)
        assert fit.text == "value"
        assert fit.dropped == 0

    def test_all_empty_is_empty_result(self):
        assert budget_fields(["", "", ""], 80) == BudgetFit("", 0)


class TestFirstFieldWins:
    def test_first_field_claims_full_budget(self):
        # Width 16: "alpha" (5) · (3) leaves 8 for "beta-very-long" → 8 < 12
        # min, so beta drops entirely; alpha keeps its full width.
        fit = budget_fields(["alpha", "beta-very-long"], 16)
        assert fit.text == "alpha"
        # Dropped = beta's full content width (14), nothing of it rendered.
        assert fit.dropped == len("beta-very-long")

    def test_long_first_field_truncates_with_ellipsis(self):
        fit = budget_fields(["this-is-a-very-long-first-field"], 12)
        assert fit.text.endswith("…")
        assert len(fit.text) == 12  # ASCII: display width == len
        # 31 chars of content, 12 columns rendered (incl. the ellipsis glyph) →
        # the ellipsis is layout, so shed = total content minus rendered text.
        assert fit.dropped == len("this-is-a-very-long-first-field") - 12


class TestShrinkThenDrop:
    def test_overlong_field_drops_with_tail(self):
        # "aaaa"(4) · "bbbb"(4) fit (kept=8 + sep 3 = 11 used of 20). The third
        # field (16 cols) can't fit the 6-col remainder and 6 < 12 → no non-nub
        # truncation, so it drops; order is priority, the tail goes with it.
        long_third = "c" * 16
        fit = budget_fields(["aaaa", "bbbb", long_third], 20)
        assert fit.text == "aaaa · bbbb"
        assert fit.dropped == 16  # the whole overlong field, nothing rendered

    def test_short_whole_field_kept_in_narrow_slot(self):
        # The principled contrast with loops' over-broad guard: "ok"(2) lands in
        # a slot below min_field but FITS WHOLE, so it is kept (a complete value
        # is not a nub). min_field gates truncation, not whole fields.
        fit = budget_fields(["aaaaaaaaaaaaaa", "ok"], 20)  # 14 · 2 → 14+3+2=19 ≤ 20
        assert fit.text == "aaaaaaaaaaaaaa · ok"
        assert fit.dropped == 0

    def test_priority_order_not_backfilled(self):
        # Once a field can't be shown, the function stops — a fitting later field
        # is NOT slipped in ahead of the dropped one (contiguous-prefix shape).
        fit = budget_fields(["aaaaaaaa", "really-long-second-field", "ok"], 8)
        assert fit.text == "aaaaaaaa"
        assert "ok" not in fit.text

    def test_width_below_min_drops_everything(self):
        # First field is overlong and the whole budget (5) is below min_field →
        # no non-nub truncation possible → empty result, all content dropped.
        fit = budget_fields(["anything", "more"], 5)
        assert fit.text == ""
        assert fit.dropped == len("anything") + len("more")


class TestWcwidth:
    def test_cjk_counted_as_display_columns_not_len(self):
        # The headline correctness win over loops' len()-based copy: each CJK
        # codepoint is 2 display columns. "日本語" is 3 chars but 6 columns, so a
        # 6-column slot fits it exactly and a 5-column slot cannot.
        cjk = "日本語"  # 6 columns, 3 codepoints
        assert budget_fields([cjk], 6).text == cjk
        assert budget_fields([cjk], 5).text != cjk  # len()==3 would wrongly "fit"

    def test_cjk_truncates_on_column_overflow(self):
        # 18-column field into a 12-column slot (≥ min_field) → a non-nub
        # truncation measured in columns, not codepoints.
        field = "日本語テストデータ"  # 9 codepoints, 18 columns
        out = budget_fields([field], 12).text
        assert out != field
        assert out.endswith("…")
        # The rendered text never exceeds the slot in DISPLAY columns.
        from painted.core._text_width import display_width

        assert display_width(out) <= 12

    def test_min_field_floor_is_display_columns(self):
        # "日本"(4) kept; remaining 13-4-3 = 6 < 12 and the second field (14
        # cols) can't fit it → drops. The floor is columns, not len().
        fit = budget_fields(["日本", "中文字符串内容"], 13)
        assert fit.text == "日本"
        assert fit.dropped == 14  # "中文字符串内容" = 7 CJK codepoints = 14 columns


class TestSepAccounting:
    def test_later_fields_pay_separator_cost(self):
        # Exactly enough for two fields plus one separator, nothing to spare.
        # "field-aa"(8) · (3) "field-bb"(8) = 19 columns.
        fit = budget_fields(["field-aa", "field-bb"], 19)
        assert fit.text == "field-aa · field-bb"
        assert fit.dropped == 0

    def test_separator_cost_can_force_a_drop(self):
        # 18 columns: room for both fields' content (16) but not the separator
        # (+3 = 19). Second field gets 18-8-3 = 7 < 12 → drops.
        fit = budget_fields(["field-aa", "field-bb"], 18)
        assert fit.text == "field-aa"
