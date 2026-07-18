"""Tests for flame_lens — proportional hierarchical visualization."""

from painted.views import flame_lens
from tests.helpers import block_to_text


class TestFlameLensZoom:
    """Tests for flame_lens at each zoom level."""

    def test_zoom_0_shows_total(self):
        """At zoom 0, flame shows root label + total value."""
        data = {"render": 45, "diff": 30, "flush": 25}
        block = flame_lens(data, 0, 40)
        text = block_to_text(block)
        assert "100" in text  # total of 45+30+25

    def test_zoom_1_shows_single_row(self):
        """At zoom 1, flame shows top-level segments in one row."""
        data = {"render": 45, "diff": 30, "flush": 25}
        block = flame_lens(data, 1, 60)
        text = block_to_text(block)
        assert "render" in text
        assert "diff" in text
        assert "flush" in text
        assert block.height == 1

    def test_zoom_2_expands_children(self):
        """At zoom 2+, flame expands child segments into additional rows."""
        data = {"main": {"render": 45, "diff": 30, "flush": 25}}
        block = flame_lens(data, 2, 60)
        text = block_to_text(block)
        assert "main" in text
        assert "render" in text
        assert block.height >= 2


class TestFlameLensProportions:
    """Tests for proportional width allocation."""

    def test_segments_fill_width(self):
        """All segments together fill the available width."""
        data = {"a": 50, "b": 50}
        block = flame_lens(data, 1, 40)
        assert block.width == 40

    def test_larger_segment_gets_more_width(self):
        """Segment with larger value gets proportionally more characters."""
        data = {"big": 90, "small": 10}
        block = flame_lens(data, 1, 40)
        row = block.row(0)
        row_text = "".join(c.char for c in row)
        assert row_text.index("big") < row_text.index("small")

    def test_single_segment_fills_width(self):
        """A single segment fills the entire width."""
        data = {"only": 100}
        block = flame_lens(data, 1, 30)
        assert block.width == 30


class TestFlameLensEdgeCases:
    """Tests for edge cases."""

    def test_empty_data(self):
        """Empty dict produces valid output."""
        block = flame_lens({}, 1, 40)
        text = block_to_text(block)
        assert "no data" in text.lower() or block.height >= 1

    def test_zero_width_returns_empty(self):
        """Zero width returns empty block."""
        block = flame_lens({"a": 1}, 1, 0)
        assert block.width == 0

    def test_nested_three_levels(self):
        """Three-level nesting at high zoom."""
        data = {"top": {"mid": {"leaf": 100}}}
        block = flame_lens(data, 3, 60)
        text = block_to_text(block)
        assert "top" in text
        assert "mid" in text
        assert "leaf" in text

    def test_zero_values_handled(self):
        """Zero-valued segments don't cause division errors."""
        data = {"active": 100, "idle": 0}
        block = flame_lens(data, 1, 40)
        text = block_to_text(block)
        assert "active" in text

    def test_width_respected(self):
        """Output block respects width constraint."""
        data = {"a": 30, "b": 70}
        block = flame_lens(data, 1, 50)
        assert block.width == 50

    def test_more_segments_than_columns(self):
        """When segments outnumber columns, output still fits requested width."""
        data = {"a": 1, "b": 1, "c": 1, "d": 1, "e": 1}
        block = flame_lens(data, 1, 3)
        assert block.width == 3


class TestFlameLensPalette:
    """flame_lens colors segments from the ambient palette's `series` ramp."""

    _DATA = {"main": {"render": 45, "diff": 30, "flush": 25}}

    @staticmethod
    def _cells(block):
        return [(c.char, c.style) for y in range(block.height) for c in block.row(y)]

    def test_default_flame_matches_legacy_cycle(self):
        """DEFAULT flame is byte-identical to the pre-`series` warm cycle.

        Parity is by construction, hash-seed independent: DEFAULT_PALETTE.series
        carries the exact (red, yellow, green, cyan) Styles the old
        `_flame_palette_colors()` derived from roles, and flame now applies
        `series[idx].merge(Style(reverse=True))` — the same Style the old
        `Style(fg=color, reverse=True)` produced. Same tuple + same index fn =>
        identical output regardless of PYTHONHASHSEED.
        """
        ambient = flame_lens(self._DATA, 2, 60)
        legacy = flame_lens(self._DATA, 2, 60, colors=("red", "yellow", "green", "cyan"))
        assert self._cells(ambient) == self._cells(legacy)

    def test_mono_flame_uses_no_color(self):
        """Honest monochrome: under MONO_PALETTE, flame segments carry no fg."""
        from painted.views import MONO_PALETTE, use_palette

        with use_palette(MONO_PALETTE):
            block = flame_lens(self._DATA, 2, 60)
        fgs = {c.style.fg for y in range(block.height) for c in block.row(y)}
        assert fgs == {None}, f"MONO flame leaked color: {fgs}"

    def test_painted_flame_uses_vivid_hex(self):
        """PAINTED_PALETTE routes vivid truecolor hexes into flame segments."""
        from painted.views import PAINTED_PALETTE, use_palette

        with use_palette(PAINTED_PALETTE):
            block = flame_lens(self._DATA, 2, 60)
        hexes = {
            c.style.fg
            for y in range(block.height)
            for c in block.row(y)
            if isinstance(c.style.fg, str) and c.style.fg.startswith("#")
        }
        assert hexes, "PAINTED flame produced no hex colors"
        assert hexes <= {s.fg for s in PAINTED_PALETTE.series}

    def test_nord_flame_uses_nord_hues(self):
        """NORD flame routes the Nord 256-color indices (ints) into segments.

        Guards the fix: the pre-`series` path stringified role fg, so "174"
        rendered as no color and NORD flame was effectively colorless. With
        int-valued `series`, segments carry real Nord hues again.
        """
        from painted.views import NORD_PALETTE, use_palette

        with use_palette(NORD_PALETTE):
            block = flame_lens(self._DATA, 2, 60)
        fgs = {
            c.style.fg for y in range(block.height) for c in block.row(y) if c.style.fg is not None
        }
        assert fgs, "NORD flame produced no colored segments"
        assert fgs <= {174, 179, 108, 110}


