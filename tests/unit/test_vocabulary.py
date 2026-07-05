"""Unit tier — the declared-vocabulary mechanism and its honesty rules.

Pins the testable honesty rules (design doc §1): an undeclared lookup raises
(rule 2), an out-of-vocabulary value raises unless ``overflow`` is declared
(rule 3), and construction validates every declaration. Rule 1 ("a declared
vocabulary must change output") needs a mark-consuming renderer and is pinned
end-to-end with the gutter re-expression (slice 3) and ``paint(mark=)``; rule 4
(no CLI dependency) is the structural test in ``test_architecture_invariants``.
"""

from __future__ import annotations

import logging
from types import MappingProxyType

import pytest

from painted import Palette, Style, Theme, use_palette, use_theme
from painted.vocabulary import (
    Role,
    Thresholds,
    Vocabulary,
    current_vocabularies,
    mark_style,
    reset_vocabularies,
    use_vocabularies,
)
import painted.vocabulary as vocabulary


def _freshness() -> Vocabulary:
    """The design doc's example: an ordered vocabulary mixing core refs, the
    ``text`` substrate, and an inline app Role."""
    return Vocabulary(
        "freshness",
        values=("fresh", "recent", "stale", "old"),
        ordered=True,
        roles={
            "fresh": "accent",
            "recent": "text",
            "stale": Role("stale", Style(fg="bright_yellow")),
            "old": "muted",
        },
    )


# --- Honesty rule 2: an undeclared lookup raises -----------------------------


class TestUndeclaredRaises:
    def test_mark_with_no_vocabulary_active_raises(self) -> None:
        reset_vocabularies()
        with pytest.raises(ValueError, match="No vocabulary named 'freshness'"):
            mark_style("freshness", "stale")

    def test_mark_with_a_different_vocabulary_active_still_raises(self) -> None:
        use_vocabularies(_freshness())
        with pytest.raises(ValueError, match="No vocabulary named 'kind'"):
            mark_style("kind", "task")


# --- Honesty rule 3: out-of-vocabulary values --------------------------------


class TestOutOfVocabulary:
    def test_member_resolves(self) -> None:
        use_vocabularies(_freshness())
        assert mark_style("freshness", "fresh") == Palette().accent

    def test_non_member_raises_without_overflow(self) -> None:
        use_vocabularies(_freshness())
        with pytest.raises(ValueError, match="not a member of vocabulary 'freshness'"):
            mark_style("freshness", "ancient")

    def test_non_member_with_overflow_series_falls_to_ramp(self) -> None:
        kind = Vocabulary(
            "kind",
            values=("decision", "task"),
            roles={"decision": "accent", "task": "success"},
            overflow="series",
        )
        use_vocabularies(kind)
        palette = Palette()
        use_palette(palette)
        assert mark_style("kind", "novel-kind") == palette.series_for("novel-kind")


# --- Construction validation -------------------------------------------------


