"""Appearance snapshot of the host-rung scroll-evidence row (HOST_RUNG §6).

The evidence row is a *styled* artifact — a muted-palette marker with an ambient
direction glyph — so a plain-text assert can't see its contract: the palette
role it resolves to, the direction glyph, and the ASCII degradation are exactly
the dimensions an appearance snapshot pins. Three scenarios (below-only,
both-directions, ASCII) so a glyph or role regression shows as a one-line diff.
Cosmetics are deferred to appearance review (§6); these lock the *current*
defaults so a later polish pass is a deliberate, reviewed snapshot change.
"""

from __future__ import annotations

from painted.icon_set import ASCII_ICONS, use_icons
from painted.views import evidence_row

_WIDTH = 24


def test_evidence_row_below(appearance) -> None:
    appearance.assert_block(evidence_row(0, 763, _WIDTH), "below")


def test_evidence_row_both(appearance) -> None:
    appearance.assert_block(evidence_row(12, 763, _WIDTH), "both")


def test_evidence_row_ascii(appearance) -> None:
    with use_icons(ASCII_ICONS):
        appearance.assert_block(evidence_row(0, 763, _WIDTH), "ascii")
