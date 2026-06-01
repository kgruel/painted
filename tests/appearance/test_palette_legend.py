"""Palette-role legend across presets — pins the *styled* dimension.

The legacy demo-goldens captured only the character layer, so a 5-role legend
rendered under DEFAULT, NORD, and MONO palettes stripped to byte-identical plain
text: "same structure, different aesthetic" was invisible to them. The appearance
snapshot serializes the cell *style*, so the three presets produce three
distinct snapshots. The in-test pairwise-difference assertion proves the ambient
palette is actually being applied — a plain snapshot (or a silent palette no-op)
could not catch "all three identical".
"""

from __future__ import annotations

from wcwidth import wcswidth

from painted import Line, Span, join_vertical
from painted.core.block import Block
from painted.views import (
    DEFAULT_PALETTE,
    MONO_PALETTE,
    NORD_PALETTE,
    current_palette,
    use_palette,
)

_ROLES = ("success", "warning", "error", "accent", "muted")
_LABELS = {name: f"■ {name}" for name in _ROLES}
_CHIP_WIDTH = max(wcswidth(label) for label in _LABELS.values())


def _build_legend() -> Block:
    """One chip per role, styled by the *ambient* palette, stacked vertically.

    Identical construction across palettes — the only thing that varies is the
    Style each role resolves to via `current_palette()`.
    """
    palette = current_palette()
    chips = [
        Line(spans=(Span(_LABELS[name], getattr(palette, name)),)).to_block(_CHIP_WIDTH)
        for name in _ROLES
    ]
    return join_vertical(*chips)


def test_palette_legend(appearance) -> None:
    with use_palette(DEFAULT_PALETTE):
        default_legend = _build_legend()
        appearance.assert_block(default_legend, "default")
    with use_palette(NORD_PALETTE):
        nord_legend = _build_legend()
        appearance.assert_block(nord_legend, "nord")
    with use_palette(MONO_PALETTE):
        mono_legend = _build_legend()
        appearance.assert_block(mono_legend, "mono")

    # The three renders MUST differ pairwise — otherwise the ambient palette is
    # not being applied and the snapshots are silently meaningless. Compare the
    # per-cell styles directly (the char layer alone is byte-identical).
    def _styles(block: Block) -> tuple:
        return tuple(cell.style for y in range(block.height) for cell in block.row(y))

    default_styles = _styles(default_legend)
    nord_styles = _styles(nord_legend)
    mono_styles = _styles(mono_legend)

    assert default_styles != nord_styles, "DEFAULT and NORD legends are identical"
    assert default_styles != mono_styles, "DEFAULT and MONO legends are identical"
    assert nord_styles != mono_styles, "NORD and MONO legends are identical"