class TestConstructionValidation:
    def test_non_kebab_name(self) -> None:
        with pytest.raises(ValueError, match="must be lowercase kebab-case"):
            Vocabulary("Bad_Name", values=("a",), roles={"a": "accent"})

    def test_empty_values(self) -> None:
        with pytest.raises(ValueError, match="declares no values"):
            Vocabulary("v", values=(), roles={})

    def test_non_string_value(self) -> None:
        with pytest.raises(ValueError, match="must be non-empty strings"):
            Vocabulary("v", values=("a", ""), roles={"a": "accent", "": "muted"})

    def test_duplicate_values(self) -> None:
        with pytest.raises(ValueError, match="duplicate values"):
            Vocabulary("v", values=("a", "a"), roles={"a": "accent"})

    def test_unbound_value(self) -> None:
        with pytest.raises(ValueError, match="unbound"):
            Vocabulary("v", values=("a", "b"), roles={"a": "accent"})

    def test_dangling_binding(self) -> None:
        with pytest.raises(ValueError, match="binds roles for non-values"):
            Vocabulary("v", values=("a",), roles={"a": "accent", "z": "muted"})

    def test_unresolvable_role_reference(self) -> None:
        with pytest.raises(ValueError, match="not a core role"):
            Vocabulary("v", values=("a",), roles={"a": "nonrole"})

    def test_bad_overflow(self) -> None:
        with pytest.raises(ValueError, match="overflow must be"):
            Vocabulary("v", values=("a",), roles={"a": "accent"}, overflow="bad")

    def test_bad_attention(self) -> None:
        with pytest.raises(ValueError, match="attention must be"):
            Vocabulary("v", values=("a",), roles={"a": "accent"}, attention="middle")

    def test_attention_validated_even_when_unordered(self) -> None:
        # D1: attention is validated regardless of ordered.
        with pytest.raises(ValueError, match="attention must be"):
            Vocabulary("v", values=("a",), roles={"a": "accent"}, ordered=False, attention="x")

    def test_role_reusing_core_name_raises(self) -> None:
        with pytest.raises(ValueError, match="reuses a core role"):
            Role("accent", Style(fg="red"))

    def test_role_non_kebab_name_raises(self) -> None:
        with pytest.raises(ValueError, match="must be lowercase kebab-case"):
            Role("Stale", Style(fg="red"))

    def test_positional_beyond_values_raises(self) -> None:
        # roles/ordered/overflow/attention are keyword-only (doc §3 signature).
        # A positional 4th arg would otherwise bind "series" to `ordered`
        # (truthy → comparative behaviors silently unlock) with overflow=None.
        with pytest.raises(TypeError):
            Vocabulary("v", ("a",), {"a": "accent"}, True)  # type: ignore[misc]


# --- Role redeclaration ------------------------------------------------------


class TestRoleRedeclaration:
    def test_conflicting_roles_within_one_vocabulary_raise(self) -> None:
        with pytest.raises(ValueError, match="redeclared with a different style"):
            Vocabulary(
                "v",
                values=("a", "b"),
                roles={"a": Role("r", Style(fg="red")), "b": Role("r", Style(fg="blue"))},
            )

    def test_identical_roles_within_one_vocabulary_ok(self) -> None:
        v = Vocabulary(
            "v",
            values=("a", "b"),
            roles={"a": Role("r", Style(fg="red")), "b": Role("r", Style(fg="red"))},
        )
        use_vocabularies(v)
        assert mark_style("v", "a") == mark_style("v", "b") == Style(fg="red")

    def test_identical_role_across_active_vocabularies_ok(self) -> None:
        v1 = Vocabulary("v1", values=("a",), roles={"a": Role("r", Style(fg="red"))})
        v2 = Vocabulary("v2", values=("b",), roles={"b": Role("r", Style(fg="red"))})
        use_vocabularies(v1, v2)  # no raise
        assert mark_style("v1", "a") == mark_style("v2", "b")

    def test_conflicting_role_across_active_vocabularies_raises(self) -> None:
        v1 = Vocabulary("v1", values=("a",), roles={"a": Role("r", Style(fg="red"))})
        v2 = Vocabulary("v2", values=("b",), roles={"b": Role("r", Style(fg="blue"))})
        with pytest.raises(ValueError, match="redeclared with a different style"):
            use_vocabularies(v1, v2)


# --- Resolution order --------------------------------------------------------