class TestFlameEmptySeriesRamp:
    """External-review round (gpt-5.5): an empty `series` ramp must degrade to
    the bare Style — the same §5 contract as Palette.series_for — not raise."""

    def test_empty_series_palette_renders(self):
        from painted import Palette, use_palette

        with use_palette(Palette(series=())):
            block = flame_lens({"a": 1, "b": {"c": 2}}, 2, 20)
        assert "a" in block_to_text(block)

    def test_empty_colors_argument_renders(self):
        block = flame_lens({"a": 1}, 1, 20, colors=[])
        assert "a" in block_to_text(block)


class TestFlameMergedRemainder:
    """Lens-local coverage of the S4 merged-remainder layout (RENDER_MODEL law 6).

    The render-model law gate (``test_render_model_laws.py``) pins the black-box
    evidence contract; these exercise the ``_flame_row_layout`` partition and the
    muted styling directly."""

    @staticmethod
    def _clamp_reference(alloc, width):
        ref, used = [], 0
        for x in alloc:
            c = max(0, min(x, width - used))
            ref.append(c)
            used += c
        return ref

    def test_layout_is_reference_clamp_when_all_render(self):
        """No positive segment vanishes → the partition is the pre-0.14
        allocate+clamp, with no remainder (byte-identical guarantee at the seam)."""
        from painted.views.lens.flame import _flame_allocate_widths, _flame_row_layout

        segments = [("a", 30), ("b", 50), ("c", 20)]
        total = 100.0
        for w in (10, 25, 40):
            widths, remainder = _flame_row_layout(segments, total, w)
            assert remainder is None
            assert widths == self._clamp_reference(_flame_allocate_widths(segments, total, w), w)

    def test_layout_footprint_is_the_merged_share(self):
        """The remainder occupies its merged members' combined proportional share
        (existing arithmetic), not more — survivors keep the rest."""
        from painted.views.lens.flame import _flame_row_layout

        segments = [(chr(ord("a") + i), 1) for i in range(20)]
        widths, remainder = _flame_row_layout(segments, 20.0, 12)
        assert remainder is not None
        rem_w, count = remainder
        # 18 of 20 merged; combined share int(12*18/20) == 10 cells.
        assert count == 18
        assert rem_w == 10
        # Survivors + remainder never exceed the contract width.
        assert sum(widths) + rem_w <= 12

    def test_layout_zero_segments_owe_no_remainder(self):
        """A dropped zero-valued segment produces no remainder (false-evidence)."""
        from painted.views.lens.flame import _flame_row_layout

        widths, remainder = _flame_row_layout([("a", 10), ("b", 10), ("z", 0)], 20.0, 2)
        assert remainder is None
        assert widths == [1, 1, 0]

    def test_remainder_cells_are_muted_not_reversed(self):
        """The remainder is evidence, not data: its cells carry the ambient
        ``muted`` role (dim), never a reverse-video series color."""
        from painted.views import flame_lens

        block = flame_lens({chr(ord("a") + i): 1 for i in range(20)}, 1, 12)
        row = block.row(0)
        # The "+18" marker cells sit past the two seated segments.
        marker_cells = [c for c in row if c.char in "+18"]
        assert marker_cells, "remainder marker not found"
        assert all(not c.style.reverse for c in marker_cells)
        assert all(c.style.dim for c in marker_cells)

    def test_remainder_does_not_shift_survivor_series_colors(self):
        """A survivor's series color is label-derived and unchanged by the
        remainder's appearance (the remainder takes no series index)."""
        from painted.views import flame_lens

        no_loss = flame_lens({"a": 1, "b": 1}, 1, 40)
        with_loss = flame_lens({chr(ord("a") + i): 1 for i in range(20)}, 1, 12)

        def first_fg(block, ch):
            for c in block.row(0):
                if c.char == ch:
                    return c.style.fg
            return None

        # ``a`` and ``b`` seat in both renders and keep their label-derived hue.
        assert first_fg(no_loss, "a") == first_fg(with_loss, "a")
        assert first_fg(no_loss, "b") == first_fg(with_loss, "b")
