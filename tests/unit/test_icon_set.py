"""IconSet: glyph vocabulary with ContextVar delivery."""

from __future__ import annotations

import dataclasses

import pytest

from painted.icon_set import (
    ASCII_ICONS,
    IconSet,
    current_icons,
    reset_icons,
    use_icons,
)


def test_icon_set_is_frozen():
    icons = IconSet()
    with pytest.raises(AttributeError):
        icons.check = "X"  # type: ignore[misc]


def test_default_icon_set_uses_unicode():
    icons = IconSet()
    assert icons.check == "✓"
    assert icons.cross == "✗"
    assert "█" in icons.progress_fill


def test_ascii_icons_are_ascii_safe():
    for field_name in (
        "check",
        "cross",
        "progress_fill",
        "progress_empty",
        "tree_branch",
        "tree_last",
        "tree_indent",
        "ellipsis",
        "rule",
        "rank_top",
        "rank_mid",
        "rank_tail",
    ):
        val = getattr(ASCII_ICONS, field_name)
        assert all(ord(c) < 128 for c in val), f"ASCII_ICONS.{field_name} has non-ASCII"


def test_ellipsis_slot_degrades():
    assert IconSet().ellipsis == "…"
    assert ASCII_ICONS.ellipsis == "..."


def test_rule_slot_degrades():
    assert IconSet().rule == "─"
    assert ASCII_ICONS.rule == "-"


def test_rank_slots_degrade():
    assert (IconSet().rank_top, IconSet().rank_mid, IconSet().rank_tail) == ("◆", "│", "·")
    assert (ASCII_ICONS.rank_top, ASCII_ICONS.rank_mid, ASCII_ICONS.rank_tail) == ("*", "|", ".")


def test_sparkline_chars_length():
    """Sparkline needs 8 levels for proper resolution."""
    icons = IconSet()
    assert len(icons.sparkline) == 8
    assert len(ASCII_ICONS.sparkline) == 8


def test_scroll_slots_degrade():
    assert (IconSet().scroll_up, IconSet().scroll_down) == ("▲", "▼")
    assert (ASCII_ICONS.scroll_up, ASCII_ICONS.scroll_down) == ("^", "v")


def test_positional_construction_preserves_pre_scroll_field_binding():
    """Regression: new fields must be APPENDED, never inserted mid-list.

    The host-rung ``scroll_up``/``scroll_down`` slots were added at the end of
    ``IconSet`` so that a full positional ``IconSet(...)`` written against the
    historical field list still binds each value to its original slot. Were a new
    field inserted before ``sparkline`` instead, a positional construction would
    silently shift — the sparkline tuple landing in the wrong slot — and
    both-directions evidence rendering would then raise. This pins the ordering:
    it constructs positionally against every pre-``scroll`` field and asserts the
    pre-existing slots still bound correctly and the appended slots kept their
    defaults.
    """
    fields = dataclasses.fields(IconSet)
    assert [f.name for f in fields[-2:]] == ["scroll_up", "scroll_down"], (
        "scroll_up/scroll_down must remain the LAST fields — appending preserves "
        "positional-construction compatibility (do not insert new fields mid-list)"
    )

    pre_scroll = [f for f in fields if f.name not in ("scroll_up", "scroll_down")]
    # A full old-style positional construction: one arg per pre-existing field,
    # in declaration order. Correct binding ⇒ the result matches the all-default
    # set and the appended slots were not consumed positionally.
    defaults = IconSet()
    icons = IconSet(*[getattr(defaults, f.name) for f in pre_scroll])

    assert isinstance(icons.sparkline, tuple)
    assert icons.sparkline == IconSet().sparkline  # the tuple did not shift slots
    assert icons.bar_fill == "█"
    assert icons.bar_empty == "░"
    assert icons.scroll_up == "▲"  # appended slot untouched by positional args
    assert icons.scroll_down == "▼"


def test_context_var_default():
    reset_icons()
    default = current_icons()
    assert default.check == "✓"


def test_use_icons_sets_context():
    reset_icons()
    use_icons(ASCII_ICONS)
    assert current_icons() is ASCII_ICONS
    reset_icons()


def test_use_icons_context_manager_restores_previous():
    reset_icons()
    use_icons(ASCII_ICONS)

    with use_icons(IconSet()):
        assert current_icons().check == "✓"

    assert current_icons() is ASCII_ICONS
    reset_icons()


def test_reset_icons_restores_default():
    use_icons(ASCII_ICONS)
    reset_icons()
    assert current_icons().check == "✓"


def test_ascii_icons_are_pure_ascii():
    """Every glyph in ASCII_ICONS is <=127 — the capability-fallback guarantee.

    ASCII_ICONS exists so painted renders on terminals that can't show Unicode;
    a single non-ASCII glyph sneaking into a slot would silently defeat that.
    Asserted at the source value (not via a rendered canary) so it's order- and
    render-path-independent.
    """
    for field in dataclasses.fields(ASCII_ICONS):
        value = getattr(ASCII_ICONS, field.name)
        glyphs = value if isinstance(value, (tuple, list)) else [value]
        for glyph in glyphs:
            assert glyph.isascii(), f"ASCII_ICONS.{field.name}={glyph!r} is not ASCII"