class TestResolutionOrder:
    def test_theme_role_override_beats_declared_app_role(self) -> None:
        use_vocabularies(_freshness())
        with use_theme(Theme(roles={"stale": Style(fg="magenta")})):
            assert mark_style("freshness", "stale") == Style(fg="magenta")
        # Override lifts on scope exit — back to the declared Role.
        assert mark_style("freshness", "stale") == Style(fg="bright_yellow")

    def test_theme_role_override_beats_core_role(self) -> None:
        use_vocabularies(_freshness())
        with use_theme(Theme(roles={"accent": Style(fg="magenta")})):
            assert mark_style("freshness", "fresh") == Style(fg="magenta")

    def test_core_reference_tracks_active_palette(self) -> None:
        use_vocabularies(_freshness())
        loud = Palette(accent=Style(fg="bright_cyan", bold=True))
        with use_palette(loud):
            assert mark_style("freshness", "fresh") == loud.accent

    def test_text_bound_value_with_none_text_is_bare_style(self) -> None:
        # D5: a value bound to ``text`` when the palette's text is None → Style().
        use_vocabularies(_freshness())
        assert Palette().text is None
        assert mark_style("freshness", "recent") == Style()

    def test_text_bound_value_tracks_a_set_text_substrate(self) -> None:
        use_vocabularies(_freshness())
        with use_palette(Palette(text=Style(fg="white"))):
            assert mark_style("freshness", "recent") == Style(fg="white")


# --- Ordered behaviors -------------------------------------------------------


class TestOrderedBehaviors:
    def test_index(self) -> None:
        assert _freshness().index("stale") == 2

    def test_at_least_is_declaration_order_tail(self) -> None:
        assert _freshness().at_least("stale") == ("stale", "old")

    def test_cmp(self) -> None:
        v = _freshness()
        assert v.cmp("fresh", "old") == -1
        assert v.cmp("old", "fresh") == 1
        assert v.cmp("stale", "stale") == 0

    def test_ordered_ops_raise_on_unordered(self) -> None:
        v = Vocabulary("u", values=("a", "b"), roles={"a": "accent", "b": "muted"})
        for op, call in (
            ("index", lambda: v.index("a")),
            ("at_least", lambda: v.at_least("a")),
            ("cmp", lambda: v.cmp("a", "b")),
        ):
            with pytest.raises(ValueError, match=f"{op} requires an ordered vocabulary"):
                call()

    def test_ordered_ops_raise_on_non_members(self) -> None:
        v = _freshness()
        with pytest.raises(ValueError, match="not a member"):
            v.index("ancient")
        with pytest.raises(ValueError, match="not a member"):
            v.at_least("ancient")
        with pytest.raises(ValueError, match="not a member"):
            v.cmp("fresh", "ancient")


# --- Thresholds --------------------------------------------------------------


def _severity_vocab() -> Vocabulary:
    return Vocabulary(
        "sev",
        values=("info", "warning", "error"),
        ordered=True,
        roles={"info": "muted", "warning": "warning", "error": "error"},
    )


class TestThresholds:
    def test_greatest_floor_cleared_wins(self) -> None:
        t = Thresholds(
            _severity_vocab(),
            {logging.INFO: "info", logging.WARNING: "warning", logging.ERROR: "error"},
        )
        assert t.resolve(logging.WARNING) == "warning"
        assert t.resolve(35) == "warning"  # between WARNING(30) and ERROR(40)
        assert t.resolve(logging.ERROR) == "error"
        assert t.resolve(100) == "error"

    def test_below_all_floors_is_smallest_floor_value(self) -> None:
        # D3: below every floor → the value of the numerically smallest floor.
        t = Thresholds(
            _severity_vocab(),
            {logging.WARNING: "warning", logging.ERROR: "error"},
        )
        assert t.resolve(0) == "warning"

    def test_reproduces_resolve_severity_default_shape(self) -> None:
        # The DEFAULT_THRESHOLDS shape: DEBUG/INFO floors both onto the lowest
        # value; below-all falls to it too (parity with diagnostics._resolve_severity,
        # whose full parity test lands in slice 2).
        t = Thresholds(
            _severity_vocab(),
            {
                logging.DEBUG: "info",
                logging.INFO: "info",
                logging.WARNING: "warning",
                logging.ERROR: "error",
            },
        )
        assert t.resolve(logging.DEBUG) == "info"
        assert t.resolve(logging.NOTSET) == "info"  # below DEBUG floor
        assert t.resolve(logging.CRITICAL) == "error"  # above ERROR floor

    def test_unordered_vocabulary_raises(self) -> None:
        un = Vocabulary("u", values=("a", "b"), roles={"a": "accent", "b": "muted"})
        with pytest.raises(ValueError, match="Thresholds requires an ordered vocabulary"):
            Thresholds(un, {1: "a"})

    def test_empty_floors_raise(self) -> None:
        with pytest.raises(ValueError, match="no floors"):
            Thresholds(_severity_vocab(), {})

    def test_non_member_mapped_value_raises(self) -> None:
        with pytest.raises(ValueError, match="not a member of vocabulary 'sev'"):
            Thresholds(_severity_vocab(), {1: "nope"})


