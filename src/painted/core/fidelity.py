"""Fidelity: density limits for rendering.

Fidelity controls *how much* to show — the character and line budgets
that lenses use for sampling and truncation. This is orthogonal to
Zoom (which controls *what* to show — detail level and depth).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fidelity:
    """Density limits for rendering.

    chars: max display width for string values (None = lens default).
    lines: max items to show for collections (None = lens default).
    """

    chars: int | None = None
    lines: int | None = None
