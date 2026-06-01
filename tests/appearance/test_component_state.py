"""Canonical appearance scenario — stateful view components at a fixed state.

Pins the *styled* output of the stateful components at a deterministic state, so
a styling regression (filled run losing its accent+bold, empty run losing its
muted/dim) surfaces as a precise snapshot diff. The suite resets ambient
palette/icons to defaults around every test, so the default styles below are
deterministic without setting a palette.
"""

from __future__ import annotations

from painted import Block, Style, join_vertical
from painted.views import ProgressState, SpinnerState, progress_bar, spinner


def test_component_state(appearance) -> None:
    # Spinner pinned to a fixed frame, with an accent+bold style so the glyph and
    # its style are both locked.
    spin = spinner(SpinnerState(frame=2), style=Style(fg="cyan", bold=True))
    label = Block.text("loading", Style(dim=True))
    spin_row = join_vertical(spin, label)

    # Progress at mid-fill: filled run defaults to palette.accent + bold, empty
    # run to palette.muted — the snapshot must show those as distinct style runs.
    bar = progress_bar(ProgressState(value=0.6), 20)

    block = join_vertical(spin_row, bar)
    appearance.assert_block(block, "components")