# --- Dual-mode ambient seam --------------------------------------------------


class TestDualModeSeam:
    def test_setter_persists(self) -> None:
        use_vocabularies(_freshness())
        assert "freshness" in current_vocabularies()

    def test_context_manager_restores(self) -> None:
        with use_vocabularies(_freshness()):
            assert "freshness" in current_vocabularies()
        assert "freshness" not in current_vocabularies()

    def test_context_manager_restores_prior_not_empty(self) -> None:
        # A scoped override restores the app layer that was active BEFORE the
        # block — a ContextVar reset, not a blind clear-to-empty.
        outer = Vocabulary("outer", values=("x",), roles={"x": "accent"})
        inner = Vocabulary("inner", values=("y",), roles={"y": "muted"})
        use_vocabularies(outer)  # setter — the prior app layer
        with use_vocabularies(inner):
            active = current_vocabularies()
            assert "inner" in active and "outer" not in active
        restored = current_vocabularies()
        assert "outer" in restored and "inner" not in restored

    def test_replace_semantics_not_accumulation(self) -> None:
        use_vocabularies(_freshness())
        kind = Vocabulary("kind", values=("x",), roles={"x": "accent"})
        use_vocabularies(kind)  # replaces the app layer
        active = current_vocabularies()
        assert "kind" in active and "freshness" not in active

    def test_name_collision_across_passed_vocabs_raises(self) -> None:
        a = Vocabulary("dup", values=("x",), roles={"x": "accent"})
        b = Vocabulary("dup", values=("y",), roles={"y": "muted"})
        with pytest.raises(ValueError, match="declared twice"):
            use_vocabularies(a, b)


# --- A1: the two-layer registry ----------------------------------------------


class TestBuiltinLayer:
    """The built-in layer is empty in slice 1, so these tests monkeypatch it to
    exercise the fall-through and collision behavior slice 2 relies on."""

    @pytest.fixture
    def builtin_severity(self, monkeypatch: pytest.MonkeyPatch) -> Vocabulary:
        builtin = Vocabulary(
            "severity",
            values=("info", "error"),
            ordered=True,
            roles={"info": "muted", "error": "error"},
        )
        monkeypatch.setattr(
            vocabulary,
            "_BUILTIN_VOCABULARIES",
            MappingProxyType({"severity": builtin}),
        )
        return builtin

    def test_fall_through_lookup_finds_a_builtin(self, builtin_severity: Vocabulary) -> None:
        reset_vocabularies()
        assert mark_style("severity", "error") == Palette().error

    def test_builtin_appears_in_current_vocabularies(self, builtin_severity: Vocabulary) -> None:
        reset_vocabularies()
        assert "severity" in current_vocabularies()

    def test_app_vocabulary_colliding_with_builtin_raises(
        self, builtin_severity: Vocabulary
    ) -> None:
        clash = Vocabulary("severity", values=("a",), roles={"a": "accent"})
        with pytest.raises(ValueError, match="collides with a built-in vocabulary"):
            use_vocabularies(clash)

    def test_app_layer_shadows_nothing_but_extends(self, builtin_severity: Vocabulary) -> None:
        use_vocabularies(Vocabulary("kind", values=("x",), roles={"x": "accent"}))
        assert set(current_vocabularies()) == {"severity", "kind"}
